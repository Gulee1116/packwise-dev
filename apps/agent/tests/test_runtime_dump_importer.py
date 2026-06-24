import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from packwise_agent.runtime_dump_importer import (
    import_instance_context,
    import_runtime_dump_directory,
    runtime_dump_import_error_report,
)
from packwise_agent.service import AgentService


class RuntimeDumpImporterTest(unittest.TestCase):
    def test_imports_runtime_dump_through_agent_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1")
            service = AgentService()

            report = import_runtime_dump_directory(service, dump_dir, require_phase1=True)

        self.assertEqual("packwise.runtime_dump_import.v1", report["schema_version"])
        self.assertTrue(report["valid"])
        self.assertEqual("atm9sky-dev-server", report["connector_id"])
        self.assertEqual("atm9sky-dev-server", service.runtime_dumps["dump_1"].connector_id)
        self.assertEqual(["mods", "items", "blocks", "fluids", "tags", "recipes", "advancements"], report["imported_sections"])
        self.assertEqual(1, report["runtime_index_summary"]["recipes"])
        self.assertEqual("minecraft:stone", service.list_runtime_recipes("dump_1")[0]["result_item"])

    def test_import_can_override_connector_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1")
            service = AgentService()

            report = import_runtime_dump_directory(service, dump_dir, connector_id="manual-atm9sky")

        self.assertEqual("manual-atm9sky", report["connector_id"])
        self.assertEqual("atm9sky-dev-server", report["manifest_connector_id"])
        self.assertEqual("manual-atm9sky", service.runtime_dumps["dump_1"].connector_id)

    def test_import_report_uses_connector_scoped_runtime_summary_for_reused_dump_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha_dump = _write_dump(
                root / "alpha" / "dump_shared",
                connector_id="forge-alpha",
                dump_id="dump_shared",
                recipe_results=["minecraft:stone"],
            )
            beta_dump = _write_dump(
                root / "beta" / "dump_shared",
                connector_id="forge-beta",
                dump_id="dump_shared",
                recipe_results=["minecraft:dirt", "minecraft:gravel"],
            )
            service = AgentService()

            alpha_report = import_runtime_dump_directory(service, alpha_dump)
            beta_report = import_runtime_dump_directory(service, beta_dump)

        self.assertEqual(1, alpha_report["runtime_index_summary"]["recipes"])
        self.assertEqual(2, beta_report["runtime_index_summary"]["recipes"])
        self.assertEqual(1, service.runtime_index_summary("dump_shared", connector_id="forge-alpha")["recipes"])
        self.assertEqual(2, service.runtime_index_summary("dump_shared", connector_id="forge-beta")["recipes"])
        self.assertEqual(
            "minecraft:stone",
            service.list_runtime_recipes("dump_shared", connector_id="forge-alpha")[0]["result_item"],
        )
        self.assertEqual(
            "minecraft:dirt",
            service.list_runtime_recipes("dump_shared", connector_id="forge-beta")[0]["result_item"],
        )

    def test_import_error_report_reuses_validation_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = Path(tmp) / "missing_dump"

            report = runtime_dump_import_error_report(dump_dir, require_phase1=True)

        self.assertEqual("packwise.runtime_dump_import.v1", report["schema_version"])
        self.assertFalse(report["valid"])
        self.assertEqual([], report["imported_sections"])
        self.assertIsNone(report["manifest_ack"])
        self.assertFalse(report["validation"]["valid"])
        self.assertIn("mods", report["validation"]["missing_phase1_sections"])

    def test_imported_second_forge_pack_builds_generic_pack_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "Second Forge Pack"
            dump_dir = _write_dump(root / "packwise-dumps" / "dump_1")
            _write_instance(instance, "Second Forge Pack")
            service = AgentService()

            dump_report = import_runtime_dump_directory(service, dump_dir)
            instance_report = import_instance_context(service, instance, dump_report["connector_id"])
            pack_index = service.build_packwise_index(dump_report["connector_id"], dump_report["dump_id"])

        self.assertEqual("packwise.instance_context_import.v1", instance_report["schema_version"])
        self.assertTrue(instance_report["valid"])
        self.assertEqual("second-forge-pack", instance_report["static_summary"]["adapter"]["pack_id"])
        self.assertIn("source_inventory", instance_report["static_summary"]["adapter"])
        self.assertIn("optional_integrations", instance_report["static_summary"]["adapter"])
        self.assertIn("mods", instance_report["static_summary"]["adapter"]["source_inventory"])
        self.assertEqual("generic-forge-1201", pack_index["profile"]["profile_id"])
        self.assertEqual("runtime_authoritative", pack_index["source_policy"]["reconciliation"]["recipes"])
        self.assertTrue(pack_index["answer_readiness"]["recipe_questions"])


def _write_dump(
    path: Path,
    connector_id: str = "atm9sky-dev-server",
    dump_id: str = "dump_1",
    recipe_results: list[str] | None = None,
) -> Path:
    recipe_results = recipe_results or ["minecraft:stone"]
    recipe_lines = []
    for index, result_item in enumerate(recipe_results):
        recipe_lines.append(
            json.dumps(
                {
                    "id": f"minecraft:stonecutting/{result_item.split(':', 1)[-1]}_{index}",
                    "type": "minecraft:stonecutting",
                    "serializer": "minecraft:stonecutting",
                    "result_item": result_item,
                    "result_count": 1,
                    "ingredient_items": ["minecraft:cobblestone"],
                    "source": "runtime:recipe_manager",
                },
                separators=(",", ":"),
            )
        )
    item_lines = []
    for item_id in sorted(set(["minecraft:cobblestone", "minecraft:stone", *recipe_results])):
        namespace, path_name = item_id.split(":", 1)
        item_lines.append(
            json.dumps(
                {
                    "id": item_id,
                    "registry": "item",
                    "namespace": namespace,
                    "path": path_name,
                    "source": "runtime:built_in_registry",
                },
                separators=(",", ":"),
            )
        )
    sections = {
        "mods": '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.20.1","source":"runtime:mod_list"}\n',
        "items": "\n".join(item_lines) + "\n",
        "blocks": '{"id":"minecraft:stone","registry":"block","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
        "fluids": '{"id":"minecraft:water","registry":"fluid","namespace":"minecraft","path":"water","source":"runtime:built_in_registry"}\n',
        "tags": '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime:registry_tags"}\n',
        "recipes": "\n".join(recipe_lines) + "\n",
        "advancements": '{"id":"minecraft:story/mine_stone","source":"runtime:server_advancements"}\n',
    }
    path.mkdir(parents=True)
    manifest_sections = []
    for name, body in sections.items():
        (path / f"{name}.ndjson").write_text(body, encoding="utf-8")
        manifest_sections.append(
            {
                "name": name,
                "content_type": "application/x-ndjson",
                "count": len([line for line in body.splitlines() if line.strip()]),
                "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    manifest = {
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
        "sections": manifest_sections,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_instance(root: Path, name: str) -> None:
    (root / "PCL").mkdir(parents=True)
    (root / "PCL" / "Setup.ini").write_text(
        "\n".join(
            [
                "VersionVanillaName:1.20.1",
                "VersionForge:47.4.20",
                "VersionArgumentIndieV2:True",
            ]
        ),
        encoding="utf-8",
    )
    (root / "modpackinfo.json").write_text(
        json.dumps({"modpack": {"name": name, "version": "2.0.0"}}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
