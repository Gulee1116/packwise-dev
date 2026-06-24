from __future__ import annotations

import json
import hashlib
import re
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .ftbquests import inspect_quest_book
from .local_workflow import ask_local
from .pack_index import build_packwise_index_from_instance, runtime_index_from_sections
from .pack_profiles import load_pack_profiles, select_pack_profile
from .runtime_dump_files import load_runtime_dump_directory, validate_runtime_dump_directory
from .runtime_dump_importer import import_instance_context, import_runtime_dump_directory
from .service import AgentService


ACCEPTANCE_SCHEMA_VERSION = "packwise.phase1_acceptance.v1"
PHASE1_TARGET_PACK_ID = "atm9sky"
PHASE1_TARGET_MINECRAFT = "1.20.1"
PHASE1_TARGET_LOADER = "forge"
PHASE1_TARGET_FORGE_MAJOR = "47"
PHASE1_SECOND_FORGE_PROFILE_ID = "generic-forge-1201"
PHASE1_CORE_NON_EMPTY_SECTIONS = ("mods", "items", "tags", "recipes")
PHASE1_REQUIRED_NON_EMPTY_SECTIONS = ("mods", "items", "blocks", "fluids", "tags", "recipes", "advancements")
PHASE1_LOCAL_ANSWER_SCENARIOS = (
    {"id": "next_step", "question": "下一步该干什么？", "use_item": False},
    {"id": "unlock", "question": "这个物品怎么解锁？", "use_item": True},
    {"id": "jei_difference", "question": "为什么 JEI/网上配方和服务器不一样？", "use_item": False},
    {"id": "blocker", "question": "当前目标缺哪些前置机器/任务/材料？", "use_item": True},
)
CHECK_REMEDIATIONS = {
    "forge_jar_built": (
        "Run ./scripts/dev build-forge and pass --forge-jar if the jar is not at the default build path."
    ),
    "runtime_dump_valid": (
        "Run /packwise dump on the ATM9Sky server, then rerun validate-dump with --require-phase1 "
        "against the generated packwise-dumps/<dump_id> directory."
    ),
    "runtime_dump_targets_forge_1201": (
        "Use the Forge 1.20.1 ATM9Sky server runtime dump, not a NeoForge/Fabric/client dump "
        "or a dump from a different Minecraft version."
    ),
    "runtime_dump_connector_matches_jar": (
        "Rerun /packwise dump with the inspected Forge connector jar so manifest connector_mod_id "
        "and connector_version match the jar metadata."
    ),
    "phase1_core_sections_non_empty": (
        "Wait for the server to finish loading, rerun /packwise dump, and inspect "
        "mods/items/tags/recipes section files if any count remains zero."
    ),
    "phase1_runtime_sections_non_empty": (
        "Wait for the server to finish loading, rerun /packwise dump, and inspect "
        "mods/items/blocks/fluids/tags/recipes/advancements section files if any count remains zero."
    ),
    "pack_index_builds": (
        "Pass the installed ATM9Sky instance directory and a valid runtime dump directory; "
        "inspect the reported error for malformed static metadata or dump data."
    ),
    "atm9sky_profile_selected": (
        "Point --instance at the ATM9Sky installation root, or add/update a data-driven pack "
        "profile if the launcher metadata identifies the pack differently."
    ),
    "runtime_truth_authoritative": (
        "Build the index from a runtime dump that contains registries, tags, and recipes so "
        "static sources remain context-only."
    ),
    "runtime_progression_truth_ready": (
        "Run /packwise dump after optional FTB Quests, FTB Teams, and GameStages integrations "
        "are loaded, then verify ftb_quests, player_progress, team_progress, and stages sections "
        "are present and parseable."
    ),
    "second_forge_1201_profile_available": (
        "Keep the generic Forge 1.20.1 data profile available so a second Forge 1.20.1 pack "
        "can be selected without code changes."
    ),
    "agent_runtime_dump_imports": (
        "Import the runtime dump and installed instance context through AgentService, then build "
        "the service-side Packwise index."
    ),
    "local_answer_has_source_refs": (
        "Ask about an item or progression target present in the runtime dump or quest data, "
        "and verify the answer includes runtime or quest source references."
    ),
    "local_answer_scenarios_have_source_refs": (
        "Run the four Phase 1 local answer scenarios against the installed instance and runtime dump; "
        "each scenario must cite runtime dump, recipe, or quest sources."
    ),
    "live_connector_loaded_seen": (
        "Start the real ATM9Sky server with the Forge connector jar in mods/ and pass logs/latest.log "
        "showing the Packwise connector loaded message."
    ),
    "live_packwise_status_seen": (
        "Start the real ATM9Sky server with the Forge connector installed, run /packwise status, "
        "and pass the resulting logs/latest.log with --server-log."
    ),
    "live_packwise_dump_seen": (
        "Run /packwise dump on the real ATM9Sky server and pass the server log that includes "
        "the dump output plus the matching dump id or local dump path."
    ),
    "online_agent_connector_status_seen": (
        "If online upload is configured, verify PACKWISE_AGENT_URL points at the running agent, "
        "rerun /packwise dump, and pass --agent-url so the report can confirm the same "
        "connector id and dump id reached the agent, every declared section uploaded, and the "
        "scoped pack-index builds from the online runtime dump with no runtime consistency "
        "errors. If online upload is not part of this run, omit --agent-url."
    ),
    "online_agent_answer_has_source_refs": (
        "If online upload is configured, rerun /packwise dump, then verify the running agent can "
        "answer a query for the same connector id and dump id with runtime or item-specific "
        "source references. If online upload is not part of this run, omit --agent-url."
    ),
    "live_packwise_ask_sources_seen": (
        "Optional live answer evidence: configure PACKWISE_AGENT_URL, run /packwise ask after a "
        "successful uploaded dump, and keep the server log lines containing Sources: refs."
    ),
}


