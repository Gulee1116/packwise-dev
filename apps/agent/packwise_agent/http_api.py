from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Mapping, Tuple

from .protocol import PROTOCOL_VERSION, ProtocolError
from .service import AgentService


class PackwiseHttpHandler(BaseHTTPRequestHandler):
    service: AgentService

    def do_GET(self) -> None:
        if self.path == "/v1/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "protocol": PROTOCOL_VERSION,
                    "service": "packwise-agent",
                },
            )
            return
        mods_match = re.fullmatch(r"/v1/runtime-dumps/([^/]+)/mods", self.path)
        if mods_match:
            dump_id = mods_match.group(1)
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
        self._send_json(404, _error("not_found", f"Unknown path: {self.path}"))

    def do_POST(self) -> None:
        try:
            if self.path == "/v1/connectors/hello":
                payload = self._read_json()
                self._send_json(200, self.service.handle_connector_hello(payload))
                return
            runtime_dump_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps", self.path)
            if runtime_dump_match:
                payload = self._read_json()
                connector_id = runtime_dump_match.group(1)
                self._send_json(200, self.service.handle_runtime_dump_manifest(connector_id, payload))
                return
            section_match = re.fullmatch(r"/v1/connectors/([^/]+)/runtime-dumps/([^/]+)/sections/([^/]+)", self.path)
            if section_match:
                connector_id, dump_id, section_name = section_match.groups()
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
            if self.path == "/v1/query/ask":
                payload = self._read_json()
                self._send_json(200, self.service.handle_ask(payload))
                return
            self._send_json(404, _error("not_found", f"Unknown path: {self.path}"))
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
