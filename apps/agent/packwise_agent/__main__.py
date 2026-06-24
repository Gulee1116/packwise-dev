from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .http_api import make_server
from .local_workflow import LOCAL_ANSWER_SCHEMA_VERSION, ask_local
from .llm import OpenAICompatibleChatClient
from .phase1_acceptance import build_phase1_acceptance_report
from .service import AgentService
from .ftbquests import inspect_quest_book
from .pack_index import (
    PHASE1_RUNTIME_SECTIONS,
    RUNTIME_SECTIONS,
    build_packwise_index_from_instance,
    runtime_index_from_sections,
)
from .runtime_dump_files import load_runtime_dump_directory, validate_runtime_dump_directory
from .runtime_dump_importer import (
    INSTANCE_IMPORT_SCHEMA_VERSION,
    import_instance_context,
    import_runtime_dump_directory,
    runtime_dump_import_error_report,
)
from .static_inspector import inspect_instance


BUILD_INDEX_ERROR_SCHEMA_VERSION = "packwise.build_index_error.v1"


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "inspect":
        _run_inspect(argv[1:])
        return
    if argv and argv[0] == "inspect-quests":
        _run_inspect_quests(argv[1:])
        return
    if argv and argv[0] == "build-index":
        _run_build_index(argv[1:])
        return
    if argv and argv[0] == "validate-dump":
        _run_validate_dump(argv[1:])
        return
    if argv and argv[0] == "import-dump":
        _run_import_dump(argv[1:])
        return
    if argv and argv[0] == "ask-local":
        _run_ask_local(argv[1:])
        return
    if argv and argv[0] == "phase1-acceptance":
        _run_phase1_acceptance(argv[1:])
        return
    if argv and argv[0] == "serve":
        argv = argv[1:]

    parser = argparse.ArgumentParser(description="Run the Packwise lightweight agent service.")
    parser.add_argument("--host", default=os.environ.get("PACKWISE_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PACKWISE_AGENT_PORT", "8765")))
    parser.add_argument("--model", default=os.environ.get("PACKWISE_LLM_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--enable-llm", action="store_true", help="Call the configured OpenAI-compatible LLM provider.")
    parser.add_argument(
        "--import-dump",
        action="append",
        default=[],
        help="Preload a local runtime dump directory into the in-memory agent before serving.",
    )
    parser.add_argument("--import-instance", help="Preload static/quest context from an installed instance before serving.")
    parser.add_argument("--import-connector-id", help="Override connector id for preloaded dumps.")
    parser.add_argument("--require-phase1-imports", action="store_true", help="Require Phase 1 sections for preloaded dumps.")
    args = parser.parse_args(argv)

    chat_client = OpenAICompatibleChatClient(model=args.model) if args.enable_llm else None
    service = AgentService(model_name=args.model, chat_client=chat_client)
    imported_dump_reports = []
    for runtime_dump_dir in args.import_dump:
        try:
            report = import_runtime_dump_directory(
                service,
                runtime_dump_dir,
                connector_id=args.import_connector_id,
                require_phase1=args.require_phase1_imports,
            )
        except (OSError, ValueError) as error:
            report = runtime_dump_import_error_report(runtime_dump_dir, require_phase1=args.require_phase1_imports)
            errors = report["validation"].setdefault("errors", [])
            if isinstance(errors, list) and str(error) not in errors:
                errors.append(str(error))
            print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
            raise SystemExit(1) from error
        imported_dump_reports.append(report)
        print(
            "Imported runtime dump "
            f"{report['dump_id']} for connector {report['connector_id']} "
            f"({len(report['imported_sections'])} sections)"
        )
    if args.import_instance:
        instance_connector_id = _preload_instance_connector_id(args.import_connector_id, imported_dump_reports)
        report = import_instance_context(service, args.import_instance, instance_connector_id)
        print(
            "Imported instance context "
            f"for connector {report['connector_id']} "
            f"({report['static_summary']['adapter'].get('pack_id') or 'unknown-pack'})"
        )
    server = make_server((args.host, args.port), service)
    print(f"Packwise agent listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping Packwise agent")
    finally:
        server.server_close()


def _run_inspect(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Inspect an installed modpack directory without starting Minecraft.")
    parser.add_argument("path")
    parser.add_argument("--output", "-o", help="Write JSON summary to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    summary = inspect_instance(args.path)
    indent = 2 if args.pretty else None
    text = json.dumps(summary, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)


def _run_inspect_quests(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Inspect FTB Quests SNBT without starting Minecraft.")
    parser.add_argument("path", help="Installed instance directory or config/ftbquests/quests directory.")
    parser.add_argument("--output", "-o", help="Write JSON quest skeleton to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    summary = inspect_quest_book(args.path)
    indent = 2 if args.pretty else None
    text = json.dumps(summary, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)


def _run_build_index(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Build a normalized Packwise index from static sources and runtime dump sections.")
    parser.add_argument("path", help="Installed modpack instance directory.")
    parser.add_argument("--runtime-dir", help="Directory containing runtime section files such as recipes.ndjson.")
    parser.add_argument(
        "--runtime-section",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="Runtime section file override, for example recipes=artifacts/recipes.ndjson.",
    )
    parser.add_argument("--output", "-o", help="Write JSON index to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    parser.add_argument("--require-phase1", action="store_true", help="Require non-empty Phase 1 runtime sections.")
    args = parser.parse_args(argv)

    try:
        sections = _load_runtime_sections(args.runtime_dir, args.runtime_section, require_phase1=args.require_phase1)
        index = build_packwise_index_from_instance(args.path, sections)
        payload = index.to_dict()
    except (OSError, ValueError) as error:
        payload = _build_index_error_report(
            instance_path=args.path,
            runtime_dir=args.runtime_dir,
            section_args=args.runtime_section,
            require_phase1=args.require_phase1,
            error=error,
        )
    indent = 2 if args.pretty else None
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    if not payload.get("valid", True):
        raise SystemExit(1)


def _run_validate_dump(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Validate a local Packwise runtime dump directory.")
    parser.add_argument("path", help="Runtime dump directory containing manifest.json and section files.")
    parser.add_argument("--require-phase1", action="store_true", help="Require all Phase 1 runtime sections.")
    parser.add_argument("--output", "-o", help="Write JSON validation report to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    report = validate_runtime_dump_directory(args.path, require_phase1=args.require_phase1)
    indent = 2 if args.pretty else None
    text = json.dumps(report, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    if not report.get("valid"):
        raise SystemExit(1)


def _run_import_dump(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Validate and import a local runtime dump through AgentService.")
    parser.add_argument("path", help="Runtime dump directory containing manifest.json and section files.")
    parser.add_argument("--instance", help="Installed modpack instance directory to import static/quest context.")
    parser.add_argument("--connector-id", help="Override connector id while importing the dump.")
    parser.add_argument("--require-phase1", action="store_true", help="Require all Phase 1 runtime sections.")
    parser.add_argument("--output", "-o", help="Write JSON import report to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    service = AgentService()
    try:
        report = import_runtime_dump_directory(
            service,
            args.path,
            connector_id=args.connector_id,
            require_phase1=args.require_phase1,
        )
    except (OSError, ValueError) as error:
        report = runtime_dump_import_error_report(args.path, require_phase1=args.require_phase1)
        errors = report["validation"].setdefault("errors", [])
        if isinstance(errors, list) and str(error) not in errors:
            errors.append(str(error))
    else:
        if args.instance:
            try:
                instance_report = import_instance_context(service, args.instance, report["connector_id"])
                pack_index = service.build_packwise_index(report["connector_id"], report["dump_id"])
                report["instance_import"] = instance_report
                report["pack_index"] = _pack_index_report(pack_index)
            except (OSError, ValueError) as error:
                report["valid"] = False
                report["instance_import"] = {
                    "schema_version": INSTANCE_IMPORT_SCHEMA_VERSION,
                    "valid": False,
                    "connector_id": report["connector_id"],
                    "instance_path": args.instance,
                    "errors": [str(error)],
                }
    indent = 2 if args.pretty else None
    text = json.dumps(report, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    if not report.get("valid"):
        raise SystemExit(1)


def _run_ask_local(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Answer a question from a local instance and Packwise runtime dump directory.")
    parser.add_argument("path", help="Installed modpack instance directory.")
    parser.add_argument("--runtime-dir", required=True, help="Runtime dump directory containing manifest.json and section files.")
    parser.add_argument("--question", "-q", required=True, help="Question to answer.")
    parser.add_argument("--item-id", help="Optional item id to anchor recipe/unlock questions.")
    parser.add_argument("--connector-id", help="Override connector id from the runtime dump manifest.")
    parser.add_argument(
        "--allow-partial-runtime",
        action="store_true",
        help="Allow exploratory answers from dumps missing required Phase 1 sections.",
    )
    parser.add_argument("--output", "-o", help="Write JSON answer packet to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    try:
        result = ask_local(
            instance_path=args.path,
            runtime_dump_dir=args.runtime_dir,
            question=args.question,
            item_id=args.item_id,
            connector_id=args.connector_id,
            require_phase1=not args.allow_partial_runtime,
        )
    except (OSError, ValueError) as error:
        result = _ask_local_error_report(
            instance_path=args.path,
            runtime_dump_dir=args.runtime_dir,
            question=args.question,
            connector_id=args.connector_id,
            require_phase1=not args.allow_partial_runtime,
            error=error,
        )
    indent = 2 if args.pretty else None
    text = json.dumps(result, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    if not result.get("valid"):
        raise SystemExit(1)


def _run_phase1_acceptance(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 1 ATM9Sky acceptance evidence report.")
    parser.add_argument("--instance", required=True, help="Installed ATM9Sky instance directory.")
    parser.add_argument("--runtime-dir", required=True, help="Runtime dump directory written by /packwise dump.")
    parser.add_argument("--forge-jar", help="Forge connector jar to verify.")
    parser.add_argument("--server-log", help="ATM9Sky server log captured after /packwise status and /packwise dump.")
    parser.add_argument("--agent-url", help="Optional running agent URL to verify online connector hello and dump state.")
    parser.add_argument("--question", default="当前目标缺哪些前置机器/任务/材料？", help="Basic question to prove local answering.")
    parser.add_argument("--item-id", default="minecraft:stone", help="Optional item id to anchor the local answer.")
    parser.add_argument("--output", "-o", help="Write JSON acceptance report to this file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(argv)

    report = build_phase1_acceptance_report(
        instance_path=args.instance,
        runtime_dump_dir=args.runtime_dir,
        forge_jar=args.forge_jar,
        server_log=args.server_log,
        agent_url=args.agent_url,
        question=args.question,
        item_id=args.item_id,
    )
    indent = 2 if args.pretty else None
    text = json.dumps(report, ensure_ascii=False, indent=indent)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.write("\n")
    else:
        print(text)
    if not report.get("valid"):
        raise SystemExit(1)


def _load_runtime_sections(
    runtime_dir: str | None,
    section_args: list[str],
    require_phase1: bool = False,
) -> dict[str, str]:
    sections: dict[str, str] = {}
    if runtime_dir:
        root = Path(runtime_dir)
        if (root / "manifest.json").is_file():
            sections.update(load_runtime_dump_directory(root, require_phase1=require_phase1).sections)
        else:
            for section in RUNTIME_SECTIONS:
                for candidate in (root / f"{section}.ndjson", root / section):
                    if candidate.is_file():
                        sections[section] = candidate.read_text(encoding="utf-8")
                        break
    for item in section_args:
        if "=" not in item:
            raise SystemExit(f"--runtime-section must be NAME=PATH, got {item}")
        name, path = item.split("=", 1)
        if name not in RUNTIME_SECTIONS:
            raise SystemExit(f"Unsupported runtime section: {name}")
        sections[name] = Path(path).read_text(encoding="utf-8")
    if require_phase1:
        _require_phase1_runtime_sections(sections)
    return sections


def _require_phase1_runtime_sections(sections: dict[str, str]) -> None:
    runtime_summary = runtime_index_from_sections(sections).summary()
    missing = [name for name in PHASE1_RUNTIME_SECTIONS if name not in sections]
    empty = [name for name in PHASE1_RUNTIME_SECTIONS if runtime_summary.get(name, 0) <= 0]
    if missing or empty:
        parts = []
        if missing:
            parts.append("missing=" + ",".join(missing))
        if empty:
            parts.append("empty=" + ",".join(empty))
        raise ValueError("Phase 1 runtime sections are incomplete: " + "; ".join(parts))


def _preload_instance_connector_id(
    configured_connector_id: str | None,
    imported_dump_reports: list[dict[str, object]],
) -> str:
    if configured_connector_id:
        return configured_connector_id
    if len(imported_dump_reports) == 1:
        connector_id = imported_dump_reports[0].get("connector_id")
        if isinstance(connector_id, str) and connector_id:
            return connector_id
    return "local-import"


def _pack_index_report(pack_index: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": pack_index.get("schema_version"),
        "profile": pack_index.get("profile"),
        "identity": pack_index.get("identity"),
        "runtime": pack_index.get("runtime"),
        "answer_readiness": pack_index.get("answer_readiness"),
        "source_policy": pack_index.get("source_policy"),
    }


def _build_index_error_report(
    instance_path: str,
    runtime_dir: str | None,
    section_args: list[str],
    require_phase1: bool,
    error: Exception,
) -> dict[str, object]:
    validation = None
    if runtime_dir and (Path(runtime_dir) / "manifest.json").is_file():
        validation = validate_runtime_dump_directory(runtime_dir, require_phase1=require_phase1)
    error_text = str(error) if str(error) else error.__class__.__name__
    return {
        "schema_version": BUILD_INDEX_ERROR_SCHEMA_VERSION,
        "valid": False,
        "instance_path": str(instance_path),
        "runtime_dump_dir": str(runtime_dir) if runtime_dir else None,
        "runtime_section_args": list(section_args),
        "require_phase1": require_phase1,
        "validation": validation,
        "errors": [error_text],
    }


def _ask_local_error_report(
    instance_path: str,
    runtime_dump_dir: str,
    question: str,
    connector_id: str | None,
    require_phase1: bool,
    error: Exception,
) -> dict[str, object]:
    import_report = runtime_dump_import_error_report(runtime_dump_dir, require_phase1=require_phase1)
    errors = [str(error)] if str(error) else [error.__class__.__name__]
    return {
        "schema_version": LOCAL_ANSWER_SCHEMA_VERSION,
        "valid": False,
        "connector_id": connector_id or import_report.get("connector_id"),
        "dump_id": import_report.get("dump_id"),
        "question": question,
        "runtime_dump_dir": str(runtime_dump_dir),
        "instance_path": str(instance_path),
        "validation": import_report["validation"],
        "import": {
            "schema_version": import_report["schema_version"],
            "manifest_connector_id": import_report["manifest_connector_id"],
            "imported_sections": import_report["imported_sections"],
            "runtime_index_summary": import_report["runtime_index_summary"],
        },
        "instance_import": None,
        "pack_index": None,
        "answer": None,
        "errors": errors,
    }


if __name__ == "__main__":
    main()
