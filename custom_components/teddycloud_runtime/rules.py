"""Configurable Custom Tonie rotation rules."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import slugify

from .const import (
    CONF_RULE_ID,
    CONF_RULE_NAME,
    CONF_RULES,
    CONF_SERIES,
    CONF_TONIE_UID,
)

DEFAULT_RULES: tuple[dict[str, str], ...] = ()


def configured_rules(entry: ConfigEntry) -> list[dict[str, str]]:
    """Return configured rules or an empty initial rule set."""
    raw_rules = entry.options.get(CONF_RULES)
    if not isinstance(raw_rules, list):
        raw_rules = DEFAULT_RULES
    return [
        {
            CONF_RULE_ID: str(rule[CONF_RULE_ID]),
            CONF_RULE_NAME: str(rule[CONF_RULE_NAME]),
            CONF_TONIE_UID: normalize_uid(str(rule[CONF_TONIE_UID])),
            CONF_SERIES: str(rule[CONF_SERIES]).strip(),
        }
        for rule in raw_rules
        if isinstance(rule, dict)
        and all(
            key in rule
            for key in (
                CONF_RULE_ID,
                CONF_RULE_NAME,
                CONF_TONIE_UID,
                CONF_SERIES,
            )
        )
    ]


def normalize_uid(value: str) -> str:
    """Normalize a displayed Tonie UID to colon-separated uppercase bytes."""
    compact = "".join(character for character in value if character.isalnum())
    return ":".join(
        compact[index : index + 2].upper() for index in range(0, len(compact), 2)
    )


def uid_to_ruid(value: str) -> str | None:
    """Convert the box UID byte order to TeddyCloud RUID byte order."""
    compact = "".join(character for character in value if character.isalnum())
    if len(compact) != 16:
        return None
    try:
        return bytes.fromhex(compact)[::-1].hex()
    except ValueError:
        return None


def unique_rule_id(name: str, rules: list[dict[str, Any]]) -> str:
    """Create a stable rule ID."""
    base = slugify(name) or "custom_tonie"
    used = {str(rule.get(CONF_RULE_ID)) for rule in rules}
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate
