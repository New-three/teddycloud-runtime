"""Sensors for TeddyCloud Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AUDIO_ID_ENTITY,
    CONF_BOX_ID,
    CONF_BOX_NAME,
    CONF_PLAYBACK_ENTITY,
    CONF_TAG_ENTITY,
    DOMAIN,
)
from .boxes import configured_boxes
from .coordinator import TeddyCloudRuntimeCoordinator
from .models import AudioFile, LibraryItem, RuntimeData, TonieMetadata


@dataclass(frozen=True, kw_only=True)
class TeddyCloudSensorDescription(SensorEntityDescription):
    """Describe a TeddyCloud sensor."""

    value_fn: Callable[["TeddyCloudRuntimeSensor"], Any]


def _metadata(entity: "TeddyCloudRuntimeSensor") -> TonieMetadata | None:
    return entity.coordinator.data.current_metadata(entity.audio_id)


def _item(entity: "TeddyCloudRuntimeSensor") -> LibraryItem | None:
    if not entity.ruid:
        return None
    return entity.coordinator.data.items.get(entity.ruid)


def _audio(entity: "TeddyCloudRuntimeSensor") -> AudioFile | None:
    if not entity.audio_id:
        return None
    return entity.coordinator.data.audio_files.get(entity.audio_id)


def _playback_value(
    entity: "TeddyCloudRuntimeSensor", key: str
) -> Any:
    if entity.box is None:
        return None
    return entity.coordinator.playback.snapshot(entity.box[CONF_BOX_ID]).get(key)


SENSORS: tuple[TeddyCloudSensorDescription, ...] = (
    TeddyCloudSensorDescription(
        key="episode",
        translation_key="episode",
        value_fn=lambda entity: (
            metadata.episode if (metadata := _metadata(entity)) else None
        ),
    ),
    TeddyCloudSensorDescription(
        key="series",
        translation_key="series",
        value_fn=lambda entity: (
            metadata.series if (metadata := _metadata(entity)) else None
        ),
    ),
    TeddyCloudSensorDescription(
        key="audio_id",
        translation_key="audio_id",
        value_fn=lambda entity: entity.audio_id,
    ),
    TeddyCloudSensorDescription(
        key="runtime",
        translation_key="runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=1,
        value_fn=lambda entity: (
            audio.runtime_seconds if (audio := _audio(entity)) else None
        ),
    ),
    TeddyCloudSensorDescription(
        key="current_ruid",
        translation_key="current_ruid",
        value_fn=lambda entity: entity.ruid,
    ),
    TeddyCloudSensorDescription(
        key="track_count",
        translation_key="track_count",
        value_fn=lambda entity: (
            audio.track_count if (audio := _audio(entity)) else None
        ),
    ),
    TeddyCloudSensorDescription(
        key="elapsed",
        translation_key="elapsed",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=1,
        value_fn=lambda entity: _playback_value(entity, "elapsed"),
    ),
    TeddyCloudSensorDescription(
        key="remaining",
        translation_key="remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=1,
        value_fn=lambda entity: _playback_value(entity, "remaining"),
    ),
    TeddyCloudSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda entity: _playback_value(entity, "progress"),
    ),
    TeddyCloudSensorDescription(
        key="playback_status",
        translation_key="playback_status",
        value_fn=lambda entity: _playback_value(entity, "status"),
    ),
    TeddyCloudSensorDescription(
        key="next_episode",
        translation_key="next_episode",
        value_fn=lambda entity: _playback_value(entity, "next_episode"),
    ),
    TeddyCloudSensorDescription(
        key="cache_state",
        translation_key="cache_state",
        value_fn=lambda entity: entity.coordinator.data.cache_state,
    ),
    TeddyCloudSensorDescription(
        key="library_count",
        translation_key="library_count",
        value_fn=lambda entity: len(entity.coordinator.data.items),
    ),
    TeddyCloudSensorDescription(
        key="custom_episode_count",
        translation_key="custom_episode_count",
        value_fn=lambda entity: entity.coordinator.data.raw_custom_count,
    ),
    TeddyCloudSensorDescription(
        key="library_audio_count",
        translation_key="library_audio_count",
        value_fn=lambda entity: len(entity.coordinator.data.audio_files),
    ),
    TeddyCloudSensorDescription(
        key="custom_runtime_count",
        translation_key="custom_runtime_count",
        value_fn=lambda entity: entity.coordinator.data.custom_runtime_count,
    ),
    TeddyCloudSensorDescription(
        key="pending_custom_runtime_count",
        translation_key="pending_custom_runtime_count",
        value_fn=lambda entity: max(
            0,
            entity.coordinator.data.raw_custom_count
            - entity.coordinator.data.custom_runtime_count,
        ),
    ),
    TeddyCloudSensorDescription(
        key="cached_runtime_count",
        translation_key="cached_runtime_count",
        value_fn=lambda entity: entity.coordinator.data.cache_entries,
    ),
)

CURRENT_SENSOR_KEYS = {
    "episode",
    "series",
    "audio_id",
    "runtime",
    "current_ruid",
    "track_count",
    "elapsed",
    "remaining",
    "progress",
    "playback_status",
    "next_episode",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TeddyCloud Runtime sensors."""
    coordinator: TeddyCloudRuntimeCoordinator = hass.data[DOMAIN][entry.entry_id]
    boxes = configured_boxes(entry)
    entities: list[TeddyCloudRuntimeSensor] = [
        TeddyCloudRuntimeSensor(coordinator, entry, description)
        for description in SENSORS
        if description.key not in CURRENT_SENSOR_KEYS
    ]
    for index, box in enumerate(boxes):
        entities.extend(
            TeddyCloudRuntimeSensor(
                coordinator,
                entry,
                description,
                box=box,
                primary=index == 0,
            )
            for description in SENSORS
            if description.key in CURRENT_SENSOR_KEYS
        )
    async_add_entities(entities)


