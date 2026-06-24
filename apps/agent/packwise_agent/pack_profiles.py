from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


PROFILE_SCHEMA_VERSION = "packwise.pack_profile.v1"


@dataclass(frozen=True)
class PackProfile:
    profile_id: str
    display_name: str
    match: Mapping[str, Any]
    adapter: Mapping[str, Any]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PackProfile":
        schema_version = payload.get("schema_version")
        if schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError(f"Expected {PROFILE_SCHEMA_VERSION}, got {schema_version}")
        match = payload.get("match")
        adapter = payload.get("adapter")
        if not isinstance(match, Mapping):
            raise ValueError("profile match must be an object")
        if not isinstance(adapter, Mapping):
            raise ValueError("profile adapter must be an object")
        return cls(
            profile_id=_require_str(payload, "profile_id"),
            display_name=_require_str(payload, "display_name"),
            match=dict(match),
            adapter=dict(adapter),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "match": dict(self.match),
            "adapter": dict(self.adapter),
        }


def load_pack_profiles(path: str | Path | None = None) -> List[PackProfile]:
    profiles_dir = Path(path) if path is not None else Path(__file__).with_name("pack_profiles")
    profiles = []
    for profile_path in sorted(profiles_dir.glob("*.json")):
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"Expected JSON object in {profile_path}")
        profiles.append(PackProfile.from_dict(payload))
    return profiles


def select_pack_profile(
    static_summary: Mapping[str, Any],
    profiles: Optional[List[PackProfile]] = None,
) -> PackProfile:
    candidates = profiles if profiles is not None else load_pack_profiles()
    if not candidates:
        raise ValueError("No pack profiles are available")
    scored = sorted(
        ((_score_profile(profile, static_summary), profile) for profile in candidates),
        key=lambda item: (item[0], item[1].profile_id),
        reverse=True,
    )
    score, profile = scored[0]
    if score <= 0:
        raise ValueError("No pack profile matched the static summary")
    return profile


def _score_profile(profile: PackProfile, static_summary: Mapping[str, Any]) -> int:
    adapter = _mapping(static_summary.get("adapter"))
    pack = _mapping(static_summary.get("pack"))
    loader = _mapping(static_summary.get("loader"))
    pack_id = (_string(adapter.get("pack_id")) or "").lower()
    pack_name = (_string(pack.get("name")) or "").lower()
    loader_name = (_string(loader.get("name")) or _string(adapter.get("loader")) or "").lower()
    minecraft_version = _string(loader.get("minecraft_version")) or _string(adapter.get("minecraft_version"))

    match = profile.match
    score = 0
    pack_ids = [item.lower() for item in _string_list(match.get("pack_ids"))]
    if pack_id and pack_id in pack_ids:
        score += 100
    name_terms = _string_list(match.get("name_contains"))
    if name_terms and all(term.lower() in pack_name for term in name_terms):
        score += 40
    expected_loader = (_string(match.get("loader")) or "").lower()
    if expected_loader and expected_loader == loader_name:
        score += 10
    elif expected_loader:
        return 0
    versions = _string_list(match.get("minecraft_versions"))
    if versions and minecraft_version in versions:
        score += 10
    elif versions:
        return 0
    return score


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
