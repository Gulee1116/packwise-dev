from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Mapping, Tuple
from urllib.parse import unquote, urlsplit

from .protocol import PROTOCOL_VERSION, ProtocolError
from .service import AgentService


class PackwiseHttpHandler(BaseHTTPRequestHandler):
    service: AgentService

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/v1/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "protocol": PROTOCOL_VERSION,
                    "service": "packwise-agent",
                },
            )
            return
        connector_match = re.fullmatch(r"/v1/connectors/([^/]+)", path)
        if connector_match:
            connector_id = _path_segment(connector_match.group(1))
            status = self.service.connector_status(connector_id)
            if status is None:
                self._send_json(404, _error("not_found", f"Unknown connector: {connector_id}"))
                return
            self._send_json(200, status)
            return
        scoped_mods_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps/([^/]+)/mods", path)
        if scoped_mods_match:
            connector_id, dump_id = _path_segments(scoped_mods_match.groups())
            if not self.service.has_runtime_dump(connector_id, dump_id):
                self._send_json(404, _unknown_runtime_dump(connector_id, dump_id))
                return
            self._send_json(
                200,
                {
                    "protocol": PROTOCOL_VERSION,
                    "message_type": "runtime_dump.mods",
                    "connector_id": connector_id,
                    "dump_id": dump_id,
                    "mods": self.service.list_runtime_mods(dump_id, connector_id=connector_id),
                },
            )
            return
        scoped_recipes_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps/([^/]+)/recipes", path)
        if scoped_recipes_match:
            connector_id, dump_id = _path_segments(scoped_recipes_match.groups())
            if not self.service.has_runtime_dump(connector_id, dump_id):
                self._send_json(404, _unknown_runtime_dump(connector_id, dump_id))
                return
            self._send_json(
                200,
                {
                    "protocol": PROTOCOL_VERSION,
                    "message_type": "runtime_dump.recipes",
                    "connector_id": connector_id,
                    "dump_id": dump_id,
                    "recipes": self.service.list_runtime_recipes(dump_id, connector_id=connector_id),
                },
            )
            return
        scoped_summary_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps/([^/]+)/index-summary", path)
        if scoped_summary_match:
            connector_id, dump_id = _path_segments(scoped_summary_match.groups())
            if not self.service.has_runtime_dump(connector_id, dump_id):
                self._send_json(404, _unknown_runtime_dump(connector_id, dump_id))
                return
            self._send_json(
                200,
                {
                    "protocol": PROTOCOL_VERSION,
                    "message_type": "runtime_dump.index_summary",
                    "connector_id": connector_id,
                    "dump_id": dump_id,
                    "summary": self.service.runtime_index_summary(dump_id, connector_id=connector_id),
                },
            )
            return
        mods_match = re.fullmatch(r"/v1/runtime-dumps/([^/]+)/mods", path)
        if mods_match:
            dump_id = _path_segment(mods_match.group(1))
            if self._send_unscoped_runtime_dump_error_if_needed(dump_id):
                return
            self._send_json(
                200,
                {
                    "protocol": PROTOCOL_VERSION,
                    "message_type": "runtime_dump.mods",
                    "dump_id": dump_id,
                    "mods": self.service.list_runtime_mods(dump_id),
                },
            )
            return
        recipes_match = re.fullmatch(r"/v1/runtime-dumps/([^/]+)/recipes", path)
        if recipes_match:
            dump_id = _path_segment(recipes_match.group(1))
            if self._send_unscoped_runtime_dump_error_if_needed(dump_id):
                return
            self._send_json(
                200,
                {
                    "protocol": PROTOCOL_VERSION,
                    "message_type": "runtime_dump.recipes",
                    "dump_id": dump_id,
                    "recipes": self.service.list_runtime_recipes(dump_id),
                },
            )
            return
        summary_match = re.fullmatch(r"/v1/runtime-dumps/([^/]+)/index-summary", path)
        if summary_match:
            dump_id = _path_segment(summary_match.group(1))
            if self._send_unscoped_runtime_dump_error_if_needed(dump_id):
                return
            self._send_json(
                200,
                {
                    "protocol": PROTOCOL_VERSION,
                    "message_type": "runtime_dump.index_summary",
                    "dump_id": dump_id,
                    "summary": self.service.runtime_index_summary(dump_id),
                },
            )
            return
        pack_index_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps/([^/]+)/pack-index", path)
        if pack_index_match:
            connector_id, dump_id = _path_segments(pack_index_match.groups())
            if not self.service.has_runtime_dump(connector_id, dump_id):
                self._send_json(404, _unknown_runtime_dump(connector_id, dump_id))
                return
            try:
                pack_index = self.service.build_packwise_index(connector_id, dump_id)
            except ValueError as error:
                self._send_json(400, _error("missing_instance_context", str(error)))
                return
            self._send_json(200, pack_index)
            return
        self._send_json(404, _error("not_found", f"Unknown path: {path}"))

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/v1/connectors/hello":
                payload = self._read_json()
                self._send_json(200, self.service.handle_connector_hello(payload))
                return
            static_match = re.fullmatch(r"/v1/connectors/([^/]+)/static-inspect", path)
            if static_match:
                payload = self._read_json()
                connector_id = _path_segment(static_match.group(1))
                self._send_json(200, self.service.handle_static_inspect(connector_id, payload))
                return
            quest_match = re.fullmatch(r"/v1/connectors/([^/]+)/quest-book", path)
            if quest_match:
                payload = self._read_json()
                connector_id = _path_segment(quest_match.group(1))
                self._send_json(200, self.service.handle_quest_book(connector_id, payload))
                return
            runtime_dump_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps", path)
            if runtime_dump_match:
                payload = self._read_json()
                connector_id = _path_segment(runtime_dump_match.group(1))
                self._send_json(200, self.service.handle_runtime_dump_manifest(connector_id, payload))
                return
            section_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps/([^/]+)/sections/([^/]+)", path)
            if section_match:
                connector_id, dump_id, section_name = _path_segments(section_match.groups())
                content_type = self.headers.get("Content-Type", "")
                body = self._read_text()
                self._send_json(
                    200,
                    self.service.handle_runtime_dump_section(
                        connector_id=connector_id,
                        dump_id=dump_id,
                        section_name=section_name,
                        content_type=content_type,
                        body=body,
                    ),
                )
                return
            if path == "/v1/query/ask":
                payload = self._read_json()
                self._send_json(200, self.service.handle_ask(payload))
                return
            self._send_json(404, _error("not_found", f"Unknown path: {path}"))
        except ProtocolError as error:
            self._send_json(400, _error("protocol_error", str(error)))
        except ValueError as error:
            self._send_json(400, _error("invalid_runtime_dump", str(error)))
        except json.JSONDecodeError as error:
            self._send_json(400, _error("invalid_json", str(error)))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> Mapping[str, Any]:
        raw = self._read_text()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ProtocolError("JSON body must be an object")
        return payload

    def _read_text(self) -> str:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length).decode("utf-8")

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_unscoped_runtime_dump_error_if_needed(self, dump_id: str) -> bool:
        connector_ids = self.service.runtime_dump_connector_ids(dump_id)
        if not connector_ids:
            self._send_json(404, _unknown_unscoped_runtime_dump(dump_id))
            return True
        if len(connector_ids) == 1:
            return False
        self._send_json(409, _ambiguous_runtime_dump(dump_id, connector_ids))
        return True


