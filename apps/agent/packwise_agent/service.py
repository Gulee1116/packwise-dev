from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol
from uuid import uuid4

from .llm import ChatMessage
from .protocol import ConnectorHello, PROTOCOL_VERSION, RuntimeDumpManifest, validate_ask
from .runtime_index import RuntimeMod, parse_mods_ndjson


class ChatClient(Protocol):
    def complete(self, messages: list[ChatMessage]) -> str:
        ...


@dataclass(frozen=True)
class RuntimeDumpStoredSection:
    connector_id: str
    dump_id: str
    section_name: str
    content_type: str
    body: str
    line_count: int


class AgentService:
    def __init__(self, model_name: str = "deepseek-v4-pro", chat_client: Optional[ChatClient] = None) -> None:
        self.model_name = model_name
        self.chat_client = chat_client
        self.connectors: Dict[str, ConnectorHello] = {}
        self.runtime_dumps: Dict[str, RuntimeDumpManifest] = {}
        self.runtime_dump_sections: Dict[tuple[str, str], RuntimeDumpStoredSection] = {}
        self.runtime_mods: Dict[str, list[RuntimeMod]] = {}

    def handle_connector_hello(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        hello = ConnectorHello.from_dict(payload)
        self.connectors[hello.connector.id] = hello
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "connector.ack",
            "message_id": _new_message_id("ack"),
            "in_reply_to": hello.message_id,
            "sent_at": _now_iso(),
            "accepted": True,
            "agent": {
                "name": "packwise-agent",
                "capabilities": ["ask", "next_steps", "goal_planning"],
            },
        }

    def handle_ask(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        request = validate_ask(payload)
        answer = self._draft_answer(request["question"], request["context"])
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "answer.packet",
            "message_id": _new_message_id("ans"),
            "in_reply_to": request["message_id"],
            "sent_at": _now_iso(),
            "answer": answer,
        }

    def handle_runtime_dump_manifest(self, connector_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        manifest = RuntimeDumpManifest.from_dict(payload)
        manifest.require_connector_id(connector_id)
        self.runtime_dumps[manifest.dump_id] = manifest
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "runtime_dump.ack",
            "message_id": _new_message_id("dump_ack"),
            "in_reply_to": manifest.message_id,
            "sent_at": _now_iso(),
            "accepted": True,
            "dump_id": manifest.dump_id,
            "section_count": len(manifest.sections),
        }

    def handle_runtime_dump_section(
        self,
        connector_id: str,
        dump_id: str,
        section_name: str,
        content_type: str,
        body: str,
    ) -> Dict[str, Any]:
        manifest = self.runtime_dumps.get(dump_id)
        if manifest is None:
            raise ValueError(f"Unknown runtime dump: {dump_id}")
        manifest.require_connector_id(connector_id)
        expected_section = next((section for section in manifest.sections if section.name == section_name), None)
        if expected_section is None:
            raise ValueError(f"Runtime dump {dump_id} did not declare section {section_name}")
        if expected_section.content_type != content_type:
            raise ValueError(f"Expected content type {expected_section.content_type}, got {content_type}")
        line_count = len([line for line in body.splitlines() if line.strip()])
        if expected_section.count != line_count:
            raise ValueError(f"Section {section_name} count mismatch: expected {expected_section.count}, got {line_count}")
        actual_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if expected_section.sha256 != actual_sha256:
            raise ValueError(f"Section {section_name} sha256 mismatch: expected {expected_section.sha256}, got {actual_sha256}")
        stored = RuntimeDumpStoredSection(
            connector_id=connector_id,
            dump_id=dump_id,
            section_name=section_name,
            content_type=content_type,
            body=body,
            line_count=line_count,
        )
        self.runtime_dump_sections[(dump_id, section_name)] = stored
        if section_name == "mods":
            self.runtime_mods[dump_id] = parse_mods_ndjson(body)
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "runtime_dump.section_ack",
            "message_id": _new_message_id("section_ack"),
            "sent_at": _now_iso(),
            "accepted": True,
            "dump_id": dump_id,
            "section_name": section_name,
            "line_count": line_count,
        }

    def list_runtime_mods(self, dump_id: str) -> list[Dict[str, str]]:
        return [mod.to_dict() for mod in self.runtime_mods.get(dump_id, [])]

    def _draft_answer(self, question: str, context: Mapping[str, Any]) -> Dict[str, Any]:
        connector_id: Optional[str] = context.get("connector_id") if isinstance(context.get("connector_id"), str) else None
        source_refs = []
        if connector_id and connector_id in self.connectors:
            source_refs.append(
                {
                    "kind": "connector",
                    "path": connector_id,
                    "label": self.connectors[connector_id].connector.pack_name,
                }
            )

        if not source_refs:
            source_refs.append(
                {
                    "kind": "protocol",
                    "path": "docs/protocol/CONNECTOR_AGENT_PROTOCOL.md",
                    "label": "Packwise protocol draft",
                }
            )

        summary = self._llm_summary(question, context) if self.chat_client else _fallback_summary(question)

        return {
            "summary": summary,
            "next_steps": [
                "先同步 connector hello 和 runtime dump，确认 Packwise 拿到当前整合包事实。",
                "再基于任务进度、stage 和配方图生成更具体的路线建议。",
            ],
            "source_refs": source_refs,
            "confidence": "low",
            "model": self.model_name,
        }

    def _llm_summary(self, question: str, context: Mapping[str, Any]) -> str:
        assert self.chat_client is not None
        prompt = (
            "你是 Packwise 的早期轻量 harness。"
            "只能基于提供的上下文回答；如果缺 runtime dump 或索引，要明确说明低置信。"
            "\n\n问题："
            + question
            + "\n\n上下文："
            + repr(dict(context))
        )
        return self.chat_client.complete(
            [
                ChatMessage(role="system", content="你是 Minecraft 整合包服务器的只读进度助理。"),
                ChatMessage(role="user", content=prompt),
            ]
        )


def _fallback_summary(question: str) -> str:
    if "下一步" in question or "干什么" in question:
        return "当前轻量 harness 还没有完整进度图；建议先完成 runtime dump，再用任务书和 stage 状态计算下一步。"
    return "当前轻量 harness 已接收问题，但需要检索索引和 runtime dump 后才能给出高置信答案。"


def _new_message_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
