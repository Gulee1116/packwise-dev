from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .ftbquests import inspect_quest_book
from .pack_profiles import PackProfile, select_pack_profile
from .runtime_index import RuntimePackIndex
from .static_inspector import inspect_instance


INDEX_SCHEMA_VERSION = "packwise.index.v1"
PHASE1_RUNTIME_SECTIONS = ("mods", "items", "blocks", "fluids", "tags", "recipes", "advancements")
POTION_EFFECT_RUNTIME_SECTIONS = ("potions", "mob_effects")
OPTIONAL_RUNTIME_SECTIONS = ("ftb_quests", "player_progress", "team_progress", "stages")
SEMANTIC_RUNTIME_SECTIONS = POTION_EFFECT_RUNTIME_SECTIONS + OPTIONAL_RUNTIME_SECTIONS
RUNTIME_SECTIONS = PHASE1_RUNTIME_SECTIONS + SEMANTIC_RUNTIME_SECTIONS


@dataclass(frozen=True)
class PackwiseIndex:
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.payload)


def build_packwise_index(
    static_summary: Mapping[str, Any],
    runtime_index: RuntimePackIndex,
    quest_summary: Optional[Mapping[str, Any]] = None,
    profile: Optional[PackProfile] = None,
) -> PackwiseIndex:
    selected_profile = profile or select_pack_profile(static_summary)
    adapter = _mapping(static_summary.get("adapter"))
    pack = _mapping(static_summary.get("pack"))
    loader = _mapping(static_summary.get("loader"))
    runtime_summary = runtime_index.summary()
    quest_counts = _mapping(quest_summary.get("counts")) if quest_summary else {}

    payload: Dict[str, Any] = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "profile": {
            "profile_id": selected_profile.profile_id,
            "display_name": selected_profile.display_name,
            "adapter": dict(selected_profile.adapter),
        },
        "identity": {
            "pack_id": adapter.get("pack_id"),
            "pack_name": pack.get("name"),
            "pack_version": pack.get("version"),
            "loader": loader.get("name") or adapter.get("loader"),
            "minecraft_version": loader.get("minecraft_version") or adapter.get("minecraft_version"),
            "loader_version": loader.get("version"),
        },
        "source_policy": {
            "runtime_truth_authoritative": True,
            "static_sources_are_preload_only": True,
            "reconciliation": _reconciliation(runtime_summary, quest_summary),
        },
        "static_sources": {
            "source_inventory": adapter.get("source_inventory", {}),
            "counts": static_summary.get("counts", {}),
            "optional_integrations": adapter.get("optional_integrations", {}),
            "known_progression_sources": adapter.get("known_progression_sources", []),
        },
        "runtime": {
            "counts": runtime_summary,
            "available_sections": [name for name, count in runtime_summary.items() if count > 0],
            "missing_phase1_sections": [name for name in PHASE1_RUNTIME_SECTIONS if runtime_summary.get(name, 0) == 0],
        },
        "quests": {
            "source": "static:ftbquests" if quest_summary else None,
            "counts": dict(quest_counts),
            "stages": list(quest_summary.get("stages", [])) if quest_summary else [],
        },
        "answer_readiness": _answer_readiness(runtime_summary, quest_summary),
    }
    return PackwiseIndex(payload)


def build_packwise_index_from_instance(
    instance_path: str | Path,
    runtime_sections: Optional[Mapping[str, str]] = None,
) -> PackwiseIndex:
    static_summary = inspect_instance(instance_path)
    runtime_index = runtime_index_from_sections(runtime_sections or {})
    quest_summary = _try_inspect_quests(instance_path, static_summary)
    return build_packwise_index(static_summary, runtime_index, quest_summary)


def runtime_index_from_sections(sections: Mapping[str, str]) -> RuntimePackIndex:
    index = RuntimePackIndex.empty()
    for section_name in RUNTIME_SECTIONS:
        body = sections.get(section_name)
        if body is not None:
            index = index.with_section(section_name, body)
    return index


def _try_inspect_quests(instance_path: str | Path, static_summary: Mapping[str, Any]) -> Mapping[str, Any] | None:
    adapter = _mapping(static_summary.get("adapter"))
    optional = _mapping(adapter.get("optional_integrations"))
    ftb_quests = _mapping(optional.get("ftb_quests"))
    if not ftb_quests.get("present"):
        return None
    try:
        return inspect_quest_book(instance_path)
    except ValueError:
        return None


