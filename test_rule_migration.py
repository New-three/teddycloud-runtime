"""Standalone regression tests for Custom-Tonie rule migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import types


def module(name: str, **attributes: object) -> types.ModuleType:
    result = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    sys.modules[name] = result
    return result


class ConfigEntry:
    def __init__(
        self,
        *,
        data: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> None:
        self.data = data or {}
        self.options = options or {}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


module("homeassistant")
module("homeassistant.config_entries", ConfigEntry=ConfigEntry)
module("homeassistant.util", slugify=slugify)

root = Path("custom_components/teddycloud_runtime").resolve()
package = module("teddycloud_runtime")
package.__path__ = [str(root)]

for name in ("const", "rules"):
    spec = importlib.util.spec_from_file_location(
        f"teddycloud_runtime.{name}", root / f"{name}.py"
    )
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)

rules = sys.modules["teddycloud_runtime.rules"]

legacy = {
    "rule_name": "Beispielregel",
    "tonie_uid": "01 23 45 67 89 AB CD EF",
    "series": "Beispielserie",
}
entry = ConfigEntry(options={"rules": [legacy]})
migrated = rules.configured_rules(entry)
assert len(migrated) == 1
assert migrated[0]["rule_id"] == "beispielregel"
assert migrated[0]["tonie_uid"] == "01:23:45:67:89:AB:CD:EF"

# Rules from the old config-entry data location are still recovered.
data_entry = ConfigEntry(data={"rules": [legacy]})
assert rules.configured_rules(data_entry)[0]["rule_id"] == "beispielregel"

# Malformed legacy records remain stored instead of disappearing during a
# box-only options change. They can therefore be repaired by a later flow.
malformed = {"rule_name": "Unvollständig", "tonie_uid": "invalid"}
malformed_entry = ConfigEntry(options={"rules": [malformed]})
assert rules.stored_rules(malformed_entry) == [malformed]
assert rules.migrate_rules(rules.stored_rules(malformed_entry)) == [malformed]
assert rules.configured_rules(malformed_entry) == []

# Returned raw records are deep copies and cannot mutate Home Assistant data.
copy = rules.stored_rules(entry)
copy[0]["series"] = "Geändert"
assert entry.options["rules"][0]["series"] == "Beispielserie"

print("Rule migration and lossless preservation: OK")
