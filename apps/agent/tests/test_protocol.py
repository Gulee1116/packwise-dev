import unittest

from packwise_agent.protocol import (
    ConnectorHello,
    ConnectorInfo,
    ConnectorSide,
    ProtocolError,
    RuntimeDumpManifest,
    RuntimeDumpSection,
)


class ProtocolTest(unittest.TestCase):
    def test_connector_hello_round_trip(self):
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
                capabilities=[
                    "runtime_dump",
                    "commands",
                    "server_progress",
                    "quest_progress",
                    "stage_state",
                ],
            ),
        )

        encoded = hello.to_dict()
        self.assertEqual("packwise.connector.v1", encoded["protocol"])
        self.assertEqual("connector.hello", encoded["message_type"])
        self.assertEqual("server", encoded["connector"]["side"])

        decoded = ConnectorHello.from_dict(encoded)
        self.assertEqual("msg_0001", decoded.message_id)
        self.assertEqual(ConnectorSide.SERVER, decoded.connector.side)
        self.assertEqual("21.1.233", decoded.connector.loader_version)
        self.assertIn("runtime_dump", decoded.connector.capabilities)

    def test_rejects_wrong_protocol(self):
        payload = {
            "protocol": "packwise.connector.v0",
            "message_type": "connector.hello",
            "message_id": "bad",
            "sent_at": "2026-06-14T08:00:00Z",
            "connector": {
                "id": "c",
                "side": "server",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "minecraft_version": "1.21.1",
                "pack_id": "p",
                "pack_name": "p",
                "pack_version": "1",
                "capabilities": [],
            },
        }
        with self.assertRaises(ProtocolError):
            ConnectorHello.from_dict(payload)

    def test_runtime_dump_manifest_round_trip(self):
        manifest = RuntimeDumpManifest.create(
            message_id="msg_0200",
            sent_at="2026-06-14T08:10:00Z",
            connector_id="stoneblock4-dev-server",
            dump_id="dump_20260614_081000",
            minecraft_version="1.21.1",
            loader="neoforge",
            loader_version="21.1.233",
            sections=[
                RuntimeDumpSection("mods", "application/x-ndjson", 404, "sha-mods"),
                RuntimeDumpSection("recipes", "application/x-ndjson", 8000, "sha-recipes"),
            ],
        )

        encoded = manifest.to_dict()
        self.assertEqual("runtime_dump.manifest", encoded["message_type"])
        self.assertEqual("stoneblock4-dev-server", encoded["connector_id"])
        self.assertEqual("recipes", encoded["sections"][1]["name"])

        decoded = RuntimeDumpManifest.from_dict(encoded)
        self.assertEqual("dump_20260614_081000", decoded.dump_id)
        self.assertEqual(8000, decoded.sections[1].count)


if __name__ == "__main__":
    unittest.main()
