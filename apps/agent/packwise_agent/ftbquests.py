from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping

from .snbt import parse_snbt


def inspect_quest_book(path: str | Path) -> Dict[str, Any]:
    quests_root = _resolve_quests_root(Path(path))
    data = _read_snbt_file(quests_root / "data.snbt")
    chapters = [_chapter_summary(path) for path in sorted((quests_root / "chapters").glob("*.snbt"))]

    task_types: Counter[str] = Counter()
    reward_types: Counter[str] = Counter()
    stage_names: set[str] = set()
    dependency_edges = 0
    quest_count = 0
    task_count = 0
    reward_count = 0

    for chapter in chapters:
        quest_count += chapter["quest_count"]
        task_count += chapter["task_count"]
        reward_count += chapter["reward_count"]
        dependency_edges += chapter["dependency_edge_count"]
        for quest in chapter["quests"]:
            for task in quest["tasks"]:
                if task.get("type"):
                    task_types[str(task["type"])] += 1
                if task.get("stage"):
                    stage_names.add(str(task["stage"]))
            for reward in quest["rewards"]:
                if reward.get("type"):
                    reward_types[str(reward["type"])] += 1
                if reward.get("stage"):
                    stage_names.add(str(reward["stage"]))

    return {
        "schema_version": "packwise.ftbquests.v1",
        "path": str(quests_root),
        "settings": {
            "version": data.get("version"),
            "progression_mode": data.get("progression_mode"),
            "default_quest_shape": data.get("default_quest_shape"),
        },
        "counts": {
            "chapters": len(chapters),
            "quests": quest_count,
            "tasks": task_count,
            "rewards": reward_count,
            "dependency_edges": dependency_edges,
            "unique_stages": len(stage_names),
        },
        "task_types": _counter_to_dict(task_types),
        "reward_types": _counter_to_dict(reward_types),
        "stages": sorted(stage_names),
        "chapters": chapters,
    }


def _resolve_quests_root(path: Path) -> Path:
    if (path / "config" / "ftbquests" / "quests").is_dir():
        return path / "config" / "ftbquests" / "quests"
    if (path / "chapters").is_dir():
        return path
    raise ValueError(f"Could not find FTB Quests root under {path}")


def _chapter_summary(path: Path) -> Dict[str, Any]:
    payload = _read_snbt_file(path)
    quests = [_quest_summary(quest) for quest in _list_of_dicts(payload.get("quests"))]
    return {
        "id": _string(payload.get("id")),
        "filename": _string(payload.get("filename")) or path.stem,
        "group": _string(payload.get("group")),
        "order_index": payload.get("order_index"),
        "icon": _icon_id(payload.get("icon")),
        "source_file": str(Path("chapters") / path.name),
        "quest_count": len(quests),
        "task_count": sum(len(quest["tasks"]) for quest in quests),
        "reward_count": sum(len(quest["rewards"]) for quest in quests),
        "dependency_edge_count": sum(len(quest["dependencies"]) for quest in quests),
        "quests": quests,
    }


def _quest_summary(payload: Mapping[str, Any]) -> Dict[str, Any]:
    tasks = [_entry_summary(task) for task in _list_of_dicts(payload.get("tasks"))]
    rewards = [_entry_summary(reward) for reward in _list_of_dicts(payload.get("rewards"))]
    dependencies = [_string(value) for value in _list(payload.get("dependencies")) if _string(value)]
    return {
        "id": _string(payload.get("id")),
        "title": _string(payload.get("title")),
        "subtitle": _string(payload.get("subtitle")),
        "icon": _icon_id(payload.get("icon")),
        "x": payload.get("x"),
        "y": payload.get("y"),
        "shape": _string(payload.get("shape")),
        "dependencies": dependencies,
        "min_required_dependencies": payload.get("min_required_dependencies"),
        "hide_until_deps_complete": payload.get("hide_until_deps_complete"),
        "tasks": tasks,
        "rewards": rewards,
    }


def _entry_summary(payload: Mapping[str, Any]) -> Dict[str, Any]:
    item = payload.get("item")
    fluid = payload.get("fluid")
    result: Dict[str, Any] = {
        "id": _string(payload.get("id")),
        "type": _string(payload.get("type")),
    }
    _copy_if_present(result, payload, "amount")
    _copy_if_present(result, payload, "count")
    _copy_if_present(result, payload, "stage")
    _copy_if_present(result, payload, "team_stage")
    _copy_if_present(result, payload, "team_reward")
    _copy_if_present(result, payload, "dimension")
    _copy_if_present(result, payload, "biome")
    _copy_if_present(result, payload, "entity")
    _copy_if_present(result, payload, "advancement")
    _copy_if_present(result, payload, "table_id")
    if isinstance(item, Mapping):
        result["item_id"] = _string(item.get("id"))
        if "count" in item:
            result["item_count"] = item["count"]
    if isinstance(fluid, Mapping):
        result["fluid_id"] = _string(fluid.get("id"))
        if "amount" in fluid:
            result["fluid_amount"] = fluid["amount"]
    return {key: value for key, value in result.items() if value is not None}


def _read_snbt_file(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        return {}
    payload = parse_snbt(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected compound in {path}")
    return payload


def _icon_id(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    components = value.get("components")
    if isinstance(components, Mapping):
        component_icon = _string(components.get("ftbquests:icon"))
        if component_icon:
            return component_icon
    return _string(value.get("id"))


def _list_of_dicts(value: Any) -> list[Mapping[str, Any]]:
    return [entry for entry in _list(value) if isinstance(entry, Mapping)]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _copy_if_present(target: Dict[str, Any], source: Mapping[str, Any], key: str) -> None:
    if key in source:
        target[key] = source[key]


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _counter_to_dict(counter: Counter[str]) -> Dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}
