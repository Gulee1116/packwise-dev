import hashlib
import unittest

from packwise_agent.protocol import ConnectorHello, ConnectorInfo, ConnectorSide
from packwise_agent.service import AgentService


class AgentServiceTest(unittest.TestCase):
    def test_connector_hello_returns_ack(self):
        service = AgentService(model_name="deepseek-v4-pro")
        hello = ConnectorHello.create(
            message_id="msg_0001",
            sent_at="2026-06-14T08:00:00Z",
            connector=ConnectorInfo(
                id="stoneblock4-dev-server",
                side=ConnectorSide.SERVER,
                loader="neoforge",
                loader_version="21.1.233",
                minecraft_version="1.21.1",
                pack_id="ftb-stoneblock-4",
                pack_name="FTB StoneBlock 4",
                pack_version="1.14.2",
                capabilities=["runtime_dump", "commands"],
            ),
        )

        ack = service.handle_connector_hello(hello.to_dict())
        self.assertEqual("connector.ack", ack["message_type"])
        self.assertEqual("msg_0001", ack["in_reply_to"])
        self.assertTrue(ack["accepted"])
        self.assertIn("stoneblock4-dev-server", service.connectors)

    def test_ask_returns_answer_packet_shape(self):
        service = AgentService(model_name="deepseek-v4-pro")
        response = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:05:00Z",
                "question": "我下一步该干什么？",
                "locale": "zh_cn",
                "context": {
                    "connector_id": "stoneblock4-dev-server",
                    "server_id": "local-dev",
                    "team_id": "team-main",
                    "known_progress": {"completed_quests": [], "stages": []},
                },
            }
        )

        self.assertEqual("answer.packet", response["message_type"])
        self.assertEqual("msg_0100", response["in_reply_to"])
        answer = response["answer"]
        self.assertTrue(answer["summary"])
        self.assertIsInstance(answer["next_steps"], list)
        self.assertIsInstance(answer["source_refs"], list)
        self.assertEqual("low", answer["confidence"])
        self.assertEqual("deepseek-v4-pro", answer["model"])

    def test_ask_can_use_injected_llm_client(self):
        service = AgentService(model_name="deepseek-v4-pro", chat_client=FakeChatClient("LLM summary"))
        response = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:05:00Z",
                "question": "这个东西从哪来？",
                "locale": "zh_cn",
                "context": {},
            }
        )

        self.assertEqual("LLM summary", response["answer"]["summary"])
        self.assertEqual("deepseek-v4-pro", response["answer"]["model"])

    def test_runtime_dump_manifest_is_stored(self):
        service = AgentService(model_name="deepseek-v4-pro")
        ack = service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
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
            },
        )

        self.assertEqual("runtime_dump.ack", ack["message_type"])
        self.assertEqual("msg_0200", ack["in_reply_to"])
        self.assertIn("dump_20260614_081000", service.runtime_dumps)

    def test_runtime_dump_manifest_rejects_connector_mismatch(self):
        service = AgentService(model_name="deepseek-v4-pro")
        with self.assertRaises(Exception):
            service.handle_runtime_dump_manifest(
                "other-server",
                {
                    "protocol": "packwise.connector.v1",
                    "message_type": "runtime_dump.manifest",
                    "message_id": "msg_0200",
                    "sent_at": "2026-06-14T08:10:00Z",
                    "connector_id": "stoneblock4-dev-server",
                    "dump_id": "dump_20260614_081000",
                    "minecraft_version": "1.21.1",
                    "loader": "neoforge",
                    "loader_version": "21.1.233",
                    "sections": [],
                },
            )

    def test_runtime_dump_section_is_stored_after_manifest(self):
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

        ack = service.handle_runtime_dump_section(
            connector_id="stoneblock4-dev-server",
            dump_id="dump_1",
            section_name="mods",
            content_type="application/x-ndjson",
            body=body,
        )

        self.assertEqual("runtime_dump.section_ack", ack["message_type"])
        self.assertEqual(1, ack["line_count"])
        self.assertEqual(body, service.runtime_dump_sections[("dump_1", "mods")].body)
        self.assertEqual("minecraft", service.runtime_mods["dump_1"][0].mod_id)

    def test_runtime_dump_section_rejects_unknown_section(self):
        service = AgentService(model_name="deepseek-v4-pro")
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
                "sections": [],
            },
        )
        with self.assertRaises(Exception):
            service.handle_runtime_dump_section(
                connector_id="stoneblock4-dev-server",
                dump_id="dump_1",
                section_name="mods",
                content_type="application/x-ndjson",
                body="",
            )

    def test_mods_section_indexes_multiple_mods(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = (
            '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}\n'
            '{"mod_id":"neoforge","display_name":"NeoForge","version":"21.1.233","source":"neoforge:ModList"}\n'
        )
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
                        "count": 2,
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

        mods = service.list_runtime_mods("dump_1")
        self.assertEqual(2, len(mods))
        self.assertEqual("minecraft", mods[0]["mod_id"])
        self.assertEqual("NeoForge", mods[1]["display_name"])

    def test_runtime_dump_section_rejects_sha_mismatch(self):
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
                        "sha256": "0" * 64,
                    }
                ],
            },
        )

        with self.assertRaises(Exception):
            service.handle_runtime_dump_section(
                connector_id="stoneblock4-dev-server",
                dump_id="dump_1",
                section_name="mods",
                content_type="application/x-ndjson",
                body=body,
            )

    def test_runtime_dump_section_rejects_count_mismatch(self):
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
                        "count": 2,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )

        with self.assertRaises(Exception):
            service.handle_runtime_dump_section(
                connector_id="stoneblock4-dev-server",
                dump_id="dump_1",
                section_name="mods",
                content_type="application/x-ndjson",
                body=body,
            )


class FakeChatClient:
    def __init__(self, response):
        self.response = response

    def complete(self, messages):
        self.messages = messages
        return self.response


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
