import json
import hashlib
import threading
import unittest
import urllib.request

from packwise_agent.http_api import make_server
from packwise_agent.service import AgentService


class HttpApiTest(unittest.TestCase):
    def test_health_and_connector_hello(self):
        server = make_server(("127.0.0.1", 0), AgentService(model_name="deepseek-v4-pro"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(f"{base}/v1/health", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertEqual("ok", health["status"])

            hello = {
                "protocol": "packwise.connector.v1",
                "message_type": "connector.hello",
                "message_id": "msg_0001",
                "sent_at": "2026-06-14T08:00:00Z",
                "connector": {
                    "id": "stoneblock4-dev-server",
                    "side": "server",
                    "loader": "neoforge",
                    "loader_version": "21.1.233",
                    "minecraft_version": "1.21.1",
                    "pack_id": "ftb-stoneblock-4",
                    "pack_name": "FTB StoneBlock 4",
                    "pack_version": "1.14.2",
                    "capabilities": ["runtime_dump"],
                },
            }
            request = urllib.request.Request(
                f"{base}/v1/connectors/hello",
                data=json.dumps(hello).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                ack = json.loads(response.read().decode("utf-8"))
            self.assertEqual("connector.ack", ack["message_type"])
            self.assertEqual("msg_0001", ack["in_reply_to"])
        finally:
            server.shutdown()
            server.server_close()

    def test_runtime_dump_manifest_endpoint(self):
        service = AgentService(model_name="deepseek-v4-pro")
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            manifest = {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_20260614_081000",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 404,
                        "sha256": "sha-mods",
                    }
                ],
            }
            request = urllib.request.Request(
                f"{base}/v1/connectors/stoneblock4-dev-server/runtime-dumps",
                data=json.dumps(manifest).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                ack = json.loads(response.read().decode("utf-8"))
            self.assertEqual("runtime_dump.ack", ack["message_type"])
            self.assertIn("dump_20260614_081000", service.runtime_dumps)
        finally:
            server.shutdown()
            server.server_close()

    def test_runtime_dump_section_endpoint(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}\n'
        service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            request = urllib.request.Request(
                f"{base}/v1/connectors/stoneblock4-dev-server/runtime-dumps/dump_1/sections/mods",
                data=body.encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                ack = json.loads(response.read().decode("utf-8"))
            self.assertEqual("runtime_dump.section_ack", ack["message_type"])
            self.assertIn(("dump_1", "mods"), service.runtime_dump_sections)
        finally:
            server.shutdown()
            server.server_close()

    def test_runtime_dump_mods_query_endpoint(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}\n'
        service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )
        service.handle_runtime_dump_section(
            connector_id="stoneblock4-dev-server",
            dump_id="dump_1",
            section_name="mods",
            content_type="application/x-ndjson",
            body=body,
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(f"{base}/v1/runtime-dumps/dump_1/mods", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual("runtime_dump.mods", payload["message_type"])
            self.assertEqual("minecraft", payload["mods"][0]["mod_id"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