class TeddyCloudRuntimeSensor(
    CoordinatorEntity[TeddyCloudRuntimeCoordinator], SensorEntity
):
    """A sensor backed by TeddyCloud and current Toniebox entities."""

    entity_description: TeddyCloudSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TeddyCloudRuntimeCoordinator,
        entry: ConfigEntry,
        description: TeddyCloudSensorDescription,
        box: dict[str, str] | None = None,
        primary: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.box = box
        self.entity_description = description
        # Preserve the unique IDs of the original single-box sensors.
        if box is not None and primary:
            self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        elif box is not None:
            self._attr_unique_id = (
                f"{entry.entry_id}_{box[CONF_BOX_ID]}_{description.key}"
            )
        else:
            self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        if box is not None:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_{box[CONF_BOX_ID]}")},
                name=f"{box[CONF_BOX_NAME]} – TeddyCloud",
                manufacturer="Toniebox",
                model="TeddyCloud playback source",
                configuration_url=entry.data["host"],
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                name="TeddyCloud Runtime",
                manufacturer="TeddyCloud",
                model="Runtime library",
                configuration_url=entry.data["host"],
            )

    def _source_entity(self, key: str) -> str | None:
        """Return one configured source entity for this box."""
        if self.box is None:
            return None
        return self.box[key]

    @property
    def audio_id(self) -> str | None:
        """Return the normalized current audio ID."""
        entity_id = self._source_entity(CONF_AUDIO_ID_ENTITY)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in {"unknown", "unavailable"}:
            if self.box is None:
                return None
            return self.coordinator.playback.snapshot(
                self.box[CONF_BOX_ID]
            ).get("audio_id")
        if state.state == "":
            return None
        return state.state

    @property
    def ruid(self) -> str | None:
        """Convert the Tonie UID entity state into TeddyCloud RUID form."""
        entity_id = self._source_entity(CONF_TAG_ENTITY)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in {"unknown", "unavailable"}:
            if self.box is None:
                return None
            return self.coordinator.playback.snapshot(
                self.box[CONF_BOX_ID]
            ).get("ruid")
        if state.state == "":
            return None
        compact = "".join(character for character in state.state if character.isalnum())
        if len(compact) != 16:
            return None
        try:
            raw = bytes.fromhex(compact)
        except ValueError:
            return None
        return raw[::-1].hex()

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        return self.entity_description.value_fn(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose useful immutable metadata on the episode sensor."""
        if self.entity_description.key != "episode":
            return None
        metadata = _metadata(self)
        if metadata is None:
            return None
        playback_entity = self._source_entity(CONF_PLAYBACK_ENTITY)
        playback = self.hass.states.get(playback_entity) if playback_entity else None
        return {
            "model": metadata.model,
            "hashes": list(metadata.hashes),
            "picture": metadata.picture,
            "box": self.box[CONF_BOX_NAME] if self.box else None,
            "box_id": self.box[CONF_BOX_ID] if self.box else None,
            "source_audio_id_entity": self._source_entity(CONF_AUDIO_ID_ENTITY),
            "source_playback_entity": playback_entity,
            "source_tag_entity": self._source_entity(CONF_TAG_ENTITY),
            "playback": playback.state if playback else None,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to both coordinator and source-entity changes."""
        await super().async_added_to_hass()
        if self.box is None:
            return
        self.async_on_remove(
            self.coordinator.playback.async_add_listener(self.async_write_ha_state)
        )

        @callback
        def source_changed(event: Event) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [
                    self.box[CONF_AUDIO_ID_ENTITY],
                    self.box[CONF_PLAYBACK_ENTITY],
                    self.box[CONF_TAG_ENTITY],
                ],
                source_changed,
            )
        )
