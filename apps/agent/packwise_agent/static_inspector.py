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
    pack_manifest = _read_pack_manifest(root)
    version_json = _read_version_json(root)
    loader = _detect_loader(setup, version_json, pack_manifest, root)
    source_inventory = _source_inventory(root)
    optional_integrations = _optional_integrations(root, source_inventory)
    pack_name = _first_str(
        _dig(modpack_info, "modpack", "name"),
        pack_manifest.get("name"),
        version_json.get("id"),
        root.name,
    )
    minecraft_version = _first_str(
        setup.get("VersionVanillaName"),
        version_json.get("id"),
        loader.get("minecraft_version"),
    )

    return {
        "schema_version": "packwise.static_inspect.v1",
        "path": str(root),
        "instance": {
            "kind": _instance_kind(setup, pack_manifest),
            "version_isolated": _to_bool(setup.get("VersionArgumentIndieV2")),
            "launcher": _launcher(setup, pack_manifest),
        },
        "pack": {
            "name": pack_name,
            "version": _first_str(_dig(modpack_info, "modpack", "version"), pack_manifest.get("version")),
            "translation_language": _first_str(_dig(modpack_info, "modpack", "translation", "language")),
        },
        "loader": {
            "minecraft_version": minecraft_version,
            "name": loader["name"],
            "version": loader["version"],
        },
        "adapter": {
            "pack_id": _slug(
                _first_str(_dig(modpack_info, "modpack", "name"), pack_manifest.get("name"), root.name)
                or "unknown-pack"
            ),
            "loader": loader["name"],
            "minecraft_version": minecraft_version,
            "quest_mod": "ftbquests" if optional_integrations["ftb_quests"]["present"] else None,
            "known_progression_sources": _known_progression_sources(optional_integrations),
            "source_inventory": source_inventory,
            "optional_integrations": optional_integrations,
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


def _read_pack_manifest(root: Path) -> Mapping[str, Any]:
    for filename in ("manifest.json", "modrinth.index.json", "mmc-pack.json"):
        path = root / filename
        if not path.is_file():
            continue
        normalized = _normalize_pack_manifest(filename, _read_json(path))
        if normalized:
            return normalized
    return {}


def _normalize_pack_manifest(filename: str, payload: Mapping[str, Any]) -> Dict[str, str | None]:
    if filename == "manifest.json" and isinstance(payload.get("minecraft"), Mapping):
        minecraft = _mapping(payload.get("minecraft"))
        loader = _curseforge_loader(minecraft)
        return {
            "kind": "curseforge_manifest",
            "launcher": "CurseForge",
            "name": _first_str(payload.get("name")),
            "version": _first_str(payload.get("version")),
            "minecraft_version": _first_str(minecraft.get("version")),
            "loader": loader["name"],
            "loader_version": loader["version"],
        }
    if filename == "modrinth.index.json" and isinstance(payload.get("dependencies"), Mapping):
        dependencies = _mapping(payload.get("dependencies"))
        loader = _modrinth_loader(dependencies)
        return {
            "kind": "modrinth_index",
            "launcher": "Modrinth",
            "name": _first_str(payload.get("name")),
            "version": _first_str(payload.get("versionId")),
            "minecraft_version": _first_str(dependencies.get("minecraft")),
            "loader": loader["name"],
            "loader_version": loader["version"],
        }
    if filename == "mmc-pack.json" and isinstance(payload.get("components"), list):
        components = [item for item in payload.get("components", []) if isinstance(item, Mapping)]
        loader = _mmc_loader(components)
        return {
            "kind": "prism_mmc_instance",
            "launcher": "Prism/MultiMC",
            "name": None,
            "version": None,
            "minecraft_version": _component_version(components, "net.minecraft"),
            "loader": loader["name"],
            "loader_version": loader["version"],
        }
    return {}


def _read_version_json(root: Path) -> Mapping[str, Any]:
    candidate = root / f"{root.name}.json"
    if candidate.is_file():
        return _read_json(candidate)
    for path in sorted(root.glob("*.json")):
        if path.name in {"manifest.json", "mmc-pack.json", "modpackinfo.json", "modrinth.index.json", "patchouli_data.json"}:
            continue
        return _read_json(path)
    return {}


def _detect_loader(
    setup: Mapping[str, str],
    version_json: Mapping[str, Any],
    pack_manifest: Mapping[str, Any],
    root: Path,
) -> Dict[str, str | None]:
    if setup.get("VersionForge"):
        return {
            "name": "forge",
            "version": _first_str(setup.get("VersionForge")),
            "minecraft_version": _first_str(setup.get("VersionVanillaName"), version_json.get("id")),
        }
    if setup.get("VersionNeoForge"):
        return {
            "name": "neoforge",
            "version": _first_str(setup.get("VersionNeoForge")),
            "minecraft_version": _first_str(setup.get("VersionVanillaName"), version_json.get("id")),
        }
    if pack_manifest.get("loader"):
        return {
            "name": _first_str(pack_manifest.get("loader")),
            "version": _first_str(pack_manifest.get("loader_version")),
            "minecraft_version": _first_str(pack_manifest.get("minecraft_version"), version_json.get("id")),
        }
    for library in _version_libraries(version_json):
        name = library.get("name")
        if not isinstance(name, str):
            continue
        if name.startswith("net.minecraftforge:forge:"):
            return _loader_from_maven_name("forge", name, version_json)
        if name.startswith("net.neoforged:neoforge:") or name.startswith("net.neoforged:forge:"):
            return _loader_from_maven_name("neoforge", name, version_json)
    detected_server_loader = _detect_server_loader(root, version_json)
    if detected_server_loader["name"]:
        return detected_server_loader
    return {
        "name": None,
        "version": None,
        "minecraft_version": _first_str(version_json.get("id")),
    }


def _curseforge_loader(minecraft: Mapping[str, Any]) -> Dict[str, str | None]:
    mod_loaders = minecraft.get("modLoaders")
    if not isinstance(mod_loaders, list):
        return {"name": None, "version": None}
    loaders = [loader for loader in mod_loaders if isinstance(loader, Mapping)]
    primary = next((loader for loader in loaders if loader.get("primary") is True), None)
    selected = primary or (loaders[0] if loaders else {})
    return _loader_from_id(_first_str(selected.get("id")))


def _modrinth_loader(dependencies: Mapping[str, Any]) -> Dict[str, str | None]:
    for name, dependency_key in (("forge", "forge"), ("neoforge", "neoforge"), ("fabric", "fabric-loader"), ("quilt", "quilt-loader")):
        version = _first_str(dependencies.get(dependency_key))
        if version:
            return {"name": name, "version": version}
    return {"name": None, "version": None}


def _mmc_loader(components: list[Mapping[str, Any]]) -> Dict[str, str | None]:
    for name, uid in (("forge", "net.minecraftforge"), ("neoforge", "net.neoforged"), ("fabric", "net.fabricmc.fabric-loader"), ("quilt", "org.quiltmc.quilt-loader")):
        version = _component_version(components, uid)
        if version:
            return {"name": name, "version": version}
    return {"name": None, "version": None}


def _component_version(components: list[Mapping[str, Any]], uid: str) -> str | None:
    for component in components:
        if component.get("uid") == uid:
            return _first_str(component.get("version"))
    return None


def _loader_from_id(loader_id: str | None) -> Dict[str, str | None]:
    if not loader_id:
        return {"name": None, "version": None}
    for prefix, name in (
        ("neoforge-", "neoforge"),
        ("forge-", "forge"),
        ("fabric-loader-", "fabric"),
        ("quilt-loader-", "quilt"),
    ):
        if loader_id.startswith(prefix):
            return {"name": name, "version": loader_id.removeprefix(prefix)}
    return {"name": loader_id.split("-", 1)[0], "version": loader_id.split("-", 1)[1] if "-" in loader_id else None}


def _version_libraries(version_json: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    libraries = version_json.get("libraries")
    if not isinstance(libraries, list):
        return []
    return [library for library in libraries if isinstance(library, Mapping)]


def _loader_from_maven_name(loader_name: str, maven_name: str, version_json: Mapping[str, Any]) -> Dict[str, str | None]:
    version = maven_name.rsplit(":", 1)[-1]
    return _loader_from_version_token(loader_name, version, _first_str(version_json.get("id")))


def _loader_from_version_token(
    loader_name: str,
    version: str,
    fallback_minecraft_version: str | None = None,
) -> Dict[str, str | None]:
    if "-" in version:
        minecraft_version = version.split("-", 1)[0]
        loader_version = version.split("-", 1)[1]
    else:
        minecraft_version = fallback_minecraft_version or _infer_minecraft_version_from_loader_version(loader_name, version)
        loader_version = version
    return {
        "name": loader_name,
        "version": loader_version,
        "minecraft_version": minecraft_version,
    }


def _infer_minecraft_version_from_loader_version(loader_name: str, loader_version: str) -> str | None:
    if loader_name != "neoforge":
        return None
    parts = loader_version.split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    major = int(parts[0])
    minor = int(parts[1])
    if major < 20 or major > 30:
        return None
    return f"1.{major}" if minor == 0 else f"1.{major}.{minor}"


def _detect_server_loader(root: Path, version_json: Mapping[str, Any]) -> Dict[str, str | None]:
    minecraft_version = _first_str(version_json.get("id"))
    for loader_name, relative in (
        ("forge", Path("libraries") / "net" / "minecraftforge" / "forge"),
        ("neoforge", Path("libraries") / "net" / "neoforged" / "neoforge"),
        ("neoforge", Path("libraries") / "net" / "neoforged" / "forge"),
    ):
        version = _first_str(*_server_library_versions(root / relative))
        if version:
            return _loader_from_version_token(loader_name, version, minecraft_version)
    root_forge = _root_loader_jar_version(root, "forge")
    if root_forge:
        return _loader_from_version_token("forge", root_forge, minecraft_version)
    root_neoforge = _root_loader_jar_version(root, "neoforge")
    if root_neoforge:
        return _loader_from_version_token("neoforge", root_neoforge, minecraft_version)
    return {"name": None, "version": None, "minecraft_version": minecraft_version}


def _server_library_versions(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return [child.name for child in sorted(path.iterdir()) if child.is_dir()]


def _root_loader_jar_version(root: Path, loader_prefix: str) -> str | None:
    for path in sorted(root.glob(f"{loader_prefix}-*.jar")):
        if not path.is_file():
            continue
        stem = path.stem
        version = stem.removeprefix(f"{loader_prefix}-")
        for suffix in ("-server", "-universal", "-installer"):
            if version.endswith(suffix):
                version = version.removesuffix(suffix)
        if version:
            return version
    return None


def _source_inventory(root: Path) -> Dict[str, Dict[str, Any]]:
    return {
        "manifest": _manifest_source_state(root),
        "mods": _source_state(root / "mods", "*.jar"),
        "config": _source_state(root / "config", "*"),
        "kubejs": _source_state(root / "kubejs", "*"),
        "datapacks": _source_state(root / "datapacks", "*"),
        "defaultconfigs": _source_state(root / "defaultconfigs", "*"),
        "ftbquests": _source_state(root / "config" / "ftbquests" / "quests", "*.snbt"),
    }


def _manifest_source_state(root: Path) -> Dict[str, Any]:
    names = ["manifest.json", "modrinth.index.json", "mmc-pack.json", "modpackinfo.json"]
    present = [name for name in names if (root / name).is_file()]
    return {
        "path": str(root),
        "present": bool(present),
        "file_count": len(present),
        "files": present,
    }


def _source_state(path: Path, pattern: str) -> Dict[str, Any]:
    return {
        "path": str(path),
        "present": path.exists(),
        "file_count": _count_files(path, pattern),
        "sample_files": _sample_relative_paths(path, pattern, limit=10),
    }


def _optional_integrations(root: Path, source_inventory: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        "ftb_quests": {
            "present": bool(source_inventory["ftbquests"]["present"]) or _has_mod_jar(root, "ftb", "quests"),
            "source": "config/ftbquests/quests" if source_inventory["ftbquests"]["present"] else "mods",
        },
        "ftb_teams": {
            "present": _has_mod_jar(root, "ftb", "teams"),
            "source": "mods",
        },
        "game_stages": {
            "present": _has_mod_jar(root, "gamestages") or _has_mod_jar(root, "game", "stages"),
            "source": "mods",
        },
        "kubejs": {
            "present": bool(source_inventory["kubejs"]["present"]) or _has_mod_jar(root, "kubejs"),
            "source": "kubejs" if source_inventory["kubejs"]["present"] else "mods",
        },
    }


def _known_progression_sources(optional_integrations: Mapping[str, Mapping[str, Any]]) -> list[str]:
    sources = ["advancements"]
    if optional_integrations["ftb_quests"]["present"]:
        sources.append("ftbquests")
    if optional_integrations["game_stages"]["present"]:
        sources.append("gamestages")
    if optional_integrations["kubejs"]["present"]:
        sources.append("kubejs")
    return sources


def _has_mod_jar(root: Path, *tokens: str) -> bool:
    mods = root / "mods"
    if not mods.is_dir():
        return False
    lowered_tokens = [token.lower() for token in tokens]
    for path in mods.glob("*.jar"):
        name = path.name.lower()
        if all(token in name for token in lowered_tokens):
            return True
    return False


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


def _sample_relative_paths(root: Path, pattern: str, limit: int) -> list[str]:
    if not root.is_dir():
        return []
    samples = []
    for path in sorted(root.rglob(pattern)):
        if not path.is_file():
            continue
        samples.append(path.relative_to(root).as_posix())
        if len(samples) >= limit:
            break
    return samples


def _dig(payload: Mapping[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _instance_kind(setup: Mapping[str, str], pack_manifest: Mapping[str, Any]) -> str:
    if setup:
        return "pcl2_installed_instance"
    kind = pack_manifest.get("kind")
    return kind if isinstance(kind, str) and kind else "directory"


def _launcher(setup: Mapping[str, str], pack_manifest: Mapping[str, Any]) -> str | None:
    if setup:
        return "PCL2"
    launcher = pack_manifest.get("launcher")
    return launcher if isinstance(launcher, str) and launcher else None


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


def _slug(value: str) -> str:
    slug = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum():
            slug.append(char)
            previous_dash = False
        elif not previous_dash:
            slug.append("-")
            previous_dash = True
    return "".join(slug).strip("-") or "unknown-pack"
