import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from packwise_agent.__main__ import main as cli_main
from packwise_agent.local_workflow import ask_local
from packwise_agent.runtime_dump_files import RuntimeDumpValidationError


class LocalWorkflowTest(unittest.TestCase):
    def test_ask_local_ingests_dump_and_answers_with_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            dump_dir = Path(tmp) / "packwise-dumps" / "dump_1"
            _write_instance(root)
            _write_dump(dump_dir)

            result = ask_local(
                instance_path=str(root),
                runtime_dump_dir=str(dump_dir),
                question="当前目标缺哪些前置机器/任务/材料？",
                item_id="minecraft:stone",
                connector_id="manual-atm9sky",
            )

        self.assertEqual("packwise.local_answer.v1", result["schema_version"])
        self.assertTrue(result["valid"])
        self.assertEqual("manual-atm9sky", result["connector_id"])
        self.assertEqual("atm9sky-dev-server", result["import"]["manifest_connector_id"])
        self.assertTrue(result["validation"]["valid"])
        self.assertEqual([], result["validation"]["empty_phase1_required_sections"])
        self.assertEqual("atm9sky", result["pack_index"]["profile"]["profile_id"])
        self.assertIn("minecraft:cobblestone", result["answer"]["summary"])
        self.assertIn({"kind": "recipe", "path": "minecraft:stonecutting/stone", "label": "minecraft:stone"}, result["answer"]["source_refs"])
        self.assertIn({"kind": "quest", "path": "chapters/start.snbt#quest_start", "label": "Stone Start"}, result["answer"]["source_refs"])

    def test_ask_local_rejects_partial_runtime_dump_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            dump_dir = Path(tmp) / "packwise-dumps" / "dump_1"
            _write_instance(root)
            _write_dump(dump_dir, include_full_phase1=False)

            with self.assertRaises(RuntimeDumpValidationError):
                ask_local(
                    instance_path=str(root),
                    runtime_dump_dir=str(dump_dir),
                    question="当前目标缺哪些前置机器/任务/材料？",
                    item_id="minecraft:stone",
                    connector_id="manual-atm9sky",
                )

    def test_ask_local_can_allow_partial_runtime_dump_for_exploration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            dump_dir = Path(tmp) / "packwise-dumps" / "dump_1"
            _write_instance(root)
            _write_dump(dump_dir, include_full_phase1=False)

            result = ask_local(
                instance_path=str(root),
                runtime_dump_dir=str(dump_dir),
                question="当前目标缺哪些前置机器/任务/材料？",
                item_id="minecraft:stone",
                connector_id="manual-atm9sky",
                require_phase1=False,
            )

        self.assertTrue(result["validation"]["valid"])
        self.assertIn("blocks", result["validation"]["missing_phase1_sections"])
        self.assertIn("minecraft:cobblestone", result["answer"]["summary"])

    def test_ask_local_cli_reports_invalid_dump_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            dump_dir = Path(tmp) / "packwise-dumps" / "dump_1"
            _write_instance(root)
            _write_dump(dump_dir, include_full_phase1=False)
            stdout = io.StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout):
                cli_main(
                    [
                        "ask-local",
                        str(root),
                        "--runtime-dir",
                        str(dump_dir),
                        "--question",
                        "当前目标缺哪些前置机器/任务/材料？",
                        "--item-id",
                        "minecraft:stone",
                        "--pretty",
                    ]
                )

        self.assertEqual(1, raised.exception.code)
        report = json.loads(stdout.getvalue())
        self.assertEqual("packwise.local_answer.v1", report["schema_version"])
        self.assertFalse(report["valid"])
        self.assertFalse(report["validation"]["valid"])
        self.assertIn("mods", report["validation"]["missing_phase1_sections"])
        self.assertIn("Runtime dump validation failed", report["errors"][0])
        self.assertIsNone(report["answer"])

    def test_build_index_cli_allows_partial_runtime_dump_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            dump_dir = Path(tmp) / "packwise-dumps" / "dump_1"
            _write_instance(root)
            _write_dump(dump_dir, include_full_phase1=False)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                cli_main(
                    [
                        "build-index",
                        str(root),
                        "--runtime-dir",
                        str(dump_dir),
                        "--pretty",
                    ]
                )

        index = json.loads(stdout.getvalue())
        self.assertEqual("packwise.index.v1", index["schema_version"])
        self.assertIn("mods", index["runtime"]["missing_phase1_sections"])
        self.assertIn("blocks", index["runtime"]["missing_phase1_sections"])
        self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["recipes"])

    def test_build_index_cli_require_phase1_reports_invalid_dump_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            dump_dir = Path(tmp) / "packwise-dumps" / "dump_1"
            _write_instance(root)
            _write_dump(dump_dir, include_full_phase1=False)
            stdout = io.StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout):
                cli_main(
                    [
                        "build-index",
                        str(root),
                        "--runtime-dir",
                        str(dump_dir),
                        "--require-phase1",
                        "--pretty",
                    ]
                )

        self.assertEqual(1, raised.exception.code)
        report = json.loads(stdout.getvalue())
        self.assertEqual("packwise.build_index_error.v1", report["schema_version"])
        self.assertFalse(report["valid"])
        self.assertTrue(report["require_phase1"])
        self.assertFalse(report["validation"]["valid"])
        self.assertIn("mods", report["validation"]["missing_phase1_sections"])
        self.assertIn("blocks", report["validation"]["empty_phase1_required_sections"])
        self.assertIn("Runtime dump validation failed", report["errors"][0])

    def test_serve_cli_reports_invalid_preloaded_dump_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = Path(tmp) / "packwise-dumps" / "dump_1"
            _write_dump(dump_dir, include_full_phase1=False)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stdout(stdout), redirect_stderr(stderr):
                cli_main(
                    [
                        "serve",
                        "--import-dump",
                        str(dump_dir),
                        "--require-phase1-imports",
                    ]
                )

        self.assertEqual(1, raised.exception.code)
        self.assertEqual("", stdout.getvalue())
        report = json.loads(stderr.getvalue())
        self.assertEqual("packwise.runtime_dump_import.v1", report["schema_version"])
        self.assertFalse(report["valid"])
        self.assertFalse(report["validation"]["valid"])
        self.assertIn("mods", report["validation"]["missing_phase1_sections"])
        self.assertIn("Runtime dump validation failed", report["validation"]["errors"])


