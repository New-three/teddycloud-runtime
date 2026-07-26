"""Helpers for configuring multiple Tonieboxes."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import slugify

from .const import (
    CONF_AUDIO_ID_ENTITY,
    CONF_BOXES,
    CONF_BOX_ID,
    CONF_BOX_NAME,
    CONF_PLAYBACK_ENTITY,
    CONF_TAG_ENTITY,
)


def configured_boxes(entry: ConfigEntry) -> list[dict[str, str]]:
    """Return configured boxes, migrating the original single box in memory."""
    boxes = entry.options.get(CONF_BOXES)
    if isinstance(boxes, list) and boxes:
        return [
            {
                CONF_BOX_ID: str(box[CONF_BOX_ID]),
                CONF_BOX_NAME: str(box[CONF_BOX_NAME]),
                CONF_AUDIO_ID_ENTITY: str(box[CONF_AUDIO_ID_ENTITY]),
                CONF_PLAYBACK_ENTITY: str(box[CONF_PLAYBACK_ENTITY]),
                CONF_TAG_ENTITY: str(box[CONF_TAG_ENTITY]),
            }
            for box in boxes
            if isinstance(box, dict)
            and all(
                key in box
                for key in (
                    CONF_BOX_ID,
                    CONF_BOX_NAME,
                    CONF_AUDIO_ID_ENTITY,
                    CONF_PLAYBACK_ENTITY,
                    CONF_TAG_ENTITY,
                )
            )
        ]

    audio_entity = str(entry.data[CONF_AUDIO_ID_ENTITY])
    name = _name_from_audio_entity(audio_entity)
    return [
        {
            CONF_BOX_ID: slugify(name) or "box_1",
            CONF_BOX_NAME: name,
            CONF_AUDIO_ID_ENTITY: audio_entity,
            CONF_PLAYBACK_ENTITY: str(entry.data[CONF_PLAYBACK_ENTITY]),
            CONF_TAG_ENTITY: str(entry.data[CONF_TAG_ENTITY]),
        }
    ]


def unique_box_id(name: str, boxes: list[dict[str, Any]]) -> str:
    """Create a stable unique ID for a newly configured box."""
    base = slugify(name) or "toniebox"
    used = {str(box.get(CONF_BOX_ID)) for box in boxes}
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _name_from_audio_entity(entity_id: str) -> str:
    """Derive a friendly initial name from an existing MQTT sensor."""
    object_id = entity_id.split(".", 1)[-1]
    for suffix in ("_content_audio_id", "_audio_id"):
        if object_id.endswith(suffix):
            object_id = object_id[: -len(suffix)]
            break
    return object_id.replace("_", " ").title() or "Toniebox"