def build_phase1_acceptance_report(
    instance_path: str | Path,
    runtime_dump_dir: str | Path,
    forge_jar: str | Path | None = None,
    server_log: str | Path | None = None,
    agent_url: str | None = None,
    question: str = "当前目标缺哪些前置机器/任务/材料？",
    item_id: str | None = "minecraft:stone",
) -> Dict[str, Any]:
    instance = Path(instance_path)
    dump_dir = Path(runtime_dump_dir)
    jar_path = Path(forge_jar) if forge_jar is not None else _default_forge_jar()
    log_path = Path(server_log) if server_log is not None else None

    checks: list[Dict[str, Any]] = []
    artifacts: Dict[str, Any] = {
        "instance_path": str(instance),
        "runtime_dump_dir": str(dump_dir),
        "forge_jar": str(jar_path),
        "server_log": str(log_path) if log_path else None,
        "agent_url": agent_url,
    }

    jar_report = _inspect_forge_jar(jar_path)
    checks.append(
        _check(
            "forge_jar_built",
            jar_report["valid"],
            "Forge connector jar exists and contains the Forge command, dump collector, and shared protocol classes.",
            evidence=jar_report,
        )
    )

    validation = validate_runtime_dump_directory(dump_dir, require_phase1=True)
    checks.append(
        _check(
            "runtime_dump_valid",
            bool(validation.get("valid")),
            "Runtime dump manifest, section sizes, counts, sha256 values, and Phase 1 section presence validate.",
            evidence={
                "dump_id": validation.get("dump_id"),
                "manifest_path": validation.get("manifest_path"),
                "manifest_size_bytes": validation.get("manifest_size_bytes"),
                "manifest_sha256": validation.get("manifest_sha256"),
                "connector_mod_id": validation.get("connector_mod_id"),
                "connector_version": validation.get("connector_version"),
                "section_count": validation.get("section_count"),
                "sections": validation.get("sections"),
                "missing_phase1_sections": validation.get("missing_phase1_sections"),
                "empty_phase1_core_sections": validation.get("empty_phase1_core_sections"),
                "empty_phase1_required_sections": validation.get("empty_phase1_required_sections"),
                "runtime_consistency_errors": validation.get("runtime_consistency_errors"),
                "errors": validation.get("errors"),
            },
        )
    )
    checks.append(
        _check(
            "runtime_dump_targets_forge_1201",
            validation.get("loader") == PHASE1_TARGET_LOADER
            and validation.get("minecraft_version") == PHASE1_TARGET_MINECRAFT
            and _forge_major_matches(validation.get("loader_version")),
            "Runtime dump identity matches Forge 47 Minecraft 1.20.1.",
            evidence={
                "loader": validation.get("loader"),
                "minecraft_version": validation.get("minecraft_version"),
                "loader_version": validation.get("loader_version"),
                "expected_loader": PHASE1_TARGET_LOADER,
                "expected_minecraft_version": PHASE1_TARGET_MINECRAFT,
                "expected_forge_major": PHASE1_TARGET_FORGE_MAJOR,
            },
        )
    )
    dump_connector_evidence = _runtime_dump_connector_evidence(validation, jar_report)
    checks.append(
        _check(
            "runtime_dump_connector_matches_jar",
            bool(dump_connector_evidence.get("passed")),
            "Runtime dump manifest identifies the same connector artifact as the inspected Forge jar.",
            evidence=dump_connector_evidence,
        )
    )
    runtime_counts = _mapping(validation.get("runtime_index_summary"))
    missing_core = [
        name for name in PHASE1_CORE_NON_EMPTY_SECTIONS if _int(runtime_counts.get(name)) <= 0
    ]
    checks.append(
        _check(
            "phase1_core_sections_non_empty",
            not missing_core,
            "Phase 1 ATM9Sky runtime truth includes non-empty mods/items/tags/recipes sections.",
            evidence={
                "required_non_empty": list(PHASE1_CORE_NON_EMPTY_SECTIONS),
                "counts": dict(runtime_counts),
                "missing_or_empty": missing_core,
            },
        )
    )
    missing_required_sections = [
        name for name in PHASE1_REQUIRED_NON_EMPTY_SECTIONS if _int(runtime_counts.get(name)) <= 0
    ]
    checks.append(
        _check(
            "phase1_runtime_sections_non_empty",
            not missing_required_sections,
            "Phase 1 runtime dump includes non-empty mods/items/blocks/fluids/tags/recipes/advancements sections.",
            evidence={
                "required_non_empty": list(PHASE1_REQUIRED_NON_EMPTY_SECTIONS),
                "counts": dict(runtime_counts),
                "missing_or_empty": missing_required_sections,
            },
        )
    )

    pack_index: Dict[str, Any] = {}
    try:
        loaded = load_runtime_dump_directory(dump_dir, require_phase1=True)
        pack_index = build_packwise_index_from_instance(instance, loaded.sections).to_dict()
        index_error: str | None = None
    except Exception as exc:  # pragma: no cover - exact exception type is surfaced in the report.
        index_error = str(exc)
    checks.append(
        _check(
            "pack_index_builds",
            bool(pack_index) and index_error is None,
            "Static ATM9Sky sources and runtime dump build a normalized Packwise index.",
            evidence=_index_evidence(pack_index, index_error),
        )
    )
    checks.append(
        _check(
            "atm9sky_profile_selected",
            _profile_id(pack_index) == PHASE1_TARGET_PACK_ID,
            "Installed instance selects the ATM9Sky data-driven pack profile.",
            evidence={
                "profile_id": _profile_id(pack_index),
                "identity": _mapping(pack_index.get("identity")),
            },
        )
    )
    checks.append(
        _check(
            "runtime_truth_authoritative",
            _runtime_truth_ready(pack_index),
            "Packwise index reconciles registries, tags, and recipes as runtime-authoritative.",
            evidence=_mapping(_mapping(pack_index.get("source_policy")).get("reconciliation")),
        )
    )
    progression_truth = _runtime_progression_truth_evidence(pack_index)
    checks.append(
        _check(
            "runtime_progression_truth_ready",
            bool(progression_truth.get("passed")),
            "Packwise index has runtime-authoritative advancements, quests, player/team progress, and stages.",
            required=False,
            evidence=progression_truth,
        )
    )
    second_pack_profile = _second_forge_1201_profile_evidence()
    checks.append(
        _check(
            "second_forge_1201_profile_available",
            bool(second_pack_profile.get("passed")),
            "A second Forge 1.20.1 pack can select the generic data-driven profile without code changes.",
            evidence=second_pack_profile,
        )
    )
    agent_import_summary = _run_agent_import(instance, dump_dir)
    checks.append(
        _check(
            "agent_runtime_dump_imports",
            bool(agent_import_summary.get("passed")),
            "AgentService imports the runtime dump plus instance context and builds a Packwise index.",
            evidence=agent_import_summary,
        )
    )
    item_source_expectation = _item_source_expectation(instance, dump_dir, item_id)

    local_answer: Dict[str, Any] = {}
    try:
        local_answer = ask_local(
            instance_path=instance,
            runtime_dump_dir=dump_dir,
            question=question,
            item_id=item_id,
        )
        answer_error: str | None = None
    except Exception as exc:  # pragma: no cover - exact exception type is surfaced in the report.
        answer_error = str(exc)
    source_refs = _answer_source_refs(local_answer)
    source_requirement = _answer_source_requirement(source_refs, item_id, item_source_expectation)
    local_dump_source_requirement = _answer_dump_source_requirement(
        source_refs,
        validation.get("dump_id") if isinstance(validation.get("dump_id"), str) else None,
    )
    checks.append(
        _check(
            "local_answer_has_source_refs",
            bool(local_answer)
            and source_requirement["passed"]
            and local_dump_source_requirement["passed"],
            "Agent can answer a basic ATM9Sky recipe/progression question with concrete source references tied to the validated runtime dump.",
            evidence={
                "question": question,
                "item_id": item_id,
                "source_refs": source_refs,
                "source_requirement": source_requirement,
                "dump_source_requirement": local_dump_source_requirement,
                "error": answer_error,
            },
        )
    )
    local_answer_scenarios = _run_local_answer_scenarios(
        instance,
        dump_dir,
        item_id,
        validation.get("dump_id") if isinstance(validation.get("dump_id"), str) else None,
        item_source_expectation,
    )
    failed_scenarios = [
        scenario["id"]
        for scenario in local_answer_scenarios
        if not scenario.get("passed")
    ]
    checks.append(
        _check(
            "local_answer_scenarios_have_source_refs",
            not failed_scenarios,
            "Agent can answer the four named Phase 1 question scenarios with source references.",
            evidence={
                "scenario_count": len(local_answer_scenarios),
                "failed_scenarios": failed_scenarios,
                "scenarios": local_answer_scenarios,
            },
        )
    )

    live_evidence = _inspect_server_log(
        log_path,
        dump_dir=dump_dir,
        connector_id=validation.get("connector_id") if isinstance(validation.get("connector_id"), str) else None,
        dump_id=validation.get("dump_id") if isinstance(validation.get("dump_id"), str) else None,
        connector_version=_string_or_none(_mapping(jar_report.get("metadata")).get("mod_version")),
    )
    checks.append(
        _check(
            "live_connector_loaded_seen",
            live_evidence["loaded_seen"],
            "Live ATM9Sky server log shows the Forge connector was loaded.",
            evidence=live_evidence,
        )
    )
    checks.append(
        _check(
            "live_packwise_status_seen",
            live_evidence["status_seen"],
            "Live ATM9Sky server log shows /packwise status output.",
            evidence=live_evidence,
        )
    )
    checks.append(
        _check(
            "live_packwise_dump_seen",
            live_evidence["dump_seen"],
            "Live ATM9Sky server log shows /packwise dump output for the validated runtime dump.",
            evidence=live_evidence,
        )
    )
    checks.append(
        _check(
            "live_optional_diagnostics_seen",
            live_evidence["optional_diagnostics_seen"],
            "Live server log includes optional integration and optional section diagnostics.",
            required=False,
            evidence=live_evidence,
        )
    )
    checks.append(
        _check(
            "live_packwise_ask_sources_seen",
            live_evidence["ask_source_refs_seen"],
            "Live server log includes optional /packwise ask answer source references.",
            required=False,
            evidence=live_evidence,
        )
    )
    online_agent_evidence = _inspect_online_agent(
        agent_url,
        connector_id=validation.get("connector_id") if isinstance(validation.get("connector_id"), str) else None,
        dump_id=validation.get("dump_id") if isinstance(validation.get("dump_id"), str) else None,
        connector_mod_id=(
            _string_or_none(_mapping(jar_report.get("metadata")).get("mod_id"))
            if jar_report.get("valid")
            else None
        ),
        connector_version=(
            _string_or_none(_mapping(jar_report.get("metadata")).get("mod_version"))
            if jar_report.get("valid")
            else None
        ),
    )
    online_agent_required = bool(agent_url and agent_url.strip())
    checks.append(
        _check(
            "online_agent_connector_status_seen",
            bool(online_agent_evidence.get("passed")),
            "Online agent reports the same connector hello and runtime dump when --agent-url is supplied.",
            required=online_agent_required,
            evidence=online_agent_evidence,
        )
    )
    online_answer_evidence = _inspect_online_answer(
        agent_url,
        connector_id=validation.get("connector_id") if isinstance(validation.get("connector_id"), str) else None,
        dump_id=validation.get("dump_id") if isinstance(validation.get("dump_id"), str) else None,
        question=question,
        item_id=item_id,
        item_source_expectation=item_source_expectation,
    )
    checks.append(
        _check(
            "online_agent_answer_has_source_refs",
            bool(online_answer_evidence.get("passed")),
            "Online agent ask endpoint answers from the uploaded dump with source references when --agent-url is supplied.",
            required=online_agent_required,
            evidence=online_answer_evidence,
        )
    )

    passed = all(check["passed"] for check in checks if check["required"])
    next_actions = _next_actions(checks)
    return {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "target": {
            "pack": "All the Mods 9: To the Sky",
            "profile_id": PHASE1_TARGET_PACK_ID,
            "loader": PHASE1_TARGET_LOADER,
            "minecraft_version": PHASE1_TARGET_MINECRAFT,
        },
        "status": "passed" if passed else "blocked",
        "valid": passed,
        "artifacts": artifacts,
        "checks": checks,
        "next_actions": next_actions,
        "runtime_validation": validation,
        "pack_index_summary": _pack_index_summary(pack_index),
        "agent_import_summary": agent_import_summary,
        "online_agent_summary": online_agent_evidence,
        "online_answer_summary": online_answer_evidence,
        "local_answer_summary": _local_answer_summary(local_answer),
        "local_answer_scenarios": local_answer_scenarios,
    }