def _reconciliation(runtime_summary: Mapping[str, int], quest_summary: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    return {
        "registries": "runtime_authoritative" if _registries_ready(runtime_summary) else "missing_runtime",
        "tags": "runtime_authoritative" if runtime_summary.get("tags", 0) else "missing_runtime",
        "recipes": "runtime_authoritative" if runtime_summary.get("recipes", 0) else "missing_runtime",
        "potions": "runtime_authoritative" if runtime_summary.get("potions", 0) else "missing_runtime",
        "mob_effects": "runtime_authoritative" if runtime_summary.get("mob_effects", 0) else "missing_runtime",
        "advancements": "runtime_authoritative" if runtime_summary.get("advancements", 0) else "missing_runtime",
        "quests": _quest_reconciliation(runtime_summary, quest_summary),
        "player_progress": "runtime_authoritative" if runtime_summary.get("player_progress", 0) else "missing_runtime",
        "team_progress": "runtime_authoritative" if runtime_summary.get("team_progress", 0) else "missing_runtime",
        "stages": _stage_reconciliation(runtime_summary, quest_summary),
    }


def _registries_ready(runtime_summary: Mapping[str, int]) -> bool:
    return all(runtime_summary.get(name, 0) for name in ("items", "blocks", "fluids"))


def _answer_readiness(runtime_summary: Mapping[str, int], quest_summary: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "recipe_questions": runtime_summary.get("recipes", 0) > 0 and runtime_summary.get("items", 0) > 0,
        "jei_difference_questions": runtime_summary.get("recipes", 0) > 0 and runtime_summary.get("tags", 0) > 0,
        "effect_route_questions": all(
            runtime_summary.get(name, 0) > 0 for name in ("recipes", "potions", "mob_effects")
        ),
        "next_step_questions": _progression_readiness(runtime_summary, quest_summary),
        "unlock_questions": _unlock_readiness(runtime_summary, quest_summary),
        "blocker_questions": "partial" if _has_progress_state(runtime_summary) else "needs_player_team_progress",
        "missing_for_full_progression": _missing_for_full_progression(runtime_summary, quest_summary),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _quest_reconciliation(runtime_summary: Mapping[str, int], quest_summary: Optional[Mapping[str, Any]]) -> str:
    if runtime_summary.get("ftb_quests", 0):
        return "runtime_authoritative"
    if quest_summary:
        return "static_preload_needs_runtime_progress"
    return "missing_static_and_runtime"


def _stage_reconciliation(runtime_summary: Mapping[str, int], quest_summary: Optional[Mapping[str, Any]]) -> str:
    if runtime_summary.get("stages", 0):
        return "runtime_authoritative"
    if quest_summary and quest_summary.get("stages"):
        return "static_preload_needs_runtime_state"
    return "missing_runtime"


def _has_progress_state(runtime_summary: Mapping[str, int]) -> bool:
    return bool(runtime_summary.get("player_progress", 0) or runtime_summary.get("team_progress", 0) or runtime_summary.get("stages", 0))


def _progression_readiness(runtime_summary: Mapping[str, int], quest_summary: Optional[Mapping[str, Any]]) -> str:
    has_quest_context = bool(runtime_summary.get("ftb_quests", 0) or quest_summary)
    if has_quest_context and _has_progress_state(runtime_summary):
        return "ready"
    if has_quest_context or runtime_summary.get("advancements", 0):
        return "partial"
    return "insufficient"


def _unlock_readiness(runtime_summary: Mapping[str, int], quest_summary: Optional[Mapping[str, Any]]) -> str:
    has_quest_context = bool(runtime_summary.get("ftb_quests", 0) or quest_summary)
    if has_quest_context and (runtime_summary.get("recipes", 0) or _has_progress_state(runtime_summary)):
        return "ready"
    if has_quest_context or runtime_summary.get("advancements", 0):
        return "partial"
    return "insufficient"


def _missing_for_full_progression(runtime_summary: Mapping[str, int], quest_summary: Optional[Mapping[str, Any]]) -> list[str]:
    missing = []
    if not runtime_summary.get("ftb_quests", 0):
        missing.append("ftb_quests_runtime" if quest_summary else "ftb_quests")
    if not runtime_summary.get("player_progress", 0):
        missing.append("player_progress")
    if not runtime_summary.get("team_progress", 0):
        missing.append("team_progress")
    if not runtime_summary.get("stages", 0):
        missing.append("stages")
    return missing
