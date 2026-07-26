"""Manual playback controls for TeddyCloud Runtime."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .boxes import configured_boxes
from .const import CONF_BOX_ID, CONF_BOX_NAME, DOMAIN
from .coordinator import TeddyCloudRuntimeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one manual next-episode button per configured Toniebox."""
    coordinator: TeddyCloudRuntimeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AssignNextEpisodeButton(coordinator, entry, box)
        for box in configured_boxes(entry)
    )


class AssignNextEpisodeButton(
    CoordinatorEntity[TeddyCloudRuntimeCoordinator], ButtonEntity
):
    """Manually complete the active episode and assign the next one."""

    _attr_has_entity_name = True
    _attr_translation_key = "assign_next_episode"
    _attr_icon = "mdi:skip-next"

    def __init__(
        self,
        coordinator: TeddyCloudRuntimeCoordinator,
        entry: ConfigEntry,
        box: dict[str, str],
    ) -> None:
        super().__init__(coordinator)
        self.box = box
        self._attr_unique_id = (
            f"{entry.entry_id}_{box[CONF_BOX_ID]}_assign_next_episode"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{box[CONF_BOX_ID]}")},
            name=f"{box[CONF_BOX_NAME]} – TeddyCloud",
            manufacturer="Toniebox",
            model="TeddyCloud playback source",
            configuration_url=entry.data["host"],
        )

    @property
    def available(self) -> bool:
        """Return whether a live or restored session can be completed."""
        return (
            self.coordinator.playback.snapshot(
                self.box[CONF_BOX_ID]
            ).get("audio_id")
            is not None
        )

    async def async_press(self) -> None:
        """Assign the next random episode to this Custom Tonie."""
        await self.coordinator.playback.async_mark_complete(
            self.box[CONF_BOX_ID]
        )

    async def async_added_to_hass(self) -> None:
        """Update availability when the playback session changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.playback.async_add_listener(
                self.async_write_ha_state
            )
        )
