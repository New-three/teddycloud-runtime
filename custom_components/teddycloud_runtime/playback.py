"""Persistent multi-box playback timing and episode rotation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging
import random
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store

from .api import TeddyCloudError
from .boxes import configured_boxes
from .const import (
    CONF_AUDIO_ID_ENTITY,
    CONF_BOX_ID,
    CONF_PLAYBACK_ENTITY,
    CONF_TAG_ENTITY,
    PLAYBACK_STORE_KEY,
)
from .coordinator import TeddyCloudRuntimeCoordinator
from .rules import configured_rules, uid_to_ruid

_LOGGER = logging.getLogger(__name__)
_TICK = timedelta(seconds=1)
_SAVE_INTERVAL_SECONDS = 30


class PlaybackManager:
    """Track playback per box and rotate completed Custom Tonie episodes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: TeddyCloudRuntimeCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.boxes = configured_boxes(entry)
        self.rules = {
            ruid: rule
            for rule in configured_rules(entry)
            if (ruid := uid_to_ruid(rule["tonie_uid"])) is not None
        }
        self.store: Store[dict[str, Any]] = Store(
            hass, 1, f"{PLAYBACK_STORE_KEY}.{entry.entry_id}"
        )
        self.progress: dict[str, float] = {}
        self.queues: dict[str, dict[str, Any]] = {}
        self.active: dict[str, dict[str, Any]] = {}
        self.inactive: dict[str, dict[str, Any]] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribers: list[Callable[[], None]] = []
        self._completion_lock = asyncio.Lock()
        self._last_save = 0.0

    async def async_start(self) -> None:
        """Load state and begin observing all configured boxes."""
        stored = await self.store.async_load()
        if isinstance(stored, dict):
            progress = stored.get("progress")
            queues = stored.get("queues")
            if isinstance(progress, dict):
                self.progress = {
                    str(key): float(value)
                    for key, value in progress.items()
                    if isinstance(value, (int, float))
                }
            if isinstance(queues, dict):
                self.queues = {
                    str(key): dict(value)
                    for key, value in queues.items()
                    if isinstance(value, dict)
                }
            self._restore_active(stored.get("active"))

        entities = {
            box[key]
            for box in self.boxes
            for key in (
                CONF_AUDIO_ID_ENTITY,
                CONF_PLAYBACK_ENTITY,
                CONF_TAG_ENTITY,
            )
        }

        @callback
        def source_changed(event: Event) -> None:
            self.hass.async_create_task(self._async_sources_changed())

        self._unsubscribers.append(
            async_track_state_change_event(self.hass, list(entities), source_changed)
        )
        self._unsubscribers.append(
            async_track_time_interval(self.hass, self._async_tick, _TICK)
        )

        @callback
        def stopping(event: Event) -> None:
            self.hass.async_create_task(self.async_stop())

        self._unsubscribers.append(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stopping)
        )
        await self._async_sources_changed()
        await self.async_retry_assignments()

    async def async_stop(self) -> None:
        """Pause sessions, save them, and remove listeners."""
        await self._async_save(stopping=True)
        while self._unsubscribers:
            self._unsubscribers.pop()()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe a sensor to timer updates."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def snapshot(self, box_id: str) -> dict[str, Any]:
        """Return current calculated values for one box."""
        active = self.active.get(box_id)
        if active is None:
            inactive = getattr(self, "inactive", {}).get(box_id, {})
            return {
                "elapsed": None,
                "remaining": None,
                "progress": None,
                "status": str(inactive.get("status", "unknown")),
                "next_episode": None,
                "next_audio_id": None,
                "audio_id": inactive.get("audio_id"),
                "ruid": inactive.get("ruid"),
                "can_assign": False,
            }
        runtime = self._runtime(active["audio_id"])
        elapsed = self._elapsed(box_id)
        queue = self.queues.get(active["ruid"], {})
        status = str(active.get("source_status", "paused"))
        if active.get("started_at") is not None:
            status = "playing"
        if (
            status != "waiting_for_mqtt"
            and queue.get("last_completed") == active["audio_id"]
        ):
            status = str(queue.get("status", "waiting_for_download"))
        next_audio_id = self._preview_audio_id(active, queue)
        metadata = self.coordinator.data.current_metadata(next_audio_id)
        return {
            "elapsed": elapsed,
            "remaining": max(0.0, runtime - elapsed) if runtime else None,
            "progress": min(100.0, elapsed / runtime * 100) if runtime else None,
            "status": status,
            "next_episode": metadata.episode if metadata else None,
            "next_audio_id": next_audio_id,
            "audio_id": active["audio_id"],
            "ruid": active["ruid"],
            "can_assign": True,
        }

    def can_assign(self, box_id: str) -> bool:
        """Return whether a configured Custom Tonie is active on the box."""
        return bool(self.snapshot(box_id).get("can_assign"))

    def _restore_active(self, stored: Any) -> None:
        """Restore paused sessions while waiting for live MQTT source states."""
        if not isinstance(stored, dict):
            return
        box_ids = {box[CONF_BOX_ID] for box in self.boxes}
        for box_id, value in stored.items():
            if not isinstance(value, dict) or str(box_id) not in box_ids:
                continue
            ruid = str(value.get("ruid", ""))
            audio_id = str(value.get("audio_id", ""))
            try:
                cycle = int(value.get("cycle", 1))
            except (TypeError, ValueError):
                continue
            if (
                ruid not in self.rules
                or audio_id not in self.coordinator.data.audio_files
            ):
                continue
            self.active[str(box_id)] = {
                "ruid": ruid,
                "audio_id": audio_id,
                "cycle": cycle,
                "started_at": None,
                "source_status": "waiting_for_mqtt",
                "was_playing": bool(value.get("was_playing", False)),
            }

    def _preview_audio_id(
        self, active: dict[str, Any], queue: dict[str, Any]
    ) -> str | None:
        """Return the episode following the active one in the shuffled queue."""
        current_audio_id = str(active["audio_id"])
        order = [
            str(candidate)
            for candidate in queue.get("order", [])
            if str(candidate) in self.coordinator.data.audio_files
        ]
        if not order:
            return None
        if order[0] != current_audio_id:
            return order[0]
        return order[1] if len(order) > 1 else None

    async def async_mark_complete(self, box_id: str) -> None:
        """Assign the next episode centrally for the active Custom Tonie."""
        box = next(
            (candidate for candidate in self.boxes if candidate[CONF_BOX_ID] == box_id),
            None,
        )
        if box is not None:
            self._sync_box(box)
        active = self.active.get(box_id)
        if active:
            await self._async_complete(box_id, active)

    async def async_reset_progress(self, box_id: str) -> None:
        """Reset current playback progress for one box."""
        active = self.active.get(box_id)
        if not active:
            return
        self.progress[self._progress_key(box_id, active)] = 0.0
        if active.get("started_at") is not None:
            active["started_at"] = self._now()
        await self._async_save()
        self._notify()

    async def async_retry_assignments(self) -> None:
        """Retry every persisted pending TeddyCloud assignment."""
        for ruid, queue in list(self.queues.items()):
            if ruid not in self.rules:
                continue
            pending = queue.get("pending_assignment")
            if isinstance(pending, dict):
                if not self._audio_matches_rule(
                    str(pending.get("audio_id", "")), ruid
                ):
                    queue["pending_assignment"] = None
                    queue["status"] = "rule_changed"
                    await self._async_save()
                    continue
                await self._async_assign(ruid, queue, pending)

    async def _async_sources_changed(self) -> None:
        for box in self.boxes:
            self._sync_box(box)
        self._notify()

    async def _async_tick(self, now: Any) -> None:
        for box in self.boxes:
            self._sync_box(box)
        for box_id, active in list(self.active.items()):
            if active.get("source_status") in {
                "waiting_for_mqtt",
                "waiting_for_assignment",
            }:
                continue
            # Seed a configured Custom Tonie immediately when it still contains
            # its original audio or audio from a previously selected series.
            if not self._audio_matches_rule(active["audio_id"], active["ruid"]):
                await self._async_complete(box_id, active)
                continue
            runtime = self._runtime(active["audio_id"])
            if runtime and self._elapsed(box_id) >= runtime:
                await self._async_complete(box_id, active)
        if self._now() - self._last_save >= _SAVE_INTERVAL_SECONDS:
            await self._async_save()
        self._notify()

    def _sync_box(self, box: dict[str, str]) -> None:
        if not hasattr(self, "inactive"):
            self.inactive = {}
        box_id = box[CONF_BOX_ID]
        audio_id, audio_available = self._source_state(
            box[CONF_AUDIO_ID_ENTITY]
        )
        tag_uid, tag_available = self._source_state(box[CONF_TAG_ENTITY])
        current = self.active.get(box_id)
        if not audio_available or not tag_available:
            self._pause(box_id)
            if current is not None:
                current["source_status"] = "waiting_for_mqtt"
            return

        ruid = self._ruid(tag_uid)
        if not audio_id or ruid not in self.rules:
            self._pause(box_id)
            self.active.pop(box_id, None)
            self.inactive[box_id] = {
                "audio_id": audio_id or None,
                "ruid": ruid,
                "status": (
                    "no_matching_rule"
                    if audio_id and ruid
                    else "no_active_tonie"
                ),
            }
            return
        self.inactive.pop(box_id, None)

        queue = self.queues.get(ruid, {})
        awaiting_audio_id = str(queue.get("awaiting_audio_id", ""))
        if awaiting_audio_id and audio_id != awaiting_audio_id:
            self._pause(box_id)
            cycle = int(queue.get("cycle", 1))
            identity = (ruid, audio_id, cycle)
            if current is None or (
                current["ruid"], current["audio_id"], current["cycle"]
            ) != identity:
                current = {
                    "ruid": ruid,
                    "audio_id": audio_id,
                    "cycle": cycle,
                    "started_at": None,
                    "was_playing": False,
                }
                self.active[box_id] = current
            current["source_status"] = "waiting_for_assignment"
            current["was_playing"] = False
            return
        if awaiting_audio_id == audio_id:
            queue.pop("awaiting_audio_id", None)
            queue["status"] = "ready"

        cycle = int(queue.get("cycle", 1))
        identity = (ruid, audio_id, cycle)
        if current is None or (
            current["ruid"], current["audio_id"], current["cycle"]
        ) != identity:
            self._pause(box_id)
            current = {
                "ruid": ruid,
                "audio_id": audio_id,
                "cycle": cycle,
                "started_at": None,
                "source_status": "paused",
                "was_playing": False,
            }
            self.active[box_id] = current

        playback_state, playback_available = self._source_state(
            box[CONF_PLAYBACK_ENTITY]
        )
        if not playback_available:
            self._pause(box_id)
            current["source_status"] = "waiting_for_mqtt"
            return

        playing = self._is_playing(playback_state)
        already_complete = queue.get("last_completed") == audio_id
        if playing and not already_complete and current["started_at"] is None:
            current["started_at"] = self._now()
            current["source_status"] = "playing"
            current["was_playing"] = True
        elif (not playing or already_complete) and current["started_at"] is not None:
            self._pause(box_id)
            current["source_status"] = "paused"
            current["was_playing"] = False
        elif not playing or already_complete:
            current["source_status"] = "paused"
            current["was_playing"] = False

    async def _async_complete(
        self, box_id: str, active: dict[str, Any]
    ) -> None:
        async with self._completion_lock:
            ruid = active["ruid"]
            audio_id = active["audio_id"]
            queue = self.queues.get(ruid)
            series = self.rules[ruid]["series"]
            if queue and str(queue.get("series", "")).casefold() != series.casefold():
                queue = None
            if queue and queue.get("last_completed") == audio_id:
                return
            runtime = self._runtime(audio_id)
            if runtime:
                self.progress[self._progress_key(box_id, active)] = runtime
            # A TeddyCloud assignment belongs to the Custom Tonie, not to a
            # single box. Stop every session for this RUID so another box
            # cannot finish a stale timer and immediately rotate it again.
            for other_box_id, other in self.active.items():
                if other["ruid"] == ruid:
                    self._pause(other_box_id)
                    other["source_status"] = "waiting_for_assignment"
                    other["was_playing"] = False

            pool = [
                candidate.audio_id
                for candidate in self.coordinator.data.audio_files.values()
                if candidate.metadata is not None
                and candidate.metadata.series.casefold() == series.casefold()
            ]
            if not pool:
                return
            if queue is None:
                order = [candidate for candidate in pool if candidate != audio_id]
                random.SystemRandom().shuffle(order)
                queue = {"cycle": 1, "order": order, "series": series}
                self.queues[ruid] = queue
            else:
                order = [
                    candidate
                    for candidate in queue.get("order", [])
                    if candidate != audio_id and candidate in pool
                ]
                queue["order"] = order

            if not queue["order"]:
                queue["cycle"] = int(queue.get("cycle", 1)) + 1
                order = list(pool)
                random.SystemRandom().shuffle(order)
                if len(order) > 1 and order[0] == audio_id:
                    order[0], order[1] = order[1], order[0]
                queue["order"] = order

            next_audio_id = str(queue["order"][0])
            next_audio = self.coordinator.data.audio_files[next_audio_id]
            pending = {
                "audio_id": next_audio_id,
                "path": next_audio.path,
            }
            queue.update(
                {
                    "last_completed": audio_id,
                    "next_audio_id": next_audio_id,
                    "awaiting_audio_id": next_audio_id,
                    "pending_assignment": pending,
                    "status": "assigning",
                    "error": None,
                }
            )
            await self._async_save()
            await self._async_assign(ruid, queue, pending)
            self._notify()

    async def _async_assign(
        self, ruid: str, queue: dict[str, Any], pending: dict[str, Any]
    ) -> None:
        if ruid not in self.rules:
            _LOGGER.error("Refusing assignment for unconfigured RUID %s", ruid)
            return
        try:
            await self.coordinator.client.async_assign_audio(
                ruid, str(pending["path"])
            )
        except TeddyCloudError as err:
            queue["status"] = "assignment_error"
            queue["error"] = str(err)
            _LOGGER.error("Failed assigning next episode to %s: %s", ruid, err)
        else:
            queue["pending_assignment"] = None
            queue["status"] = "waiting_for_download"
            queue["error"] = None
        await self._async_save()

    def _pause(self, box_id: str) -> None:
        active = self.active.get(box_id)
        if not active or active.get("started_at") is None:
            return
        key = self._progress_key(box_id, active)
        self.progress[key] = self.progress.get(key, 0.0) + (
            self._now() - float(active["started_at"])
        )
        active["started_at"] = None

    def _elapsed(self, box_id: str) -> float:
        active = self.active[box_id]
        elapsed = self.progress.get(self._progress_key(box_id, active), 0.0)
        if active.get("started_at") is not None:
            elapsed += self._now() - float(active["started_at"])
        return max(0.0, elapsed)

    def _progress_key(self, box_id: str, active: dict[str, Any]) -> str:
        return (
            f"{box_id}|{active['ruid']}|{active['audio_id']}|{active['cycle']}"
        )

    def _runtime(self, audio_id: str) -> float | None:
        audio = self.coordinator.data.audio_files.get(str(audio_id))
        return audio.runtime_seconds if audio else None

    def _audio_matches_rule(self, audio_id: str, ruid: str) -> bool:
        """Return whether an audio file still belongs to this rule's series."""
        audio = self.coordinator.data.audio_files.get(audio_id)
        return bool(
            audio
            and audio.metadata
            and ruid in self.rules
            and audio.metadata.series.casefold()
            == self.rules[ruid]["series"].casefold()
        )

    async def _async_save(self, *, stopping: bool = False) -> None:
        saved_at = self._now()
        persisted_active: dict[str, dict[str, Any]] = {}
        for box_id in list(self.active):
            active = self.active[box_id]
            was_playing = active.get("started_at") is not None
            if was_playing:
                self._pause(box_id)
            persisted_active[box_id] = {
                "ruid": active["ruid"],
                "audio_id": active["audio_id"],
                "cycle": active["cycle"],
                "was_playing": was_playing
                or bool(active.get("was_playing", False)),
                "saved_at": saved_at,
            }
            if was_playing and not stopping:
                active["started_at"] = self._now()
        await self.store.async_save(
            {
                "progress": self.progress,
                "queues": self.queues,
                "active": persisted_active,
            }
        )
        self._last_save = self._now()

    def _source_state(self, entity_id: str) -> tuple[str | None, bool]:
        """Return a source value and whether MQTT currently provides it."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in {"unknown", "unavailable"}:
            return None, False
        return state.state, True

    @staticmethod
    def _ruid(value: str | None) -> str | None:
        if not value:
            return None
        compact = "".join(character for character in value if character.isalnum())
        if len(compact) != 16:
            return None
        try:
            return bytes.fromhex(compact)[::-1].hex()
        except ValueError:
            return None

    @staticmethod
    def _is_playing(value: str | None) -> bool:
        return bool(value and value.casefold() in {"on", "playing", "true", "1"})

    @staticmethod
    def _now() -> float:
        return time.time()

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()
