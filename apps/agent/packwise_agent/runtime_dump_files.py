from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from .pack_index import PHASE1_RUNTIME_SECTIONS, RUNTIME_SECTIONS, runtime_index_from_sections
from .protocol import RUNTIME_DUMP_NDJSON_CONTENT_TYPE, RuntimeDumpManifest
from .runtime_index import RuntimePackIndex, runtime_consistency_errors


VALIDATION_SCHEMA_VERSION = "packwise.runtime_dump_validation.v1"
PHASE1_CORE_NON_EMPTY_SECTIONS = ("mods", "items", "tags", "recipes")
PHASE1_REQUIRED_NON_EMPTY_SECTIONS = PHASE1_RUNTIME_SECTIONS


@dataclass(frozen=True)
class RuntimeDumpDirectory:
    path: Path
    manifest: RuntimeDumpManifest
    sections: Dict[str, str]
    report: Dict[str, Any]


def load_runtime_dump_directory(path: str | Path, require_phase1: bool = False) -> RuntimeDumpDirectory:
    root = Path(path)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Runtime dump manifest is missing: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest_payload, Mapping):
        raise ValueError(f"Expected JSON object in {manifest_path}")
    manifest = RuntimeDumpManifest.from_dict(manifest_payload)
    sections: Dict[str, str] = {}
    section_reports = []
    errors = []
    duplicate_sections = _duplicate_section_names(manifest.sections)
    if duplicate_sections:
        errors.append("Duplicate runtime dump sections in manifest: " + ", ".join(duplicate_sections))
    section_path_collisions = _section_path_collisions(manifest.sections)
    if section_path_collisions:
        errors.append(
            "Runtime dump section file path collisions: "
            + "; ".join(
                f"{item['file']} <- {', '.join(item['section_names'])}"
                for item in section_path_collisions
            )
        )
    invalid_content_type_sections = _invalid_runtime_content_types(manifest.sections)
    if invalid_content_type_sections:
        errors.append(
            "Runtime dump sections must use "
            + RUNTIME_DUMP_NDJSON_CONTENT_TYPE
            + ": "
            + ", ".join(
                f"{item['name']}={item['content_type']}" for item in invalid_content_type_sections
            )
        )

    for section in manifest.sections:
        try:
            section_path = _section_path(root, section.name, section.content_type)
        except ValueError as error:
            errors.append(f"Invalid section file path for {section.name}: {error}")
            section_reports.append(_section_report(section.name, section.content_type, False, None, None, None, section.sha256))
            continue
        if not section_path.is_file():
            errors.append(f"Missing section file for {section.name}: {section_path.name}")
            section_reports.append(_section_report(section.name, section.content_type, False, None, None, None, section.sha256))
            continue
        section_bytes = section_path.read_bytes()
        body = section_bytes.decode("utf-8")
        actual_count = _line_count(body)
        actual_sha = hashlib.sha256(section_bytes).hexdigest()
        if actual_count != section.count:
            errors.append(f"Section {section.name} count mismatch: expected {section.count}, got {actual_count}")
        if actual_sha != section.sha256:
            errors.append(f"Section {section.name} sha256 mismatch: expected {section.sha256}, got {actual_sha}")
        sections[section.name] = body
        section_reports.append(
            _section_report(
                section.name,
                section.content_type,
                True,
                len(section_bytes),
                actual_count,
                actual_sha,
                section.sha256,
            )
        )

    missing_phase1 = [name for name in PHASE1_RUNTIME_SECTIONS if name not in sections]
    if require_phase1 and missing_phase1:
        errors.append("Missing phase1 runtime sections: " + ", ".join(missing_phase1))

    runtime_index, parse_errors = _runtime_index_with_parse_errors(sections)
    runtime_summary = runtime_index.summary()
    errors.extend(parse_errors)
    consistency_errors = runtime_consistency_errors(runtime_index)
    errors.extend(consistency_errors)
    empty_phase1_core = [
        name for name in PHASE1_CORE_NON_EMPTY_SECTIONS if runtime_summary.get(name, 0) <= 0
    ]
    empty_phase1_required = [
        name for name in PHASE1_REQUIRED_NON_EMPTY_SECTIONS if runtime_summary.get(name, 0) <= 0
    ]
    if require_phase1 and empty_phase1_required:
        errors.append("Empty phase1 runtime sections: " + ", ".join(empty_phase1_required))

    report = {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "valid": not errors,
        "path": str(root),
        "manifest_path": str(manifest_path),
        "manifest_size_bytes": len(manifest_bytes),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "connector_id": manifest.connector_id,
        "dump_id": manifest.dump_id,
        "minecraft_version": manifest.minecraft_version,
        "loader": manifest.loader,
        "loader_version": manifest.loader_version,
        "connector_mod_id": manifest.connector_mod_id,
        "connector_version": manifest.connector_version,
        "section_count": len(manifest.sections),
        "sections": section_reports,
        "runtime_index_summary": runtime_summary,
        "missing_phase1_sections": missing_phase1,
        "empty_phase1_core_sections": empty_phase1_core,
        "empty_phase1_required_sections": empty_phase1_required,
        "invalid_content_type_sections": invalid_content_type_sections,
        "section_path_collisions": section_path_collisions,
        "runtime_consistency_errors": consistency_errors,
        "errors": errors,
    }
    if errors:
        raise RuntimeDumpValidationError(report)
    return RuntimeDumpDirectory(root, manifest, sections, report)


