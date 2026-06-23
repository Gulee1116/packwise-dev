from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping


PROTOCOL_VERSION = "packwise.connector.v1"


class ProtocolError(ValueError):
    pass


class ConnectorSide(Enum):
    CLIENT = "client"
    SERVER = "server"
    CLIENT_SERVER = "client_server"


@dataclass(frozen=True)
class ConnectorInfo:
    id: str
    side: ConnectorSide
    loader: str
    loader_version: str
    minecraft_version: str
    pack_id: str
    pack_name: str
    pack_version: str
    capabilities: List[str]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConnectorInfo":
        return cls(
            id=_require_str(payload, "id"),
            side=ConnectorSide(_require_str(payload, "side")),
            loader=_require_str(payload, "loader"),
            loader_version=_require_str(payload, "loader_version"),
            minecraft_version=_require_str(payload, "minecraft_version"),
            pack_id=_require_str(payload, "pack_id"),
            pack_name=_require_str(payload, "pack_name"),
            pack_version=_require_str(payload, "pack_version"),
            capabilities=_require_str_list(payload, "capabilities"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "side": self.side.value,
            "loader": self.loader,
            "loader_version": self.loader_version,
            "minecraft_version": self.minecraft_version,
            "pack_id": self.pack_id,
            "pack_name": self.pack_name,
            "pack_version": self.pack_version,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class ConnectorHello:
    protocol: str
    message_type: str
    message_id: str
    sent_at: str
    connector: ConnectorInfo

    @classmethod
    def create(cls, message_id: str, sent_at: str, connector: ConnectorInfo) -> "ConnectorHello":
        return cls(
            protocol=PROTOCOL_VERSION,
            message_type="connector.hello",
            message_id=message_id,
            sent_at=sent_at,
            connector=connector,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConnectorHello":
        _require_protocol(payload)
        message_type = _require_str(payload, "message_type")
        if message_type != "connector.hello":
            raise ProtocolError(f"Expected message_type connector.hello, got {message_type}")
        connector_payload = payload.get("connector")
        if not isinstance(connector_payload, Mapping):
            raise ProtocolError("connector must be an object")
        return cls(
            protocol=PROTOCOL_VERSION,
            message_type=message_type,
            message_id=_require_str(payload, "message_id"),
            sent_at=_require_str(payload, "sent_at"),
            connector=ConnectorInfo.from_dict(connector_payload),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol": self.protocol,
            "message_type": self.message_type,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
            "connector": self.connector.to_dict(),
        }


@dataclass(frozen=True)
class RuntimeDumpSection:
    name: str
    content_type: str
    count: int
    sha256: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeDumpSection":
        count = payload.get("count")
        if not isinstance(count, int) or count < 0:
            raise ProtocolError("count must be a non-negative integer")
        return cls(
            name=_require_str(payload, "name"),
            content_type=_require_str(payload, "content_type"),
            count=count,
            sha256=_require_str(payload, "sha256"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "content_type": self.content_type,
            "count": self.count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class RuntimeDumpManifest:
    protocol: str
    message_type: str
    message_id: str
    sent_at: str
    connector_id: str
    dump_id: str
    minecraft_version: str
    loader: str
    loader_version: str
    sections: List[RuntimeDumpSection]

    @classmethod
    def create(
        cls,
        message_id: str,
        sent_at: str,
        connector_id: str,
        dump_id: str,
        minecraft_version: str,
        loader: str,
        loader_version: str,
        sections: List[RuntimeDumpSection],
    ) -> "RuntimeDumpManifest":
        return cls(
            protocol=PROTOCOL_VERSION,
            message_type="runtime_dump.manifest",
            message_id=message_id,
            sent_at=sent_at,
            connector_id=connector_id,
            dump_id=dump_id,
            minecraft_version=minecraft_version,
            loader=loader,
            loader_version=loader_version,
            sections=list(sections),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeDumpManifest":
        _require_protocol(payload)
        message_type = _require_str(payload, "message_type")
        if message_type != "runtime_dump.manifest":
            raise ProtocolError(f"Expected message_type runtime_dump.manifest, got {message_type}")
        sections_payload = payload.get("sections")
        if not isinstance(sections_payload, list):
            raise ProtocolError("sections must be a list")
        sections = []
        for item in sections_payload:
            if not isinstance(item, Mapping):
                raise ProtocolError("each section must be an object")
            sections.append(RuntimeDumpSection.from_dict(item))
        return cls(
            protocol=PROTOCOL_VERSION,
            message_type=message_type,
            message_id=_require_str(payload, "message_id"),
            sent_at=_require_str(payload, "sent_at"),
            connector_id=_require_str(payload, "connector_id"),
            dump_id=_require_str(payload, "dump_id"),
            minecraft_version=_require_str(payload, "minecraft_version"),
            loader=_require_str(payload, "loader"),
            loader_version=_require_str(payload, "loader_version"),
            sections=sections,
        )

    def require_connector_id(self, expected_connector_id: str) -> None:
        if self.connector_id != expected_connector_id:
            raise ProtocolError(f"Expected connector_id {expected_connector_id}, got {self.connector_id}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol": self.protocol,
            "message_type": self.message_type,
            "message_id": self.message_id,
            "sent_at": self.sent_at,
            "connector_id": self.connector_id,
            "dump_id": self.dump_id,
            "minecraft_version": self.minecraft_version,
            "loader": self.loader,
            "loader_version": self.loader_version,
            "sections": [section.to_dict() for section in self.sections],
        }


def validate_ask(payload: Mapping[str, Any]) -> Dict[str, Any]:
    _require_protocol(payload)
    message_type = _require_str(payload, "message_type")
    if message_type != "query.ask":
        raise ProtocolError(f"Expected message_type query.ask, got {message_type}")
    question = _require_str(payload, "question")
    if not question.strip():
        raise ProtocolError("question must not be empty")
    return {
        "message_id": _require_str(payload, "message_id"),
        "sent_at": _require_str(payload, "sent_at"),
        "question": question,
        "locale": str(payload.get("locale", "zh_cn")),
        "context": dict(payload.get("context") or {}),
    }


def _require_protocol(payload: Mapping[str, Any]) -> None:
    protocol = _require_str(payload, "protocol")
    if protocol != PROTOCOL_VERSION:
        raise ProtocolError(f"Expected protocol {PROTOCOL_VERSION}, got {protocol}")


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{key} must be a non-empty string")
    return value


def _require_str_list(payload: Mapping[str, Any], key: str) -> List[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ProtocolError(f"{key} must be a string list")
    return list(value)
