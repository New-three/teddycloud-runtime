"""Configuration flow for TeddyCloud Runtime."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .api import TeddyCloudClient, TeddyCloudError
from .boxes import configured_boxes, unique_box_id
from .const import (
    CONF_AUDIO_ID_ENTITY,
    CONF_BOXES,
    CONF_BOX_ID,
    CONF_BOX_NAME,
    CONF_PLAYBACK_ENTITY,
    CONF_RULE_ID,
    CONF_RULE_NAME,
    CONF_RULES,
    CONF_SERIES,
    CONF_TAG_ENTITY,
    CONF_TONIE_UID,
    DEFAULT_AUDIO_ID_ENTITY,
    DEFAULT_HOST,
    DEFAULT_PLAYBACK_ENTITY,
    DEFAULT_TAG_ENTITY,
    DOMAIN,
)
from .rules import (
    configured_rules,
    normalize_uid,
    stored_rules,
    uid_to_ruid,
    unique_rule_id,
)


class TeddyCloudRuntimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a TeddyCloud Runtime config flow."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TeddyCloudRuntimeOptionsFlow:
        """Return the multi-box options flow."""
        return TeddyCloudRuntimeOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single TeddyCloud config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).rstrip("/")
            client = TeddyCloudClient(async_get_clientsession(self.hass), host)
            try:
                await client.async_get_tag_index()
                await client.async_get_custom_metadata()
            except TeddyCloudError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(host.lower())
                self._abort_if_unique_id_configured()
                user_input[CONF_HOST] = host
                return self.async_create_entry(title="TeddyCloud", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=(user_input or {}).get(CONF_HOST, DEFAULT_HOST),
                ): str,
                vol.Required(
                    CONF_AUDIO_ID_ENTITY,
                    default=(user_input or {}).get(
                        CONF_AUDIO_ID_ENTITY, DEFAULT_AUDIO_ID_ENTITY
                    ),
                ): str,
                vol.Required(
                    CONF_PLAYBACK_ENTITY,
                    default=(user_input or {}).get(
                        CONF_PLAYBACK_ENTITY, DEFAULT_PLAYBACK_ENTITY
                    ),
                ): str,
                vol.Required(
                    CONF_TAG_ENTITY,
                    default=(user_input or {}).get(
                        CONF_TAG_ENTITY, DEFAULT_TAG_ENTITY
                    ),
                ): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class TeddyCloudRuntimeOptionsFlow(config_entries.OptionsFlowWithReload):
    """Add, edit, and remove Toniebox entity groups."""

    def __init__(self) -> None:
        self._selected_box_id: str | None = None
        self._selected_rule_id: str | None = None

    @property
    def boxes(self) -> list[dict[str, str]]:
        """Return a safe copy of all configured boxes."""
        return [dict(box) for box in configured_boxes(self.config_entry)]

    @property
    def rules(self) -> list[dict[str, str]]:
        """Return a safe copy of all configured Custom Tonie rules."""
        return [dict(rule) for rule in configured_rules(self.config_entry)]

    def _save(
        self,
        *,
        boxes: list[dict[str, str]] | None = None,
        rules: list[dict[str, str]] | None = None,
    ) -> ConfigFlowResult:
        """Save both option groups so editing one never discards the other."""
        return self.async_create_entry(
            data={
                CONF_BOXES: boxes if boxes is not None else self.boxes,
                # A box-only change must never normalize, filter, or erase rules.
                CONF_RULES: (
                    rules
                    if rules is not None
                    else stored_rules(self.config_entry)
                ),
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show box management actions."""
        menu = ["add_box", "edit_box", "add_rule", "edit_rule"]
        if len(self.boxes) > 1:
            menu.append("remove_box")
        if self.rules:
            menu.append("remove_rule")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_box(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add another Toniebox."""
        boxes = self.boxes
        errors: dict[str, str] = {}
        if user_input is not None:
            if _entities_already_used(user_input, boxes):
                errors["base"] = "entities_already_used"
            else:
                box = dict(user_input)
                box[CONF_BOX_ID] = unique_box_id(
                    str(user_input[CONF_BOX_NAME]), boxes
                )
                boxes.append(box)
                return self._save(boxes=boxes)
        return self.async_show_form(
            step_id="add_box",
            data_schema=_box_schema(user_input),
            errors=errors,
        )

    async def async_step_edit_box(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a box to edit."""
        if user_input is not None:
            self._selected_box_id = str(user_input[CONF_BOX_ID])
            return await self.async_step_edit_box_form()
        return self.async_show_form(
            step_id="edit_box",
            data_schema=_box_choice_schema(self.boxes),
        )

    async def async_step_edit_box_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one Toniebox."""
        boxes = self.boxes
        selected = next(
            box for box in boxes if box[CONF_BOX_ID] == self._selected_box_id
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            other_boxes = [
                box for box in boxes if box[CONF_BOX_ID] != self._selected_box_id
            ]
            if _entities_already_used(user_input, other_boxes):
                errors["base"] = "entities_already_used"
            else:
                updated = dict(user_input)
                updated[CONF_BOX_ID] = selected[CONF_BOX_ID]
                boxes = [
                    updated if box[CONF_BOX_ID] == selected[CONF_BOX_ID] else box
                    for box in boxes
                ]
                return self._save(boxes=boxes)
        return self.async_show_form(
            step_id="edit_box_form",
            data_schema=_box_schema(user_input or selected),
            errors=errors,
        )

    async def async_step_remove_box(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one Toniebox configuration."""
        boxes = self.boxes
        if user_input is not None:
            selected = str(user_input[CONF_BOX_ID])
            return self._save(
                boxes=[box for box in boxes if box[CONF_BOX_ID] != selected]
            )
        return self.async_show_form(
            step_id="remove_box",
            data_schema=_box_choice_schema(boxes),
        )

    async def async_step_add_rule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a Custom Tonie rotation rule."""
        rules = self.rules
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_rule(user_input, rules)
            if not errors:
                rule = dict(user_input)
                rule[CONF_TONIE_UID] = normalize_uid(rule[CONF_TONIE_UID])
                rule[CONF_RULE_ID] = unique_rule_id(rule[CONF_RULE_NAME], rules)
                rules.append(rule)
                return self._save(rules=rules)
        return self.async_show_form(
            step_id="add_rule",
            data_schema=_rule_schema(user_input),
            errors=errors,
        )

    async def async_step_edit_rule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a Custom Tonie rule to edit."""
        if user_input is not None:
            self._selected_rule_id = str(user_input[CONF_RULE_ID])
            return await self.async_step_edit_rule_form()
        return self.async_show_form(
            step_id="edit_rule",
            data_schema=_rule_choice_schema(self.rules),
        )

    async def async_step_edit_rule_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one Custom Tonie rotation rule."""
        rules = self.rules
        selected = next(
            rule
            for rule in rules
            if rule[CONF_RULE_ID] == self._selected_rule_id
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            other_rules = [
                rule
                for rule in rules
                if rule[CONF_RULE_ID] != self._selected_rule_id
            ]
            errors = _validate_rule(user_input, other_rules)
            if not errors:
                updated = dict(user_input)
                updated[CONF_TONIE_UID] = normalize_uid(updated[CONF_TONIE_UID])
                updated[CONF_RULE_ID] = selected[CONF_RULE_ID]
                rules = [
                    updated
                    if rule[CONF_RULE_ID] == selected[CONF_RULE_ID]
                    else rule
                    for rule in rules
                ]
                return self._save(rules=rules)
        return self.async_show_form(
            step_id="edit_rule_form",
            data_schema=_rule_schema(user_input or selected),
            errors=errors,
        )

    async def async_step_remove_rule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove one Custom Tonie rotation rule."""
        rules = self.rules
        if user_input is not None:
            selected = str(user_input[CONF_RULE_ID])
            return self._save(
                rules=[
                    rule for rule in rules if rule[CONF_RULE_ID] != selected
                ]
            )
        return self.async_show_form(
            step_id="remove_rule",
            data_schema=_rule_choice_schema(rules),
        )


def _box_schema(values: dict[str, Any] | None = None) -> vol.Schema:
    """Return a Toniebox form with entity pickers."""
    values = values or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BOX_NAME,
                description={"suggested_value": values.get(CONF_BOX_NAME)},
            ): TextSelector(),
            vol.Required(
                CONF_AUDIO_ID_ENTITY,
                description={
                    "suggested_value": values.get(CONF_AUDIO_ID_ENTITY)
                },
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_PLAYBACK_ENTITY,
                description={
                    "suggested_value": values.get(CONF_PLAYBACK_ENTITY)
                },
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_TAG_ENTITY,
                description={"suggested_value": values.get(CONF_TAG_ENTITY)},
            ): EntitySelector(EntitySelectorConfig(domain="sensor")),
        }
    )


