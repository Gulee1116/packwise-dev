import json
import hashlib
import threading
import unittest
import urllib.error
from urllib.parse import quote
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

    def test_connector_status_endpoint_reports_hello_and_runtime_dumps(self):
        service = AgentService(model_name="deepseek-v4-pro")
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            _post_json(
                f"{base}/v1/connectors/hello",
                {
                    "protocol": "packwise.connector.v1",
                    "message_type": "connector.hello",
                    "message_id": "msg_0001",
                    "sent_at": "2026-06-14T08:00:00Z",
                    "connector": {
                        "id": "atm9sky-dev-server",
                        "side": "server",
                        "loader": "forge",
                        "loader_version": "47.4.20",
                        "minecraft_version": "1.20.1",
                        "pack_id": "atm9sky",
                        "pack_name": "All the Mods 9 - To the Sky",
                        "pack_version": "1.1.0",
                        "capabilities": ["runtime_dump", "commands"],
                    },
                },
            )
            _upload_sections(
                service,
                "atm9sky-dev-server",
                "dump_1",
                {
                    "recipes": '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
                    "tags": '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime:registry_tags"}\n',
                },
            )

            with urllib.request.urlopen(f"{base}/v1/connectors/atm9sky-dev-server", timeout=5) as response:
                status = json.loads(response.read().decode("utf-8"))

            self.assertEqual("connector.status", status["message_type"])
            self.assertTrue(status["hello_present"])
            self.assertEqual("msg_0001", status["hello"]["message_id"])
            self.assertEqual("forge", status["connector"]["loader"])
            self.assertEqual("atm9sky", status["connector"]["pack_id"])
            self.assertFalse(status["static_inspect_present"])
            self.assertEqual("dump_1", status["runtime_dumps"][0]["dump_id"])
            self.assertEqual("packwise_connector", status["runtime_dumps"][0]["connector_mod_id"])
            self.assertEqual("0.1.0", status["runtime_dumps"][0]["connector_version"])
            self.assertEqual(2, status["runtime_dumps"][0]["section_count"])
            self.assertEqual(["recipes", "tags"], status["runtime_dumps"][0]["declared_sections"])
            self.assertEqual(["recipes", "tags"], status["runtime_dumps"][0]["uploaded_sections"])
            self.assertEqual(2, status["runtime_dumps"][0]["uploaded_section_count"])
            self.assertEqual([], status["runtime_dumps"][0]["missing_sections"])
            self.assertEqual([], status["runtime_dumps"][0]["extra_sections"])
            self.assertTrue(status["runtime_dumps"][0]["upload_complete"])
            self.assertEqual(1, status["runtime_dumps"][0]["indexed_summary"]["recipes"])
            self.assertEqual(1, status["runtime_dumps"][0]["indexed_summary"]["tags"])
            self.assertEqual([], status["runtime_dumps"][0]["runtime_consistency_errors"])
        finally:
            server.shutdown()
            server.server_close()

    def test_connector_status_endpoint_reports_incomplete_runtime_dump_upload(self):
        service = AgentService(model_name="deepseek-v4-pro")
        service.handle_runtime_dump_manifest(
            "atm9sky-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_partial",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "connector_mod_id": "packwise_connector",
                "connector_version": "0.1.0",
                "sections": [
                    {"name": "recipes", "content_type": "application/x-ndjson", "count": 1, "sha256": "sha-recipes"},
                    {"name": "tags", "content_type": "application/x-ndjson", "count": 1, "sha256": "sha-tags"},
                ],
            },
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(f"{base}/v1/connectors/atm9sky-dev-server", timeout=5) as response:
                status = json.loads(response.read().decode("utf-8"))

            runtime_dump = status["runtime_dumps"][0]
            self.assertEqual("dump_partial", runtime_dump["dump_id"])
            self.assertEqual(["recipes", "tags"], runtime_dump["declared_sections"])
            self.assertEqual([], runtime_dump["uploaded_sections"])
            self.assertEqual(0, runtime_dump["uploaded_section_count"])
            self.assertEqual(["recipes", "tags"], runtime_dump["missing_sections"])
            self.assertFalse(runtime_dump["upload_complete"])
        finally:
            server.shutdown()
            server.server_close()

    def test_connector_status_endpoint_rejects_unknown_connector(self):
        service = AgentService(model_name="deepseek-v4-pro")
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(f"{base}/v1/connectors/missing-connector", timeout=5)

            self.assertEqual(404, raised.exception.code)
            error = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual("not_found", error["error"]["code"])
            self.assertIn("Unknown connector: missing-connector", error["error"]["message"])
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

    def test_runtime_dump_manifest_endpoint_rejects_duplicate_sections(self):
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
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_duplicate",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "sections": [
                    {
                        "name": "recipes",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": "sha-recipes-a",
                    },
                    {
                        "name": "recipes",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": "sha-recipes-b",
                    },
                ],
            }
            request = urllib.request.Request(
                f"{base}/v1/connectors/atm9sky-dev-server/runtime-dumps",
                data=json.dumps(manifest).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=5)

            self.assertEqual(400, raised.exception.code)
            error = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual("invalid_runtime_dump", error["error"]["code"])
            self.assertIn("Duplicate runtime dump sections in manifest: recipes", error["error"]["message"])
            self.assertNotIn("dump_duplicate", service.runtime_dumps)
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

    def test_scoped_endpoints_decode_percent_encoded_connector_and_dump_ids(self):
        service = AgentService(model_name="deepseek-v4-pro")
        connector_id = "forge:alpha/one"
        dump_id = "dump 1"
        recipes = '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n'
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            encoded_connector = quote(connector_id, safe="")
            encoded_dump = quote(dump_id, safe="")
            _post_json(
                f"{base}/v1/connectors/{encoded_connector}/runtime-dumps",
                {
                    "protocol": "packwise.connector.v1",
                    "message_type": "runtime_dump.manifest",
                    "message_id": "msg_0200",
                    "sent_at": "2026-06-14T08:10:00Z",
                    "connector_id": connector_id,
                    "dump_id": dump_id,
                    "minecraft_version": "1.20.1",
                    "loader": "forge",
                    "loader_version": "47.4.20",
                    "sections": [
                        {
                            "name": "recipes",
                            "content_type": "application/x-ndjson",
                            "count": 1,
                            "sha256": _sha256(recipes),
                        }
                    ],
                },
            )
            request = urllib.request.Request(
                f"{base}/v1/connectors/{encoded_connector}/runtime-dumps/{encoded_dump}/sections/recipes",
                data=recipes.encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                ack = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                f"{base}/v1/connectors/{encoded_connector}/runtime-dumps/{encoded_dump}/recipes",
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual("runtime_dump.section_ack", ack["message_type"])
            self.assertEqual(connector_id, payload["connector_id"])
            self.assertEqual(dump_id, payload["dump_id"])
            self.assertEqual("minecraft:stone", payload["recipes"][0]["result_item"])
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

    def test_runtime_dump_recipes_query_endpoint(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n'
        service.handle_runtime_dump_manifest(
            "atm9sky-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "sections": [
                    {
                        "name": "recipes",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )
        service.handle_runtime_dump_section(
            connector_id="atm9sky-dev-server",
            dump_id="dump_1",
            section_name="recipes",
            content_type="application/x-ndjson",
            body=body,
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(f"{base}/v1/runtime-dumps/dump_1/recipes", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual("runtime_dump.recipes", payload["message_type"])
            self.assertEqual("minecraft:stone", payload["recipes"][0]["result_item"])
        finally:
            server.shutdown()
            server.server_close()

    def test_connector_scoped_runtime_dump_query_endpoints(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "forge-alpha",
            "dump_shared",
            {
                "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
            },
        )
        _upload_sections(
            service,
            "forge-beta",
            "dump_shared",
            {
                "recipes": '{"id":"minecraft:crafting/dirt","type":"minecraft:crafting","serializer":"minecraft:crafting_shapeless","result_item":"minecraft:dirt","result_count":1,"source":"runtime"}\n',
            },
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(
                f"{base}/v1/connectors/forge-alpha/runtime-dumps/dump_shared/recipes",
                timeout=5,
            ) as response:
                alpha_recipes = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                f"{base}/v1/connectors/forge-beta/runtime-dumps/dump_shared/recipes",
                timeout=5,
            ) as response:
                beta_recipes = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(
                f"{base}/v1/connectors/forge-alpha/runtime-dumps/dump_shared/index-summary",
                timeout=5,
            ) as response:
                alpha_summary = json.loads(response.read().decode("utf-8"))

            self.assertEqual("forge-alpha", alpha_recipes["connector_id"])
            self.assertEqual("minecraft:stone", alpha_recipes["recipes"][0]["result_item"])
            self.assertEqual("forge-beta", beta_recipes["connector_id"])
            self.assertEqual("minecraft:dirt", beta_recipes["recipes"][0]["result_item"])
            self.assertEqual("forge-alpha", alpha_summary["connector_id"])
            self.assertEqual(1, alpha_summary["summary"]["recipes"])
        finally:
            server.shutdown()
            server.server_close()

    def test_unscoped_runtime_dump_query_rejects_ambiguous_dump_id(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "forge-alpha",
            "dump_shared",
            {
                "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
            },
        )
        _upload_sections(
            service,
            "forge-beta",
            "dump_shared",
            {
                "recipes": '{"id":"minecraft:crafting/dirt","type":"minecraft:crafting","serializer":"minecraft:crafting_shapeless","result_item":"minecraft:dirt","result_count":1,"source":"runtime"}\n',
            },
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(f"{base}/v1/runtime-dumps/dump_shared/recipes", timeout=5)

            self.assertEqual(409, raised.exception.code)
            error = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual("ambiguous_runtime_dump", error["error"]["code"])
            self.assertEqual("dump_shared", error["error"]["dump_id"])
            self.assertEqual(["forge-alpha", "forge-beta"], error["error"]["connector_ids"])
            self.assertIn("/v1/connectors/<connector_id>/runtime-dumps/dump_shared", error["error"]["message"])

            with urllib.request.urlopen(
                f"{base}/v1/connectors/forge-alpha/runtime-dumps/dump_shared/recipes",
                timeout=5,
            ) as response:
                alpha_recipes = json.loads(response.read().decode("utf-8"))
            self.assertEqual("minecraft:stone", alpha_recipes["recipes"][0]["result_item"])
        finally:
            server.shutdown()
            server.server_close()

    def test_unscoped_runtime_dump_query_rejects_unknown_dump_id(self):
        service = AgentService(model_name="deepseek-v4-pro")
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(f"{base}/v1/runtime-dumps/missing_dump/recipes", timeout=5)

            self.assertEqual(404, raised.exception.code)
            error = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual("not_found", error["error"]["code"])
            self.assertIn("Unknown runtime dump: missing_dump", error["error"]["message"])
        finally:
            server.shutdown()
            server.server_close()

    def test_connector_scoped_runtime_dump_query_rejects_unknown_connector_dump_pair(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "forge-alpha",
            "dump_shared",
            {
                "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
            },
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(
                    f"{base}/v1/connectors/forge-beta/runtime-dumps/dump_shared/recipes",
                    timeout=5,
                )

            self.assertEqual(404, raised.exception.code)
            error = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual("not_found", error["error"]["code"])
            self.assertIn("Unknown runtime dump for connector forge-beta: dump_shared", error["error"]["message"])
        finally:
            server.shutdown()
            server.server_close()

    def test_static_quest_and_pack_index_endpoints(self):
        service = AgentService(model_name="deepseek-v4-pro")
        recipes = '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n'
        service.handle_runtime_dump_manifest(
            "atm9sky-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "sections": [
                    {"name": "recipes", "content_type": "application/x-ndjson", "count": 1, "sha256": _sha256(recipes)}
                ],
            },
        )
        service.handle_runtime_dump_section("atm9sky-dev-server", "dump_1", "recipes", "application/x-ndjson", recipes)
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            _post_json(f"{base}/v1/connectors/atm9sky-dev-server/static-inspect", _static_summary())
            _post_json(f"{base}/v1/connectors/atm9sky-dev-server/quest-book", _quest_summary())
            with urllib.request.urlopen(
                f"{base}/v1/connectors/atm9sky-dev-server/runtime-dumps/dump_1/pack-index",
                timeout=5,
            ) as response:
                index = json.loads(response.read().decode("utf-8"))
            self.assertEqual("packwise.index.v1", index["schema_version"])
            self.assertEqual("atm9sky", index["profile"]["profile_id"])
            self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["recipes"])
            self.assertEqual("static_preload_needs_runtime_progress", index["source_policy"]["reconciliation"]["quests"])
        finally:
            server.shutdown()
            server.server_close()

    def test_pack_index_endpoint_can_use_connector_hello_as_minimal_context(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "atm9sky-dev-server",
            "dump_1",
            {
                "items": '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
                "recipes": '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
            },
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            _post_json(
                f"{base}/v1/connectors/hello",
                {
                    "protocol": "packwise.connector.v1",
                    "message_type": "connector.hello",
                    "message_id": "msg_0001",
                    "sent_at": "2026-06-14T08:00:00Z",
                    "connector": {
                        "id": "atm9sky-dev-server",
                        "side": "server",
                        "loader": "forge",
                        "loader_version": "47.4.20",
                        "minecraft_version": "1.20.1",
                        "pack_id": "atm9sky",
                        "pack_name": "All the Mods 9 - To the Sky",
                        "pack_version": "1.1.0",
                        "capabilities": ["runtime_dump", "commands"],
                    },
                },
            )
            with urllib.request.urlopen(
                f"{base}/v1/connectors/atm9sky-dev-server/runtime-dumps/dump_1/pack-index",
                timeout=5,
            ) as response:
                index = json.loads(response.read().decode("utf-8"))

            self.assertEqual("atm9sky", index["profile"]["profile_id"])
            self.assertEqual("atm9sky", index["identity"]["pack_id"])
            self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["recipes"])
            self.assertTrue(index["answer_readiness"]["recipe_questions"])
        finally:
            server.shutdown()
            server.server_close()

    def test_pack_index_endpoint_requires_static_or_connector_context(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "atm9sky-dev-server",
            "dump_1",
            {
                "recipes": '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
            },
        )
        server = make_server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(
                    f"{base}/v1/connectors/atm9sky-dev-server/runtime-dumps/dump_1/pack-index",
                    timeout=5,
                )

            self.assertEqual(400, raised.exception.code)
            error = json.loads(raised.exception.read().decode("utf-8"))
            self.assertEqual("missing_instance_context", error["error"]["code"])
            self.assertIn("No static inspect or connector hello available", error["error"]["message"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _upload_sections(service, connector_id, dump_id, sections):
    service.handle_runtime_dump_manifest(
        connector_id,
        {
            "protocol": "packwise.connector.v1",
            "message_type": "runtime_dump.manifest",
            "message_id": "msg_0200",
            "sent_at": "2026-06-14T08:10:00Z",
            "connector_id": connector_id,
            "dump_id": dump_id,
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "loader_version": "47.4.20",
            "connector_mod_id": "packwise_connector",
            "connector_version": "0.1.0",
            "sections": [
                {
                    "name": name,
                    "content_type": "application/x-ndjson",
                    "count": len([line for line in body.splitlines() if line.strip()]),
                    "sha256": _sha256(body),
                }
                for name, body in sections.items()
            ],
        },
    )
    for name, body in sections.items():
        service.handle_runtime_dump_section(connector_id, dump_id, name, "application/x-ndjson", body)


def _static_summary():
    return {
        "schema_version": "packwise.static_inspect.v1",
        "path": "/tmp/atm9sky",
        "pack": {"name": "All the Mods 9 - To the Sky", "version": "1.1.0", "translation_language": None},
        "loader": {"minecraft_version": "1.20.1", "name": "forge", "version": "47.4.20"},
        "adapter": {
            "pack_id": "all-the-mods-9-to-the-sky",
            "loader": "forge",
            "minecraft_version": "1.20.1",
            "quest_mod": "ftbquests",
            "known_progression_sources": ["advancements", "ftbquests", "kubejs"],
            "source_inventory": {},
            "optional_integrations": {"ftb_quests": {"present": True}},
        },
        "counts": {},
    }


def _quest_summary():
    return {
        "schema_version": "packwise.ftbquests.v1",
        "path": "/tmp/atm9sky/config/ftbquests/quests",
        "counts": {"chapters": 1, "quests": 1, "tasks": 1, "rewards": 0, "dependency_edges": 0},
        "stages": [],
        "chapters": [],
    }