def _write_instance(root: Path) -> None:
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
        json.dumps({"modpack": {"name": "All the Mods 9 - To the Sky", "version": "1.1.0"}}),
        encoding="utf-8",
    )
    _touch(root / "mods" / "ftb-quests-forge.jar")
    quests_root = root / "config" / "ftbquests" / "quests"
    chapters = quests_root / "chapters"
    chapters.mkdir(parents=True)
    (quests_root / "data.snbt").write_text('{ version: 13 progression_mode: "flexible" }', encoding="utf-8")
    (chapters / "start.snbt").write_text(
        """
        {
          id: "chapter_start"
          quests: [
            {
              id: "quest_start"
              title: "Stone Start"
              tasks: [{ id: "task_stone" type: "item" item: { id: "minecraft:stone" count: 1 } }]
            }
          ]
        }
        """,
        encoding="utf-8",
    )


def _write_dump(path: Path, include_full_phase1: bool = True) -> None:
    sections = {
        "mods": '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.20.1","source":"runtime:mod_list"}\n',
        "items": (
            '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
            '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
        ),
        "blocks": '{"id":"minecraft:stone","registry":"block","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
        "fluids": '{"id":"minecraft:water","registry":"fluid","namespace":"minecraft","path":"water","source":"runtime:built_in_registry"}\n',
        "tags": '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime:registry_tags"}\n',
        "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
        "advancements": '{"id":"minecraft:story/mine_stone","source":"runtime:server_advancements"}\n',
    }
    if not include_full_phase1:
        for name in ("mods", "blocks", "fluids"):
            sections.pop(name)
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
        "connector_id": "atm9sky-dev-server",
        "dump_id": "dump_1",
        "minecraft_version": "1.20.1",
        "loader": "forge",
        "loader_version": "47.4.20",
        "connector_mod_id": "packwise_connector",
        "connector_version": "0.1.0",
        "sections": manifest_sections,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