def _box_choice_schema(boxes: list[dict[str, str]]) -> vol.Schema:
    """Return a selector containing all configured boxes."""
    options = [
        SelectOptionDict(value=box[CONF_BOX_ID], label=box[CONF_BOX_NAME])
        for box in boxes
    ]
    return vol.Schema(
        {
            vol.Required(CONF_BOX_ID): SelectSelector(
                SelectSelectorConfig(options=options)
            )
        }
    )


def _entities_already_used(
    candidate: dict[str, Any], boxes: list[dict[str, str]]
) -> bool:
    """Reject entity groups overlapping another configured box."""
    candidate_entities = {
        str(candidate[key])
        for key in (
            CONF_AUDIO_ID_ENTITY,
            CONF_PLAYBACK_ENTITY,
            CONF_TAG_ENTITY,
        )
    }
    return any(
        candidate_entities
        & {
            box[CONF_AUDIO_ID_ENTITY],
            box[CONF_PLAYBACK_ENTITY],
            box[CONF_TAG_ENTITY],
        }
        for box in boxes
    )


def _rule_schema(values: dict[str, Any] | None = None) -> vol.Schema:
    """Return the editable Custom Tonie rule form."""
    values = values or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_RULE_NAME,
                description={"suggested_value": values.get(CONF_RULE_NAME)},
            ): TextSelector(),
            vol.Required(
                CONF_TONIE_UID,
                description={"suggested_value": values.get(CONF_TONIE_UID)},
            ): TextSelector(),
            vol.Required(
                CONF_SERIES,
                description={"suggested_value": values.get(CONF_SERIES)},
            ): TextSelector(),
        }
    )


def _rule_choice_schema(rules: list[dict[str, str]]) -> vol.Schema:
    """Return a selector containing all Custom Tonie rules."""
    options = [
        SelectOptionDict(
            value=rule[CONF_RULE_ID],
            label=f"{rule[CONF_RULE_NAME]} – {rule[CONF_SERIES]}",
        )
        for rule in rules
    ]
    return vol.Schema(
        {
            vol.Required(CONF_RULE_ID): SelectSelector(
                SelectSelectorConfig(options=options)
            )
        }
    )


def _validate_rule(
    candidate: dict[str, Any], rules: list[dict[str, str]]
) -> dict[str, str]:
    """Validate UID syntax and enforce one rule per physical Custom Tonie."""
    ruid = uid_to_ruid(str(candidate.get(CONF_TONIE_UID, "")))
    if ruid is None:
        return {"base": "invalid_uid"}
    if any(uid_to_ruid(rule[CONF_TONIE_UID]) == ruid for rule in rules):
        return {"base": "uid_already_used"}
    if not str(candidate.get(CONF_SERIES, "")).strip():
        return {"base": "series_required"}
    return {}
