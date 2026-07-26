"""Data coordinator for TeddyCloud Runtime."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TeddyCloudClient, TeddyCloudError
from .const import (
    DOMAIN,
    LIBRARY_CONCURRENCY,
    STORE_KEY,
    STORE_VERSION,
    UPDATE_INTERVAL,
)
from .models import AudioFile, LibraryItem, RuntimeData, TonieMetadata

_LOGGER = logging.getLogger(__name__)


class TeddyCloudRuntimeCoordinator(DataUpdateCoordinator[RuntimeData]):
    """Coordinate library data and cached runtime discovery."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TeddyCloudClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client
        self.store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)
        self.cache: dict[str, dict[str, Any]] = {}
        self._cache_loaded = False
        self._refresh_identifiers: set[str] = set()
        self._clear_all_runtimes = False

    async def _async_setup(self) -> None:
        """Load persistent cache before the first refresh."""
        stored = await self.store.async_load()
        if isinstance(stored, dict):
            entries = stored.get("entries", {})
            if isinstance(entries, dict):
                # Current cache keys contain audio ID, hash and file size.
                # Discard obsolete entries without requiring a Store migration.
                self.cache = {
                    key: value
                    for key, value in entries.items()
                    if isinstance(key, str)
                    and key.count("|") == 2
                    and isinstance(value, dict)
                    and isinstance(value.get("audio_id"), str)
                    and isinstance(value.get("path"), str)
                    and isinstance(value.get("runtime_seconds"), (int, float))
                }
        self._cache_loaded = True

    async def _async_update_data(self) -> RuntimeData:
        """Read and merge the TeddyCloud library."""
        try:
            tags, custom_rows, library_rows = await asyncio.gather(
                self.client.async_get_tag_index(),
                self.client.async_get_custom_metadata(),
                self.client.async_get_library_files(),
            )
            metadata_by_audio, metadata_by_model = _metadata_maps(custom_rows)
            items = _library_items(tags, metadata_by_model)
            audio_files = _audio_files(library_rows, metadata_by_audio)

            cache_changed = False
            if self._clear_all_runtimes:
                self.cache.clear()
                self._clear_all_runtimes = False
                cache_changed = True

            for identifier in self._refresh_identifiers:
                audio = audio_files.get(identifier)
                if audio is None:
                    item = items.get(identifier)
                    if item and item.metadata and item.metadata.audio_ids:
                        audio = audio_files.get(item.metadata.audio_ids[0])
                if audio is not None:
                    self.cache.pop(audio.cache_key, None)
                    cache_changed = True
            self._refresh_identifiers.clear()

            semaphore = asyncio.Semaphore(LIBRARY_CONCURRENCY)

            async def populate(audio: AudioFile) -> None:
                nonlocal cache_changed
                cached = self.cache.get(audio.cache_key)
                if cached is not None:
                    runtime = cached.get("runtime_seconds")
                    if isinstance(runtime, (int, float)) and runtime > 0:
                        audio.runtime_seconds = float(runtime)
                        return
                async with semaphore:
                    try:
                        runtime = await self.client.async_runtime(
                            self.client.library_audio_url(audio.path)
                        )
                    except TeddyCloudError as err:
                        _LOGGER.warning(
                            "Could not determine runtime for library file %s: %s",
                            audio.path,
                            err,
                        )
                        return
                    audio.runtime_seconds = runtime
                    self.cache[audio.cache_key] = {
                        "audio_id": audio.audio_id,
                        "path": audio.path,
                        "runtime_seconds": runtime,
                    }
                    cache_changed = True

            await asyncio.gather(
                *(
                    populate(audio)
                    for audio in audio_files.values()
                    if audio.valid
                )
            )
            if cache_changed:
                await self.store.async_save({"entries": self.cache})

            populated = sum(
                audio.runtime_seconds is not None for audio in audio_files.values()
            )
            return RuntimeData(
                items=items,
                audio_files=audio_files,
                metadata_by_audio_id=metadata_by_audio,
                metadata_by_model=metadata_by_model,
                cache_entries=len(self.cache),
                cache_state="ready" if populated else "empty",
                raw_custom_count=len(custom_rows),
            )
        except TeddyCloudError as err:
            raise UpdateFailed(f"TeddyCloud update failed: {err}") from err

    async def async_clear_cache(self) -> None:
        """Clear all runtime cache values and refresh the library."""
        self._clear_all_runtimes = True
        await self.async_request_refresh()

    async def async_refresh_runtime(self, identifier: str | None) -> None:
        """Force runtime recalculation for one or all library items."""
        if identifier:
            self._refresh_identifiers.add(identifier.lower())
        else:
            self._clear_all_runtimes = True
        await self.async_request_refresh()


def _metadata_maps(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, TonieMetadata], dict[str, TonieMetadata]]:
    """Build custom JSON lookup maps."""
    by_audio: dict[str, TonieMetadata] = {}
    by_model: dict[str, TonieMetadata] = {}
    for row in rows:
        audio_ids = tuple(str(value) for value in row.get("audio_id", []) if value)
        hashes = tuple(str(value) for value in row.get("hash", []) if value)
        metadata = TonieMetadata(
            model=str(row.get("model", "")),
            audio_ids=audio_ids,
            hashes=hashes,
            series=str(row.get("series", "")),
            episode=str(row.get("episodes", row.get("episode", ""))),
            picture=str(row.get("pic", row.get("picture", ""))),
            tracks=tuple(str(value) for value in row.get("tracks", []) if value),
        )
        if metadata.model:
            by_model[metadata.model] = metadata
        for audio_id in audio_ids:
            by_audio[audio_id] = metadata
    return by_audio, by_model


def _library_items(
    tags: list[dict[str, Any]],
    metadata_by_model: dict[str, TonieMetadata],
) -> dict[str, LibraryItem]:
    """Convert tag-index records and attach immutable custom metadata."""
    result: dict[str, LibraryItem] = {}
    for tag in tags:
        ruid = str(tag.get("ruid", "")).lower()
        if not ruid or tag.get("type") != "tag":
            continue
        source_info = tag.get("sourceInfo") or {}
        tonie_info = tag.get("tonieInfo") or {}
        model = str(source_info.get("model") or tonie_info.get("model") or "")
        metadata = metadata_by_model.get(model)
        audio_url = str(tag.get("audioUrl", ""))
        item = LibraryItem(
            ruid=ruid,
            uid=str(tag.get("uid", "")),
            audio_url=audio_url,
            exists=bool(tag.get("exists")),
            nocloud=bool(tag.get("nocloud")),
            source=str(tag.get("source", "")),
            track_count=len(tag.get("trackSeconds") or []),
            model=model,
            metadata=metadata,
        )
        result[ruid] = item
    return result


def _audio_files(
    rows: list[dict[str, Any]],
    metadata_by_audio: dict[str, TonieMetadata],
) -> dict[str, AudioFile]:
    """Convert fileIndexV2 rows into the complete physical audio library."""
    result: dict[str, AudioFile] = {}
    for row in rows:
        path = str(row.get("path", ""))
        header = row.get("tafHeader") or {}
        audio_id = str(header.get("audioId", ""))
        if not path.lower().endswith(".taf") or not audio_id:
            continue
        audio = AudioFile(
            path=path,
            audio_id=audio_id,
            sha1_hash=str(header.get("sha1Hash", "")),
            size=int(row.get("size", 0)),
            valid=bool(header.get("valid")),
            track_count=len(header.get("trackSeconds") or []),
            metadata=metadata_by_audio.get(audio_id),
        )
        result[audio_id] = audio
    return result
