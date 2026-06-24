from __future__ import annotations

from typing import Any, Dict

from .protocol import PROTOCOL_VERSION
from .runtime_dump_importer import import_instance_context, import_runtime_dump_directory
from .service import AgentService


LOCAL_ANSWER_SCHEMA_VERSION = "packwise.local_answer.v1"


def ask_local(
    instance_path: str,
    runtime_dump_dir: str,
    question: str,
    item_id: str | None = None,
    connector_id: str | None = None,
    require_phase1: bool = True,
) -> Dict[str, Any]:
    service = AgentService()
    import_report = import_runtime_dump_directory(
        service,
        runtime_dump_dir,
        connector_id=connector_id,
        require_phase1=require_phase1,
    )
    effective_connector_id = import_report["connector_id"]
    instance_import = import_instance_context(service, instance_path, effective_connector_id)

    context: Dict[str, Any] = {
        "connector_id": effective_connector_id,
        "dump_id": import_report["dump_id"],
    }
    if item_id:
        context["item_id"] = item_id
    response = service.handle_ask(
        {
            "protocol": PROTOCOL_VERSION,
            "message_type": "query.ask",
            "message_id": "msg_local_ask",
            "sent_at": import_report["sent_at"],
            "question": question,
            "locale": "zh_cn",
            "context": context,
        }
    )
    pack_index = service.build_packwise_index(effective_connector_id, import_report["dump_id"])
    return {
        "schema_version": LOCAL_ANSWER_SCHEMA_VERSION,
        "valid": True,
        "connector_id": effective_connector_id,
        "dump_id": import_report["dump_id"],
        "question": question,
        "validation": import_report["validation"],
        "import": {
            "schema_version": import_report["schema_version"],
            "manifest_connector_id": import_report["manifest_connector_id"],
            "imported_sections": import_report["imported_sections"],
            "runtime_index_summary": import_report["runtime_index_summary"],
        },
        "instance_import": {
            "schema_version": instance_import["schema_version"],
            "static_summary": instance_import["static_summary"],
            "quest_summary": instance_import["quest_summary"],
        },
        "pack_index": {
            "profile": pack_index["profile"],
            "identity": pack_index["identity"],
            "runtime": pack_index["runtime"],
            "answer_readiness": pack_index["answer_readiness"],
        },
        "answer": response["answer"],
    }