def make_server(address: Tuple[str, int], service: AgentService) -> ThreadingHTTPServer:
    class Handler(PackwiseHttpHandler):
        pass

    Handler.service = service
    return ThreadingHTTPServer(address, Handler)


def _error(code: str, message: str) -> Dict[str, Any]:
    return {
        "protocol": PROTOCOL_VERSION,
        "message_type": "error",
        "error": {
            "code": code,
            "message": message,
        },
    }


def _unknown_runtime_dump(connector_id: str, dump_id: str) -> Dict[str, Any]:
    return _error("not_found", f"Unknown runtime dump for connector {connector_id}: {dump_id}")


def _unknown_unscoped_runtime_dump(dump_id: str) -> Dict[str, Any]:
    return _error("not_found", f"Unknown runtime dump: {dump_id}")


def _ambiguous_runtime_dump(dump_id: str, connector_ids: list[str]) -> Dict[str, Any]:
    payload = _error(
        "ambiguous_runtime_dump",
        f"Runtime dump {dump_id} belongs to multiple connectors; use a scoped /v1/connectors/<connector_id>/runtime-dumps/{dump_id}/... endpoint.",
    )
    payload["error"]["dump_id"] = dump_id
    payload["error"]["connector_ids"] = list(connector_ids)
    return payload


def _path_segment(segment: str) -> str:
    return unquote(segment)


def _path_segments(segments: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_path_segment(segment) for segment in segments)
