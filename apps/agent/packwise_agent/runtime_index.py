from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping


@dataclass(frozen=True)
class RuntimeMod:
    mod_id: str
    display_name: str
    version: str
    source: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeMod":
        return cls(
            mod_id=_require_str(payload, "mod_id"),
            display_name=_require_str(payload, "display_name"),
            version=_require_str(payload, "version"),
            source=_require_str(payload, "source"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "mod_id": self.mod_id,
            "display_name": self.display_name,
            "version": self.version,
            "source": self.source,
        }


def parse_mods_ndjson(body: str) -> List[RuntimeMod]:
    mods: List[RuntimeMod] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"mods line {line_number} must be a JSON object")
        mods.append(RuntimeMod.from_dict(payload))
    return sorted(mods, key=lambda mod: mod.mod_id)


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value
