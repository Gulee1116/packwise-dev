from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


IGNORED_TOP_LEVEL = {
    "cache",
    "crash-reports",
    "dynamic-resource-pack-cache",
    "ftbteambases",
    "local",
    "logs",
    "saves",
    "screenshots",
}


def inspect_instance(path: str | Path) -> Dict[str, Any]:
    root = Path(path)
    if not root.exists():
        raise ValueError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Path is not a directory: {root}")

    setup = _read_pcl_setup(root / "PCL" / "Setup.ini")
    modpack_info = _read_modpack_info(root / "modpackinfo.json")
    version_json = _read_version_json(root)

    return {
        "schema_version": "packwise.static_inspect.v1",
        "path": str(root),
        "instance": {
            "kind": "pcl2_installed_instance" if setup else "directory",
            "version_isolated": _to_bool(setup.get("VersionArgumentIndieV2")),
            "launcher": "PCL2" if setup else None,
        },
        "pack": {
            "name": _first_str(
                _dig(modpack_info, "modpack", "name"),
                version_json.get("id"),
                root.name,
            ),
            "version": _first_str(_dig(modpack_info, "modpack", "version")),
            "translation_language": _first_str(_dig(modpack_info, "modpack", "translation", "language")),
        },
        "loader": {
            "minecraft_version": _first_str(setup.get("VersionVanillaName"), version_json.get("id")),
            "name": "neoforge" if setup.get("VersionNeoForge") else None,
            "version": _first_str(setup.get("VersionNeoForge")),
        },
        "counts": {
            "mod_jars": _count_files(root / "mods", "*.jar"),
            "ftbquests_snbt_files": _count_files(root / "config" / "ftbquests" / "quests", "*.snbt"),
            "ftbquests_chapter_files": _count_files(root / "config" / "ftbquests" / "quests" / "chapters", "*.snbt"),
            "kubejs_js_files": _count_files(root / "kubejs", "*.js"),
            "kubejs_server_js_files": _count_files(root / "kubejs" / "server_scripts", "*.js"),
            "kubejs_recipe_js_files": _count_files(root / "kubejs" / "server_scripts" / "recipes", "*.js"),
            "kubejs_data_json_files": _count_files(root / "kubejs" / "data", "*.json"),
            "datapack_files": _count_files(root / "datapacks", "*"),
            "datapack_recipe_json_files": _count_datapack_recipes(root / "datapacks"),
            "defaultconfig_files": _count_files(root / "defaultconfigs", "*"),
        },
        "safe_samples": {
            "mod_jars": _sample_names(root / "mods", "*.jar", limit=10),
            "quest_chapters": _sample_names(root / "config" / "ftbquests" / "quests" / "chapters", "*.snbt", limit=10),
        },
        "ignored_present": sorted(name for name in IGNORED_TOP_LEVEL if (root / name).exists()),
    }


def _read_pcl_setup(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    result: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def _read_modpack_info(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        return {}
    return _read_json(path)


def _read_version_json(root: Path) -> Mapping[str, Any]:
    candidate = root / f"{root.name}.json"
    if candidate.is_file():
        return _read_json(candidate)
    for path in sorted(root.glob("*.json")):
        if path.name in {"modpackinfo.json", "patchouli_data.json"}:
            continue
        return _read_json(path)
    return {}


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _count_files(root: Path, pattern: str) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob(pattern) if path.is_file())


def _count_datapack_recipes(root: Path) -> int:
    if not root.is_dir():
        return 0
    count = 0
    for path in root.rglob("*.json"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if "data" in parts and ("recipes" in parts or "recipe" in parts):
            count += 1
    return count


def _sample_names(root: Path, pattern: str, limit: int) -> list[str]:
    if not root.is_dir():
        return []
    return [path.name for path in sorted(root.glob(pattern))[:limit] if path.is_file()]


def _dig(payload: Mapping[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _to_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None