class RuntimeDumpValidationError(ValueError):
    def __init__(self, report: Mapping[str, Any]) -> None:
        super().__init__("Runtime dump validation failed")
        self.report = dict(report)


def validate_runtime_dump_directory(path: str | Path, require_phase1: bool = False) -> Dict[str, Any]:
    try:
        return load_runtime_dump_directory(path, require_phase1=require_phase1).report
    except RuntimeDumpValidationError as error:
        return dict(error.report)
    except (OSError, ValueError) as error:
        return _invalid_report(Path(path), require_phase1, str(error))


def _section_path(root: Path, section_name: str, content_type: str) -> Path:
    return root / _section_filename(section_name, content_type)


def _section_filename(section_name: str, content_type: str) -> str:
    safe_name = _safe_path_segment(section_name)
    if content_type == RUNTIME_DUMP_NDJSON_CONTENT_TYPE:
        return f"{safe_name}.ndjson"
    return f"{safe_name}.txt"


def _safe_path_segment(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "_-." else "_" for character in value)
    if not safe:
        raise ValueError("path segment must not be empty")
    if safe in (".", ".."):
        raise ValueError("path segment must not resolve to current or parent directory")
    return safe


def _invalid_report(path: Path, require_phase1: bool, error: str) -> Dict[str, Any]:
    runtime_summary = runtime_index_from_sections({}).summary()
    manifest_path = path / "manifest.json"
    manifest_fingerprint = _file_fingerprint(manifest_path)
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "valid": False,
        "path": str(path),
        "manifest_path": str(manifest_path),
        "manifest_size_bytes": manifest_fingerprint["size_bytes"],
        "manifest_sha256": manifest_fingerprint["sha256"],
        "connector_id": None,
        "dump_id": None,
        "minecraft_version": None,
        "loader": None,
        "loader_version": None,
        "connector_mod_id": None,
        "connector_version": None,
        "section_count": 0,
        "sections": [],
        "runtime_index_summary": runtime_summary,
        "missing_phase1_sections": list(PHASE1_RUNTIME_SECTIONS) if require_phase1 else [],
        "empty_phase1_core_sections": list(PHASE1_CORE_NON_EMPTY_SECTIONS) if require_phase1 else [],
        "empty_phase1_required_sections": list(PHASE1_REQUIRED_NON_EMPTY_SECTIONS) if require_phase1 else [],
        "invalid_content_type_sections": [],
        "section_path_collisions": [],
        "runtime_consistency_errors": [],
        "errors": [error],
    }


def _file_fingerprint(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"size_bytes": None, "sha256": None}
    content = path.read_bytes()
    return {
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _line_count(body: str) -> int:
    return len([line for line in body.splitlines() if line.strip()])


def _duplicate_section_names(sections: list[Any]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for section in sections:
        name = getattr(section, "name", None)
        if not isinstance(name, str):
            continue
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    return sorted(duplicates)


def _section_path_collisions(sections: list[Any]) -> list[Dict[str, Any]]:
    by_filename: dict[str, list[str]] = {}
    for section in sections:
        name = getattr(section, "name", None)
        content_type = getattr(section, "content_type", None)
        if not isinstance(name, str) or not isinstance(content_type, str):
            continue
        try:
            filename = _section_filename(name, content_type)
        except ValueError:
            continue
        by_filename.setdefault(filename, []).append(name)
    return [
        {"file": filename, "section_names": names}
        for filename, names in sorted(by_filename.items())
        if len(set(names)) > 1
    ]


def _invalid_runtime_content_types(sections: list[Any]) -> list[Dict[str, str]]:
    invalid = []
    for section in sections:
        name = getattr(section, "name", None)
        content_type = getattr(section, "content_type", None)
        if name in RUNTIME_SECTIONS and content_type != RUNTIME_DUMP_NDJSON_CONTENT_TYPE:
            invalid.append({"name": str(name), "content_type": str(content_type)})
    return invalid


def _runtime_index_with_parse_errors(sections: Mapping[str, str]) -> tuple[RuntimePackIndex, list[str]]:
    runtime_index = RuntimePackIndex.empty()
    errors: list[str] = []
    for section_name in RUNTIME_SECTIONS:
        body = sections.get(section_name)
        if body is None:
            continue
        try:
            runtime_index = runtime_index.with_section(section_name, body)
        except ValueError as error:
            errors.append(f"Runtime section parse error in {section_name}: {error}")
    return runtime_index, errors


def _section_report(
    name: str,
    content_type: str,
    present: bool,
    size_bytes: int | None,
    actual_count: int | None,
    actual_sha256: str | None,
    expected_sha256: str,
) -> Dict[str, Any]:
    return {
        "name": name,
        "content_type": content_type,
        "present": present,
        "size_bytes": size_bytes,
        "count": actual_count,
        "sha256": actual_sha256,
        "expected_sha256": expected_sha256,
    }
