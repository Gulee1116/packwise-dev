from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from .ftbquests import inspect_quest_book
from .runtime_dump_files import load_runtime_dump_directory, validate_runtime_dump_directory
from .service import AgentService
from .static_inspector import inspect_instance


IMPORT_SCHEMA_VERSION = "packwise.runtime_dump_import.v1"
INSTANCE_IMPORT_SCHEMA_VERSION = "packwise.instance_context_import.v1"


def import_runtime_dump_directory(
    service: AgentService,
    runtime_dump_dir: str | Path,
    connector_id: str | None = None,
    require_phase1: bool = False,
) -> Dict[str, Any]:
    loaded = load_runtime_dump_directory(runtime_dump_dir, require_phase1=require_phase1)
    effective_connector_id = connector_id or loaded.manifest.connector_id
    manifest_payload = loaded.manifest.to_dict()
    manifest_payload["connector_id"] = effective_connector_id
    manifest_ack = service.handle_runtime_dump_manifest(effective_connector_id, manifest_payload)

    imported_sections = []
    skipped_sections = []
    section_acks = []
    for section in loaded.manifest.sections:
        body = loaded.sections.get(section.name)
        if body is None:
            skipped_sections.append(section.name)
            continue
        section_acks.append(
            service.handle_runtime_dump_section(
                connector_id=effective_connector_id,
                dump_id=loaded.manifest.dump_id,
                section_name=section.name,
                content_type=section.content_type,
                body=body,
            )
        )
        imported_sections.append(section.name)

    return {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "connector_id": effective_connector_id,
        "manifest_connector_id": loaded.manifest.connector_id,
        "dump_id": loaded.manifest.dump_id,
        "sent_at": loaded.manifest.sent_at,
        "runtime_dump_dir": str(loaded.path),
        "valid": loaded.report["valid"],
        "manifest_ack": manifest_ack,
        "imported_sections": imported_sections,
        "skipped_sections": skipped_sections,
        "section_acks": section_acks,
        "runtime_index_summary": service.runtime_index_summary(
            loaded.manifest.dump_id,
            connector_id=effective_connector_id,
        ),
        "validation": loaded.report,
    }


def runtime_dump_import_error_report(
    runtime_dump_dir: str | Path,
    require_phase1: bool = False,
) -> Dict[str, Any]:
    validation = validate_runtime_dump_directory(runtime_dump_dir, require_phase1=require_phase1)
    return {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "connector_id": validation.get("connector_id"),
        "manifest_connector_id": validation.get("connector_id"),
        "dump_id": validation.get("dump_id"),
        "sent_at": None,
        "runtime_dump_dir": str(Path(runtime_dump_dir)),
        "valid": False,
        "manifest_ack": None,
        "imported_sections": [],
        "skipped_sections": [],
        "section_acks": [],
        "runtime_index_summary": validation.get("runtime_index_summary", {}),
        "validation": validation,
    }


def import_instance_context(
    service: AgentService,
    instance_path: str | Path,
    connector_id: str,
) -> Dict[str, Any]:
    static_summary = inspect_instance(instance_path)
    static_ack = service.handle_static_inspect(connector_id, static_summary)
    quest_summary = _try_inspect_quests(instance_path)
    quest_ack = service.handle_quest_book(connector_id, quest_summary) if quest_summary is not None else None
    return {
        "schema_version": INSTANCE_IMPORT_SCHEMA_VERSION,
        "valid": True,
        "connector_id": connector_id,
        "instance_path": str(Path(instance_path)),
        "static_ack": static_ack,
        "quest_ack": quest_ack,
        "static_summary": _static_summary_report(static_summary),
        "quest_summary": _quest_summary_report(quest_summary),
    }


def _try_inspect_quests(instance_path: str | Path) -> Mapping[str, Any] | None:
    try:
        return inspect_quest_book(instance_path)
    except ValueError:
        return None


def _static_summary_report(summary: Mapping[str, Any]) -> Dict[str, Any]:
    pack = summary.get("pack") if isinstance(summary.get("pack"), Mapping) else {}
    loader = summary.get("loader") if isinstance(summary.get("loader"), Mapping) else {}
    adapter = summary.get("adapter") if isinstance(summary.get("adapter"), Mapping) else {}
    counts = summary.get("counts") if isinstance(summary.get("counts"), Mapping) else {}
    source_inventory = adapter.get("source_inventory") if isinstance(adapter.get("source_inventory"), Mapping) else {}
    optional_integrations = (
        adapter.get("optional_integrations")
        if isinstance(adapter.get("optional_integrations"), Mapping)
        else {}
    )
    return {
        "pack": dict(pack),
        "loader": dict(loader),
        "adapter": {
            "pack_id": adapter.get("pack_id"),
            "loader": adapter.get("loader"),
            "minecraft_version": adapter.get("minecraft_version"),
            "quest_mod": adapter.get("quest_mod"),
            "known_progression_sources": adapter.get("known_progression_sources", []),
            "source_inventory": dict(source_inventory),
            "optional_integrations": dict(optional_integrations),
        },
        "counts": dict(counts),
    }


def _quest_summary_report(summary: Mapping[str, Any] | None) -> Dict[str, Any]:
    if summary is None:
        return {"present": False}
    counts = summary.get("counts") if isinstance(summary.get("counts"), Mapping) else {}
    return {
        "present": True,
        "counts": dict(counts),
    }