def _default_forge_jar() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "connectors" / "forge" / "build" / "libs" / "packwise_connector-0.1.0.jar"


def _inspect_forge_jar(path: Path) -> Dict[str, Any]:
    required_entries = [
        "META-INF/mods.toml",
        "dev/packwise/connector/forge/PackwiseForgeMod.class",
        "dev/packwise/connector/forge/PackwiseForgeCommands.class",
        "dev/packwise/connector/forge/ForgePackMetadata.class",
        "dev/packwise/connector/forge/ForgeRuntimeDumpCollector.class",
        "dev/packwise/connector/forge/ForgeOptionalRuntimeDumpCollector.class",
        "dev/packwise/connector/protocol/AgentAnswer.class",
        "dev/packwise/connector/protocol/AgentHttpClient.class",
        "dev/packwise/connector/protocol/CommandResponse.class",
        "dev/packwise/connector/protocol/ConnectorHello.class",
        "dev/packwise/connector/protocol/ConnectorInfo.class",
        "dev/packwise/connector/protocol/ConnectorSide.class",
        "dev/packwise/connector/protocol/JsonText.class",
        "dev/packwise/connector/protocol/ModSnapshot.class",
        "dev/packwise/connector/protocol/ModsSectionDumper.class",
        "dev/packwise/connector/protocol/NdjsonSectionDumper.class",
        "dev/packwise/connector/protocol/QueryAsk.class",
        "dev/packwise/connector/protocol/RuntimeDumpContent.class",
        "dev/packwise/connector/protocol/RuntimeDumpFileWriter.class",
        "dev/packwise/connector/protocol/RuntimeDumpManifest.class",
        "dev/packwise/connector/protocol/RuntimeDumpSection.class",
        "dev/packwise/connector/protocol/RuntimeDumpUploader.class",
        "dev/packwise/connector/protocol/RuntimeDumpUploadResult.class",
        "dev/packwise/connector/protocol/RuntimeSectionNames.class",
    ]
    report: Dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": None,
        "sha256": None,
        "required_entries": required_entries,
        "missing_entries": required_entries,
        "forbidden_entries": [],
        "pack_specific_string_matches": [],
        "metadata": {},
        "missing_metadata": [],
        "valid": False,
    }
    if not path.is_file():
        return report
    report["size_bytes"] = path.stat().st_size
    report["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        report["error"] = str(exc)
        return report
    missing = [entry for entry in required_entries if entry not in names]
    report["missing_entries"] = missing
    forbidden = _forbidden_forge_jar_entries(names)
    report["forbidden_entries"] = forbidden
    pack_specific_string_matches = _pack_specific_string_matches(path, names)
    report["pack_specific_string_matches"] = pack_specific_string_matches
    if "META-INF/mods.toml" in names:
        try:
            mods_toml = archive_text(path, "META-INF/mods.toml")
            metadata = _forge_mods_metadata(mods_toml)
            missing_metadata = _missing_forge_metadata(metadata)
            report["metadata"] = metadata
            report["missing_metadata"] = missing_metadata
        except (OSError, tomllib.TOMLDecodeError) as exc:
            report["metadata_error"] = str(exc)
            report["missing_metadata"] = ["parseable_mods_toml"]
    else:
        report["missing_metadata"] = ["mods_toml"]
    report["entry_count"] = len(names)
    report["valid"] = (
        not missing
        and not forbidden
        and not pack_specific_string_matches
        and not report["missing_metadata"]
    )
    return report


def archive_text(path: Path, entry: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(entry).decode("utf-8")


def _forbidden_forge_jar_entries(names: set[str]) -> list[str]:
    forbidden_suffixes = (".py", ".pyc", ".pyo", ".whl", ".egg")
    forbidden_segments = ("/python/", "/site-packages/", "/pip/")
    forbidden_names = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"}
    matches = []
    for name in sorted(names):
        lowered = name.lower()
        basename = lowered.rsplit("/", 1)[-1]
        if (
            lowered.endswith(forbidden_suffixes)
            or any(segment in f"/{lowered}" for segment in forbidden_segments)
            or basename in forbidden_names
        ):
            matches.append(name)
    return matches


def _pack_specific_string_matches(path: Path, names: set[str]) -> list[Dict[str, str]]:
    forbidden_needles = {
        b"atm9sky": "atm9sky",
        b"all the mods 9": "all the mods 9",
        b"all-the-mods-9-to-the-sky": "all-the-mods-9-to-the-sky",
    }
    matches = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(names):
            if name.endswith("/"):
                continue
            lowered = archive.read(name).lower()
            for needle, label in forbidden_needles.items():
                if needle in lowered:
                    matches.append({"entry": name, "match": label})
    return matches


def _forge_mods_metadata(text: str) -> Dict[str, Any]:
    payload = tomllib.loads(text)
    mods = payload.get("mods") if isinstance(payload.get("mods"), list) else []
    packwise_mod = next(
        (
            mod
            for mod in mods
            if isinstance(mod, Mapping) and mod.get("modId") == "packwise_connector"
        ),
        {},
    )
    dependencies = _mapping(payload.get("dependencies"))
    packwise_dependencies = dependencies.get("packwise_connector")
    if not isinstance(packwise_dependencies, list):
        packwise_dependencies = []
    forge_dependency = _dependency(packwise_dependencies, "forge")
    minecraft_dependency = _dependency(packwise_dependencies, "minecraft")
    return {
        "mod_loader": payload.get("modLoader"),
        "loader_version_range": payload.get("loaderVersion"),
        "mod_id": packwise_mod.get("modId"),
        "mod_version": packwise_mod.get("version"),
        "display_name": packwise_mod.get("displayName"),
        "forge_dependency_range": forge_dependency.get("versionRange"),
        "minecraft_dependency_range": minecraft_dependency.get("versionRange"),
    }


def _dependency(dependencies: list[Any], mod_id: str) -> Mapping[str, Any]:
    for dependency in dependencies:
        if isinstance(dependency, Mapping) and dependency.get("modId") == mod_id:
            return dependency
    return {}


def _missing_forge_metadata(metadata: Mapping[str, Any]) -> list[str]:
    missing = []
    if metadata.get("mod_loader") != "javafml":
        missing.append("modLoader=javafml")
    if metadata.get("mod_id") != "packwise_connector":
        missing.append("modId=packwise_connector")
    if not _contains_text(metadata.get("loader_version_range"), "47"):
        missing.append("loaderVersion includes Forge 47")
    if not _contains_text(metadata.get("forge_dependency_range"), "47"):
        missing.append("forge dependency includes Forge 47")
    if not _contains_text(metadata.get("minecraft_dependency_range"), PHASE1_TARGET_MINECRAFT):
        missing.append(f"minecraft dependency includes {PHASE1_TARGET_MINECRAFT}")
    return missing


def _contains_text(value: Any, needle: str) -> bool:
    return isinstance(value, str) and needle in value


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _connector_mod_label(version: str | None) -> str | None:
    if not version:
        return None
    return f"packwise_connector {version}"


def _forge_major_matches(value: Any) -> bool:
    return isinstance(value, str) and re.match(rf"^{re.escape(PHASE1_TARGET_FORGE_MAJOR)}(?:\.|$)", value) is not None


def _inspect_server_log(
    path: Optional[Path],
    *,
    dump_dir: Path,
    connector_id: str | None,
    dump_id: str | None,
    connector_version: str | None,
) -> Dict[str, Any]:
    expected = {
        "expected_connector_id": connector_id,
        "expected_dump_id": dump_id,
        "expected_dump_dir": str(dump_dir),
        "expected_connector_mod": _connector_mod_label(connector_version),
        "size_bytes": None,
        "sha256": None,
        "status_identity_seen": False,
        "status_forge_major_seen": False,
        "status_connector_mod_seen": False,
        "generic_loaded_seen": False,
        "loaded_connector_mod_seen": False,
        "status_connector_id_seen": False,
        "status_pack_seen": False,
        "status_capabilities_seen": False,
        "status_optional_integrations_seen": False,
        "status_agent_url_seen": False,
        "generic_dump_seen": False,
        "dump_connector_id_seen": False,
        "dump_id_detail_seen": False,
        "dump_id_seen": False,
        "dump_path_seen": False,
        "ask_answer_seen": False,
        "ask_source_refs_seen": False,
        "ask_source_refs": [],
        "ask_dump_source_refs": [],
        "ask_expected_dump_id": dump_id,
        "ask_failure_seen": False,
    }
    if path is None:
        return {
            "path": None,
            "present": False,
            "loaded_seen": False,
            "status_seen": False,
            "dump_seen": False,
            "optional_diagnostics_seen": False,
            **expected,
            "hint": "Provide --server-log from the ATM9Sky server after running /packwise status and /packwise dump.",
        }
    if not path.is_file():
        return {
            "path": str(path),
            "present": False,
            "loaded_seen": False,
            "status_seen": False,
            "dump_seen": False,
            "optional_diagnostics_seen": False,
            **expected,
            "hint": "Server log file was not found.",
        }
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    text = raw_text.lower()
    normalized_text = _normalize_log_path(text)
    log_bytes = path.read_bytes()
    generic_loaded_seen = "packwise connector loaded" in text and "packwise_connector" in text
    loaded_connector_mod_seen = (
        _contains_loaded_connector_version(text, connector_version)
        if connector_version
        else True
    )
    loaded_seen = generic_loaded_seen and loaded_connector_mod_seen
    status_forge_major_seen = _status_forge_major_seen(text)
    status_identity_seen = status_forge_major_seen and "minecraft 1.20.1" in text
    status_connector_mod_seen = (
        _contains_labeled_value(text, "connector mod", _connector_mod_label(connector_version))
        if connector_version
        else True
    )
    status_connector_id_seen = _contains_labeled_value(text, "connector id", connector_id) if connector_id else False
    status_pack_seen = "pack:" in text
    status_capabilities_seen = "capabilities:" in text and "runtime_dump" in text and "commands" in text
    status_optional_integrations_seen = "optional integrations:" in text
    status_agent_url_seen = "agent url:" in text
    status_seen = all(
        [
            status_identity_seen,
            status_connector_mod_seen,
            status_connector_id_seen,
            status_pack_seen,
            status_capabilities_seen,
            status_optional_integrations_seen,
            status_agent_url_seen,
        ]
    )
    generic_dump_seen = "packwise:" in text and "runtime dump" in text and ("path=" in text or "packwise-dumps" in text)
    dump_connector_id_seen = _contains_detail_value(text, "connector_id", connector_id) if connector_id else False
    dump_id_detail_seen = _contains_dump_id_detail(text, dump_id) if dump_id else False
    dump_id_seen = _contains_path_segment(text, dump_id) if dump_id else False
    dump_path_seen = _normalize_log_path(str(dump_dir)).lower() in normalized_text
    dump_seen = generic_dump_seen and dump_connector_id_seen and (dump_id_detail_seen or dump_id_seen or dump_path_seen)
    optional_diagnostics_seen = (
        ("optional integrations:" in text or "optional_integrations=" in text)
        and "optional_sections=" in text
    )
    ask_source_refs = _extract_live_ask_source_refs(text)
    ask_dump_source_refs = _live_dump_source_refs(ask_source_refs, dump_id)
    ask_source_refs_seen = bool(ask_dump_source_refs)
    ask_answer_seen = bool(ask_source_refs) and "confidence:" in text
    ask_failure_seen = "packwise ask failed" in text or "packwise ask requires" in text
    return {
        "path": str(path),
        "present": True,
        "size_bytes": len(log_bytes),
        "sha256": hashlib.sha256(log_bytes).hexdigest(),
        "loaded_seen": loaded_seen,
        "generic_loaded_seen": generic_loaded_seen,
        "loaded_connector_mod_seen": loaded_connector_mod_seen,
        "status_seen": status_seen,
        "status_identity_seen": status_identity_seen,
        "status_forge_major_seen": status_forge_major_seen,
        "status_connector_mod_seen": status_connector_mod_seen,
        "status_connector_id_seen": status_connector_id_seen,
        "status_pack_seen": status_pack_seen,
        "status_capabilities_seen": status_capabilities_seen,
        "status_optional_integrations_seen": status_optional_integrations_seen,
        "status_agent_url_seen": status_agent_url_seen,
        "dump_seen": dump_seen,
        "generic_dump_seen": generic_dump_seen,
        "expected_connector_id": connector_id,
        "dump_connector_id_seen": dump_connector_id_seen,
        "expected_dump_id": dump_id,
        "expected_dump_dir": str(dump_dir),
        "expected_connector_mod": _connector_mod_label(connector_version),
        "dump_id_detail_seen": dump_id_detail_seen,
        "dump_id_seen": dump_id_seen,
        "dump_path_seen": dump_path_seen,
        "optional_diagnostics_seen": optional_diagnostics_seen,
        "ask_answer_seen": ask_answer_seen,
        "ask_source_refs_seen": ask_source_refs_seen,
        "ask_source_refs": ask_source_refs,
        "ask_dump_source_refs": ask_dump_source_refs,
        "ask_expected_dump_id": dump_id,
        "ask_failure_seen": ask_failure_seen,
    }


def _inspect_online_agent(
    agent_url: str | None,
    *,
    connector_id: str | None,
    dump_id: str | None,
    connector_mod_id: str | None,
    connector_version: str | None,
) -> Dict[str, Any]:
    expected = {
        "configured": bool(agent_url and agent_url.strip()),
        "endpoint": None,
        "expected_connector_id": connector_id,
        "expected_dump_id": dump_id,
        "expected_connector_mod_id": connector_mod_id,
        "expected_connector_version": connector_version,
        "expected_connector_mod": _connector_mod_label(connector_version),
        "checked": False,
        "status_endpoint": None,
        "pack_index_endpoint": None,
        "present": False,
        "hello_present": False,
        "connector_id_seen": False,
        "connector_mod_seen": False,
        "dump_seen": False,
        "dump_identity_matches": False,
        "dump_connector_mod_seen": False,
        "dump_upload_complete": False,
        "dump_declared_sections": [],
        "dump_uploaded_sections": [],
        "dump_missing_uploaded_sections": [],
        "dump_required_sections_non_empty": False,
        "dump_missing_required_sections": list(PHASE1_REQUIRED_NON_EMPTY_SECTIONS),
        "dump_runtime_consistency_errors": [],
        "dump_runtime_consistency_valid": False,
        "pack_index_checked": False,
        "pack_index_seen": False,
        "pack_index_profile_id": None,
        "pack_index_runtime_truth_ready": False,
        "passed": False,
    }
    if not agent_url or not agent_url.strip():
        return {
            **expected,
            "hint": "Pass --agent-url to verify online connector.hello and runtime dump upload evidence.",
        }
    if not connector_id or not dump_id:
        return {
            **expected,
            "checked": False,
            "error": "Runtime dump validation did not provide connector_id and dump_id.",
        }

    status_endpoint = _agent_connector_status_url(agent_url, connector_id)
    status_response = _fetch_agent_json(status_endpoint)
    if not status_response["ok"]:
        return {
            **expected,
            "endpoint": status_endpoint,
            "status_endpoint": status_endpoint,
            "checked": True,
            "http_status": status_response.get("http_status"),
            "error": status_response.get("error"),
        }
    payload = _mapping(status_response.get("payload"))

    connector_payload = _mapping(payload.get("connector"))
    runtime_dumps = payload.get("runtime_dumps")
    runtime_dumps = runtime_dumps if isinstance(runtime_dumps, list) else []
    matching_dump = next(
        (
            dump
            for dump in runtime_dumps
            if isinstance(dump, Mapping) and dump.get("dump_id") == dump_id
        ),
        None,
    )
    hello_present = payload.get("hello_present") is True
    connector_id_seen = (
        payload.get("connector_id") == connector_id
        and connector_payload.get("id") == connector_id
    )
    connector_artifact_comparable = bool(connector_mod_id and connector_version)
    connector_mod_seen = (
        not connector_artifact_comparable
        or (
            connector_payload.get("connector_mod_id") == connector_mod_id
            and connector_payload.get("connector_version") == connector_version
        )
    )
    dump_seen = matching_dump is not None
    dump_identity_matches = (
        isinstance(matching_dump, Mapping)
        and matching_dump.get("loader") == PHASE1_TARGET_LOADER
        and matching_dump.get("minecraft_version") == PHASE1_TARGET_MINECRAFT
        and _forge_major_matches(matching_dump.get("loader_version"))
    )
    dump_connector_mod_seen = (
        not connector_artifact_comparable
        or (
            isinstance(matching_dump, Mapping)
            and matching_dump.get("connector_mod_id") == connector_mod_id
            and matching_dump.get("connector_version") == connector_version
        )
    )
    dump_upload_complete = isinstance(matching_dump, Mapping) and matching_dump.get("upload_complete") is True
    dump_declared_sections = _string_list(_mapping(matching_dump).get("declared_sections"))
    dump_uploaded_sections = _string_list(_mapping(matching_dump).get("uploaded_sections"))
    dump_missing_uploaded_sections = _string_list(_mapping(matching_dump).get("missing_sections"))
    dump_indexed_summary = _mapping(_mapping(matching_dump).get("indexed_summary"))
    dump_missing_required_sections = [
        name for name in PHASE1_REQUIRED_NON_EMPTY_SECTIONS if _int(dump_indexed_summary.get(name)) <= 0
    ]
    dump_required_sections_non_empty = isinstance(matching_dump, Mapping) and not dump_missing_required_sections
    dump_runtime_consistency_errors_raw = _mapping(matching_dump).get("runtime_consistency_errors")
    dump_runtime_consistency_errors = _list(dump_runtime_consistency_errors_raw)
    dump_runtime_consistency_valid = (
        isinstance(matching_dump, Mapping)
        and isinstance(dump_runtime_consistency_errors_raw, list)
        and not dump_runtime_consistency_errors
    )
    pack_index_endpoint = _agent_pack_index_url(agent_url, connector_id, dump_id)
    pack_index_response = _fetch_agent_json(pack_index_endpoint)
    pack_index_payload = _mapping(pack_index_response.get("payload"))
    pack_index_seen = (
        pack_index_response["ok"]
        and pack_index_payload.get("schema_version") == "packwise.index.v1"
    )
    pack_index_profile_id = _profile_id(pack_index_payload)
    pack_index_runtime_truth_ready = pack_index_seen and _runtime_truth_ready(pack_index_payload)
    passed = (
        payload.get("message_type") == "connector.status"
        and hello_present
        and connector_id_seen
        and connector_mod_seen
        and dump_seen
        and dump_identity_matches
        and dump_connector_mod_seen
        and dump_upload_complete
        and dump_required_sections_non_empty
        and dump_runtime_consistency_valid
        and pack_index_seen
        and pack_index_runtime_truth_ready
    )
    return {
        **expected,
        "endpoint": status_endpoint,
        "status_endpoint": status_endpoint,
        "pack_index_endpoint": pack_index_endpoint,
        "checked": True,
        "present": True,
        "http_status": status_response.get("http_status"),
        "message_type": payload.get("message_type"),
        "hello_present": hello_present,
        "connector_id_seen": connector_id_seen,
        "connector_mod_seen": connector_mod_seen,
        "dump_seen": dump_seen,
        "dump_identity_matches": dump_identity_matches,
        "dump_connector_mod_seen": dump_connector_mod_seen,
        "dump_upload_complete": dump_upload_complete,
        "dump_declared_sections": dump_declared_sections,
        "dump_uploaded_sections": dump_uploaded_sections,
        "dump_missing_uploaded_sections": dump_missing_uploaded_sections,
        "dump_required_sections_non_empty": dump_required_sections_non_empty,
        "dump_missing_required_sections": dump_missing_required_sections,
        "dump_runtime_consistency_errors": dump_runtime_consistency_errors,
        "dump_runtime_consistency_valid": dump_runtime_consistency_valid,
        "connector": dict(connector_payload),
        "matching_dump": dict(matching_dump) if isinstance(matching_dump, Mapping) else None,
        "runtime_dump_count": len(runtime_dumps),
        "pack_index_checked": True,
        "pack_index_http_status": pack_index_response.get("http_status"),
        "pack_index_seen": pack_index_seen,
        "pack_index_profile_id": pack_index_profile_id,
        "pack_index_runtime_truth_ready": pack_index_runtime_truth_ready,
        "pack_index_runtime_counts": dict(_mapping(_mapping(pack_index_payload.get("runtime")).get("counts"))),
        "pack_index_error": None if pack_index_response["ok"] else pack_index_response.get("error"),
        "passed": passed,
    }


def _fetch_agent_json(endpoint: str) -> Dict[str, Any]:
    try:
        request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            status_code = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "http_status": exc.code, "error": body}
    except (OSError, TimeoutError) as exc:
        return {"ok": False, "http_status": None, "error": str(exc)}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return {"ok": False, "http_status": status_code, "error": f"Invalid JSON response: {exc}"}
    if not isinstance(payload, Mapping):
        return {"ok": False, "http_status": status_code, "error": "JSON response was not an object."}
    return {"ok": True, "http_status": status_code, "payload": payload}


def _agent_connector_status_url(agent_url: str, connector_id: str) -> str:
    base = agent_url.strip().rstrip("/")
    quoted_connector_id = urllib.parse.quote(connector_id, safe="")
    return f"{base}/v1/connectors/{quoted_connector_id}"


def _agent_pack_index_url(agent_url: str, connector_id: str, dump_id: str) -> str:
    base = agent_url.strip().rstrip("/")
    quoted_connector_id = urllib.parse.quote(connector_id, safe="")
    quoted_dump_id = urllib.parse.quote(dump_id, safe="")
    return f"{base}/v1/connectors/{quoted_connector_id}/runtime-dumps/{quoted_dump_id}/pack-index"


def _inspect_online_answer(
    agent_url: str | None,
    *,
    connector_id: str | None,
    dump_id: str | None,
    question: str,
    item_id: str | None,
    item_source_expectation: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    expected = {
        "configured": bool(agent_url and agent_url.strip()),
        "endpoint": None,
        "expected_connector_id": connector_id,
        "expected_dump_id": dump_id,
        "question": question,
        "item_id": item_id,
        "checked": False,
        "answer_seen": False,
        "source_refs": [],
        "source_requirement": _answer_source_requirement([], item_id, item_source_expectation),
        "dump_source_requirement": _answer_dump_source_requirement([], dump_id),
        "passed": False,
    }
    if not agent_url or not agent_url.strip():
        return {
            **expected,
            "hint": "Pass --agent-url to verify online query.ask answer evidence.",
        }
    if not connector_id or not dump_id:
        return {
            **expected,
            "checked": False,
            "error": "Runtime dump validation did not provide connector_id and dump_id.",
        }

    endpoint = _agent_ask_url(agent_url)
    payload = {
        "protocol": "packwise.connector.v1",
        "message_type": "query.ask",
        "message_id": "phase1_online_answer_check",
        "sent_at": "2026-06-14T08:00:00Z",
        "question": question,
        "locale": "zh_cn",
        "context": {
            "connector_id": connector_id,
            "dump_id": dump_id,
            "loader": PHASE1_TARGET_LOADER,
            "minecraft_version": PHASE1_TARGET_MINECRAFT,
            "pack_id": PHASE1_TARGET_PACK_ID,
        },
    }
    if item_id:
        payload["context"]["item_id"] = item_id

    response = _post_agent_json(endpoint, payload)
    if not response["ok"]:
        return {
            **expected,
            "endpoint": endpoint,
            "checked": True,
            "http_status": response.get("http_status"),
            "error": response.get("error"),
        }
    response_payload = _mapping(response.get("payload"))
    source_refs = _answer_source_refs(response_payload)
    source_requirement = _answer_source_requirement(source_refs, item_id, item_source_expectation)
    dump_source_requirement = _answer_dump_source_requirement(source_refs, dump_id)
    answer = _mapping(response_payload.get("answer"))
    passed = (
        response_payload.get("message_type") == "answer.packet"
        and bool(answer)
        and source_requirement["passed"]
        and dump_source_requirement["passed"]
    )
    return {
        **expected,
        "endpoint": endpoint,
        "checked": True,
        "http_status": response.get("http_status"),
        "message_type": response_payload.get("message_type"),
        "answer_seen": bool(answer),
        "summary": answer.get("summary"),
        "confidence": answer.get("confidence"),
        "source_refs": source_refs,
        "source_requirement": source_requirement,
        "dump_source_requirement": dump_source_requirement,
        "passed": passed,
    }


def _post_agent_json(endpoint: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            status_code = response.status
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "http_status": exc.code, "error": response_body}
    except (OSError, TimeoutError) as exc:
        return {"ok": False, "http_status": None, "error": str(exc)}

    try:
        response_payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        return {"ok": False, "http_status": status_code, "error": f"Invalid JSON response: {exc}"}
    if not isinstance(response_payload, Mapping):
        return {"ok": False, "http_status": status_code, "error": "JSON response was not an object."}
    return {"ok": True, "http_status": status_code, "payload": response_payload}


def _agent_ask_url(agent_url: str) -> str:
    base = agent_url.strip().rstrip("/")
    return f"{base}/v1/query/ask"


def _normalize_log_path(value: str) -> str:
    return value.replace("\\", "/").lower()


def _contains_path_segment(text: str, value: str | None) -> bool:
    if not value:
        return False
    escaped = re.escape(value.lower())
    pattern = rf"(?<![a-z0-9_.-]){escaped}(?![a-z0-9_.-])"
    return re.search(pattern, text.lower()) is not None


def _contains_dump_id_detail(text: str, value: str | None) -> bool:
    return _contains_detail_value(text, "dump_id", value)


def _contains_detail_value(text: str, key: str, value: str | None) -> bool:
    if not value:
        return False
    escaped_key = re.escape(key.lower())
    escaped_value = re.escape(value.lower())
    return re.search(rf"{escaped_key}\s*=\s*{escaped_value}(?![a-z0-9_.-])", text.lower()) is not None


def _contains_labeled_value(text: str, label: str, value: str | None) -> bool:
    if not value:
        return False
    escaped_label = re.escape(label.lower())
    escaped_value = re.escape(value.lower())
    return re.search(rf"{escaped_label}\s*:\s*{escaped_value}(?![a-z0-9_.-])", text.lower()) is not None


def _contains_loaded_connector_version(text: str, version: str | None) -> bool:
    if not version:
        return False
    escaped_version = re.escape(version.lower())
    return (
        re.search(
            rf"packwise connector loaded:.*mod_id\s*=\s*packwise_connector.*version\s*=\s*{escaped_version}(?![a-z0-9_.-])",
            text.lower(),
        )
        is not None
    )


def _status_forge_major_seen(text: str) -> bool:
    escaped = re.escape(PHASE1_TARGET_FORGE_MAJOR)
    return re.search(rf"packwise connector:\s*forge\s+{escaped}(?:\.|\s|$)", text.lower()) is not None


def _extract_live_ask_source_refs(text: str) -> list[str]:
    refs: list[str] = []
    allowed_prefixes = ("recipe:", "quest:", "runtime_dump_section:")
    for line in text.splitlines():
        if "sources:" not in line:
            continue
        _, source_text = line.split("sources:", 1)
        for raw_ref in source_text.split(","):
            ref = raw_ref.strip()
            if ref.startswith(allowed_prefixes):
                refs.append(ref)
    return refs


def _live_dump_source_refs(refs: list[str], dump_id: str | None) -> list[str]:
    if not dump_id:
        return []
    expected_prefix = f"runtime_dump_section:{dump_id}/"
    return [ref for ref in refs if ref.startswith(expected_prefix)]


def _check(
    check_id: str,
    passed: bool,
    description: str,
    *,
    required: bool = True,
    evidence: Any = None,
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "required": required,
        "passed": bool(passed),
        "description": description,
        "remediation": CHECK_REMEDIATIONS.get(check_id),
        "evidence": evidence,
    }


def _next_actions(checks: list[Mapping[str, Any]]) -> list[Dict[str, str]]:
    actions: list[Dict[str, str]] = []
    for check in checks:
        if not check.get("required") or check.get("passed"):
            continue
        remediation = check.get("remediation")
        action: Dict[str, str] = {"check_id": str(check.get("id"))}
        if isinstance(remediation, str):
            action["action"] = remediation
        actions.append(action)
    return actions


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item for item in _list(value) if isinstance(item, str)]


def _int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _profile_id(pack_index: Mapping[str, Any]) -> str | None:
    profile = _mapping(pack_index.get("profile"))
    value = profile.get("profile_id")
    return value if isinstance(value, str) else None


def _index_evidence(pack_index: Mapping[str, Any], error: str | None) -> Dict[str, Any]:
    return {
        "schema_version": pack_index.get("schema_version"),
        "profile_id": _profile_id(pack_index),
        "runtime_counts": _mapping(_mapping(pack_index.get("runtime")).get("counts")),
        "answer_readiness": _mapping(pack_index.get("answer_readiness")),
        "error": error,
    }


def _runtime_truth_ready(pack_index: Mapping[str, Any]) -> bool:
    reconciliation = _mapping(_mapping(pack_index.get("source_policy")).get("reconciliation"))
    return all(
        reconciliation.get(name) == "runtime_authoritative"
        for name in ("registries", "tags", "recipes")
    )


def _runtime_progression_truth_evidence(pack_index: Mapping[str, Any]) -> Dict[str, Any]:
    reconciliation = _mapping(_mapping(pack_index.get("source_policy")).get("reconciliation"))
    runtime_counts = _mapping(_mapping(pack_index.get("runtime")).get("counts"))
    answer_readiness = _mapping(pack_index.get("answer_readiness"))
    required = ("advancements", "quests", "player_progress", "team_progress", "stages")
    missing = [
        name
        for name in required
        if reconciliation.get(name) != "runtime_authoritative"
    ]
    return {
        "passed": not missing,
        "required_runtime_authoritative": list(required),
        "missing_or_not_runtime_authoritative": missing,
        "reconciliation": dict(reconciliation),
        "runtime_counts": dict(runtime_counts),
        "answer_readiness": dict(answer_readiness),
        "missing_for_full_progression": list(answer_readiness.get("missing_for_full_progression", []))
        if isinstance(answer_readiness.get("missing_for_full_progression"), list)
        else [],
    }


def _runtime_dump_connector_evidence(
    validation: Mapping[str, Any],
    jar_report: Mapping[str, Any],
) -> Dict[str, Any]:
    metadata = _mapping(jar_report.get("metadata"))
    expected_mod_id = _string_or_none(metadata.get("mod_id"))
    expected_version = _string_or_none(metadata.get("mod_version"))
    actual_mod_id = _string_or_none(validation.get("connector_mod_id"))
    actual_version = _string_or_none(validation.get("connector_version"))
    comparable = bool(jar_report.get("valid") and expected_mod_id and expected_version)
    passed = (
        not comparable
        or (
            actual_mod_id == expected_mod_id
            and actual_version == expected_version
        )
    )
    return {
        "passed": passed,
        "comparable": comparable,
        "expected_connector_mod_id": expected_mod_id,
        "expected_connector_version": expected_version,
        "manifest_connector_mod_id": actual_mod_id,
        "manifest_connector_version": actual_version,
    }


def _second_forge_1201_profile_evidence() -> Dict[str, Any]:
    synthetic_pack_id = "second-forge-1201-validation-pack"
    try:
        profiles = load_pack_profiles()
        static_summary = {
            "pack": {"name": "Second Forge 1.20.1 Validation Pack", "version": "0.0.0"},
            "loader": {
                "name": PHASE1_TARGET_LOADER,
                "minecraft_version": PHASE1_TARGET_MINECRAFT,
                "version": "47.4.20",
            },
            "adapter": {
                "pack_id": synthetic_pack_id,
                "loader": PHASE1_TARGET_LOADER,
                "minecraft_version": PHASE1_TARGET_MINECRAFT,
            },
        }
        selected = select_pack_profile(static_summary, profiles)
        adapter = _mapping(selected.adapter)
        passed = (
            selected.profile_id == PHASE1_SECOND_FORGE_PROFILE_ID
            and adapter.get("loader") == PHASE1_TARGET_LOADER
            and adapter.get("minecraft_version") == PHASE1_TARGET_MINECRAFT
        )
        return {
            "passed": passed,
            "profile_ids": [profile.profile_id for profile in profiles],
            "selected_profile_id": selected.profile_id,
            "selected_display_name": selected.display_name,
            "selected_adapter": dict(adapter),
            "synthetic_pack_id": synthetic_pack_id,
            "expected_profile_id": PHASE1_SECOND_FORGE_PROFILE_ID,
        }
    except Exception as exc:  # pragma: no cover - exact loader/parse error is surfaced in the report.
        return {
            "passed": False,
            "profile_ids": [],
            "selected_profile_id": None,
            "synthetic_pack_id": synthetic_pack_id,
            "expected_profile_id": PHASE1_SECOND_FORGE_PROFILE_ID,
            "error": str(exc),
        }


def _answer_source_refs(local_answer: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    answer = _mapping(local_answer.get("answer"))
    refs = answer.get("source_refs")
    if not isinstance(refs, list):
        return []
    return [ref for ref in refs if isinstance(ref, Mapping)]


def _item_source_expectation(instance: Path, dump_dir: Path, item_id: str | None) -> Dict[str, Any]:
    if not item_id:
        return {
            "item_id": None,
            "checked": False,
            "item_present": False,
            "expected_recipe_ids": [],
            "expected_quest_paths": [],
            "expected_runtime_quest_ids": [],
            "expected_static_quest_ids": [],
            "error": None,
        }
    errors: list[str] = []
    item_present = False
    recipe_ids: list[str] = []
    runtime_quest_ids: list[str] = []
    runtime_quest_paths: list[str] = []
    static_quest_ids: list[str] = []
    static_quest_paths: list[str] = []
    try:
        loaded = load_runtime_dump_directory(dump_dir, require_phase1=True)
        runtime_index = runtime_index_from_sections(loaded.sections)
        recipe_ids = sorted(
            recipe.id
            for recipe in runtime_index.recipes
            if recipe.result_item == item_id
        )
        item_present = any(item.id == item_id for item in runtime_index.items)
        for quest in runtime_index.ftb_quests:
            if item_id not in quest.task_item_ids and item_id not in quest.reward_item_ids:
                continue
            runtime_quest_ids.append(quest.quest_id)
            runtime_quest_paths.append(f"{loaded.manifest.dump_id}/ftb_quests#{quest.quest_id}")
    except Exception as exc:  # pragma: no cover - validation errors are already reported separately.
        errors.append(str(exc))
    try:
        quest_summary = inspect_quest_book(instance)
        for chapter in quest_summary.get("chapters", []):
            if not isinstance(chapter, Mapping):
                continue
            source_file = chapter.get("source_file") if isinstance(chapter.get("source_file"), str) else "chapters"
            for quest in chapter.get("quests", []):
                if not isinstance(quest, Mapping) or not _quest_mentions_item_id(quest, item_id):
                    continue
                quest_id = quest.get("id") if isinstance(quest.get("id"), str) and quest.get("id") else "quest"
                static_quest_ids.append(quest_id)
                static_quest_paths.append(f"{source_file}#{quest_id}")
    except ValueError:
        pass
    except Exception as exc:  # pragma: no cover - static quest parsing errors are reported by import/index checks.
        errors.append(str(exc))
    expected_quest_paths = sorted(set(runtime_quest_paths + static_quest_paths))
    return {
        "item_id": item_id,
        "checked": not errors,
        "item_present": item_present,
        "expected_recipe_ids": recipe_ids,
        "expected_quest_paths": expected_quest_paths,
        "expected_runtime_quest_ids": sorted(set(runtime_quest_ids)),
        "expected_static_quest_ids": sorted(set(static_quest_ids)),
        "error": "; ".join(errors) if errors else None,
    }


def _has_runtime_answer_source(source_refs: list[Mapping[str, Any]]) -> bool:
    allowed = {"recipe", "quest", "runtime_dump_section"}
    return any(ref.get("kind") in allowed for ref in source_refs)


def _has_item_specific_answer_source(source_refs: list[Mapping[str, Any]]) -> bool:
    return any(ref.get("kind") in {"recipe", "quest"} for ref in source_refs)


def _answer_source_requirement(
    source_refs: list[Mapping[str, Any]],
    item_id: str | None,
    item_source_expectation: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    if item_id:
        expectation = _mapping(item_source_expectation)
        source_expectation_checked = expectation.get("checked") is True
        item_present = expectation.get("item_present") is True
        expected_recipe_ids = _expected_recipe_ids(item_source_expectation)
        expected_quest_paths = _expected_quest_paths(item_source_expectation)
        recipe_refs = _source_refs_of_kind(source_refs, "recipe")
        matching_recipe_refs = [
            dict(ref)
            for ref in recipe_refs
            if isinstance(ref.get("path"), str) and ref["path"] in expected_recipe_ids
        ]
        quest_refs = _source_refs_of_kind(source_refs, "quest")
        matching_quest_refs = [
            dict(ref)
            for ref in quest_refs
            if isinstance(ref.get("path"), str) and ref["path"] in expected_quest_paths
        ]
        has_item_specific_source = _has_item_specific_answer_source(source_refs)
        if (expected_recipe_ids or expected_quest_paths) and (recipe_refs or quest_refs):
            passed = bool(matching_recipe_refs or matching_quest_refs)
        elif source_expectation_checked and not item_present and not expected_recipe_ids and not expected_quest_paths:
            passed = False
        elif source_expectation_checked and (recipe_refs or quest_refs):
            passed = False
        else:
            passed = has_item_specific_source
        return {
            "kind": "item_specific",
            "required_source_kinds": ["recipe", "quest"],
            "item_id": item_id,
            "source_expectation_checked": source_expectation_checked,
            "item_present": item_present,
            "expected_recipe_ids": expected_recipe_ids,
            "expected_quest_paths": expected_quest_paths,
            "matching_recipe_refs": matching_recipe_refs,
            "matching_quest_refs": matching_quest_refs,
            "recipe_refs": [dict(ref) for ref in recipe_refs],
            "quest_refs": [dict(ref) for ref in quest_refs],
            "passed": passed,
        }
    return {
        "kind": "runtime_context",
        "required_source_kinds": ["recipe", "quest", "runtime_dump_section"],
        "passed": _has_runtime_answer_source(source_refs),
    }


def _expected_recipe_ids(item_source_expectation: Mapping[str, Any] | None) -> list[str]:
    payload = _mapping(item_source_expectation)
    value = payload.get("expected_recipe_ids")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _expected_quest_paths(item_source_expectation: Mapping[str, Any] | None) -> list[str]:
    payload = _mapping(item_source_expectation)
    value = payload.get("expected_quest_paths")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _source_refs_of_kind(source_refs: list[Mapping[str, Any]], kind: str) -> list[Mapping[str, Any]]:
    return [ref for ref in source_refs if ref.get("kind") == kind]


def _quest_mentions_item_id(quest: Mapping[str, Any], item_id: str) -> bool:
    for section_name in ("tasks", "rewards"):
        entries = quest.get(section_name)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, Mapping) and entry.get("item_id") == item_id:
                return True
    return False


def _answer_dump_source_requirement(
    source_refs: list[Mapping[str, Any]],
    dump_id: str | None,
) -> Dict[str, Any]:
    matching_refs = []
    if dump_id:
        expected_prefix = f"{dump_id}/"
        matching_refs = [
            dict(ref)
            for ref in source_refs
            if ref.get("kind") == "runtime_dump_section"
            and isinstance(ref.get("path"), str)
            and ref["path"].startswith(expected_prefix)
        ]
    return {
        "kind": "expected_runtime_dump",
        "expected_dump_id": dump_id,
        "matching_refs": matching_refs,
        "passed": bool(matching_refs),
    }


def _run_agent_import(instance: Path, dump_dir: Path) -> Dict[str, Any]:
    try:
        service = AgentService()
        dump_import = import_runtime_dump_directory(service, dump_dir, require_phase1=True)
        instance_import = import_instance_context(service, instance, str(dump_import["connector_id"]))
        pack_index = service.build_packwise_index(str(dump_import["connector_id"]), str(dump_import["dump_id"]))
        profile = _mapping(pack_index.get("profile"))
        return {
            "passed": bool(dump_import.get("valid")) and profile.get("profile_id") == PHASE1_TARGET_PACK_ID,
            "connector_id": dump_import.get("connector_id"),
            "dump_id": dump_import.get("dump_id"),
            "imported_sections": dump_import.get("imported_sections", []),
            "runtime_index_summary": dump_import.get("runtime_index_summary", {}),
            "instance_import": {
                "valid": instance_import.get("valid"),
                "static_summary": instance_import.get("static_summary", {}),
                "quest_summary": instance_import.get("quest_summary", {}),
            },
            "pack_index": {
                "profile_id": profile.get("profile_id"),
                "runtime": _mapping(pack_index.get("runtime")),
                "answer_readiness": _mapping(pack_index.get("answer_readiness")),
            },
            "error": None,
        }
    except Exception as exc:  # pragma: no cover - exact exception type is surfaced in the report.
        return {
            "passed": False,
            "connector_id": None,
            "dump_id": None,
            "imported_sections": [],
            "runtime_index_summary": {},
            "instance_import": {},
            "pack_index": {},
            "error": str(exc),
        }


def _run_local_answer_scenarios(
    instance: Path,
    dump_dir: Path,
    item_id: str | None,
    expected_dump_id: str | None,
    item_source_expectation: Mapping[str, Any] | None,
) -> list[Dict[str, Any]]:
    results = []
    for scenario in PHASE1_LOCAL_ANSWER_SCENARIOS:
        scenario_item_id = item_id if scenario["use_item"] else None
        try:
            answer_packet = ask_local(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                question=str(scenario["question"]),
                item_id=scenario_item_id,
            )
            refs = _answer_source_refs(answer_packet)
            answer = _mapping(answer_packet.get("answer"))
            source_requirement = _answer_source_requirement(
                refs,
                scenario_item_id,
                item_source_expectation if scenario_item_id else None,
            )
            dump_source_requirement = _answer_dump_source_requirement(refs, expected_dump_id)
            results.append(
                {
                    "id": scenario["id"],
                    "question": scenario["question"],
                    "item_id": scenario_item_id,
                    "passed": source_requirement["passed"] and dump_source_requirement["passed"],
                    "source_requirement": source_requirement,
                    "dump_source_requirement": dump_source_requirement,
                    "summary": answer.get("summary"),
                    "confidence": answer.get("confidence"),
                    "source_refs": refs,
                    "error": None,
                }
            )
        except Exception as exc:  # pragma: no cover - exact exception type is surfaced in the report.
            results.append(
                {
                    "id": scenario["id"],
                    "question": scenario["question"],
                    "item_id": scenario_item_id,
                    "passed": False,
                    "source_requirement": _answer_source_requirement(
                        [],
                        scenario_item_id,
                        item_source_expectation if scenario_item_id else None,
                    ),
                    "dump_source_requirement": _answer_dump_source_requirement([], expected_dump_id),
                    "summary": None,
                    "confidence": None,
                    "source_refs": [],
                    "error": str(exc),
                }
            )
    return results


def _pack_index_summary(pack_index: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": pack_index.get("schema_version"),
        "profile_id": _profile_id(pack_index),
        "identity": _mapping(pack_index.get("identity")),
        "runtime": _mapping(pack_index.get("runtime")),
        "answer_readiness": _mapping(pack_index.get("answer_readiness")),
    }


def _local_answer_summary(local_answer: Mapping[str, Any]) -> Dict[str, Any]:
    answer = _mapping(local_answer.get("answer"))
    return {
        "schema_version": local_answer.get("schema_version"),
        "summary": answer.get("summary"),
        "confidence": answer.get("confidence"),
        "source_refs": answer.get("source_refs", []),
    }
