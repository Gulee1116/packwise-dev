import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from packwise_agent.runtime_dump_files import (
    RuntimeDumpValidationError,
    load_runtime_dump_directory,
    validate_runtime_dump_directory,
)


class RuntimeDumpFilesTest(unittest.TestCase):
    def test_loads_and_validates_phase1_runtime_dump_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", _phase1_sections())

            loaded = load_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertEqual("dump_1", loaded.manifest.dump_id)
        self.assertTrue(loaded.report["valid"])
        self.assertEqual(str(dump_dir / "manifest.json"), loaded.report["manifest_path"])
        self.assertGreater(loaded.report["manifest_size_bytes"], 0)
        self.assertRegex(loaded.report["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual([], loaded.report["missing_phase1_sections"])
        self.assertEqual([], loaded.report["empty_phase1_core_sections"])
        self.assertEqual([], loaded.report["empty_phase1_required_sections"])
        self.assertEqual([], loaded.report["runtime_consistency_errors"])
        self.assertEqual(1, loaded.report["runtime_index_summary"]["recipes"])
        self.assertIn("recipes", loaded.sections)
        section_reports = {section["name"]: section for section in loaded.report["sections"]}
        self.assertEqual(len(_phase1_sections()["recipes"].encode("utf-8")), section_reports["recipes"]["size_bytes"])
        self.assertRegex(section_reports["recipes"]["sha256"], r"^[0-9a-f]{64}$")

    def test_validation_report_captures_sha_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", {"recipes": _phase1_sections()["recipes"]})
            (dump_dir / "recipes.ndjson").write_text('{"id":"minecraft:changed"}\n', encoding="utf-8")

            report = validate_runtime_dump_directory(dump_dir)

        self.assertFalse(report["valid"])
        self.assertIn("sha256 mismatch", report["errors"][0])

    def test_loads_non_ndjson_section_with_writer_filename_convention(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", {})
            body = "diagnostic note\n"
            (dump_dir / "diagnostic_notes.txt").write_text(body, encoding="utf-8")
            manifest_path = dump_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sections"].append(
                {
                    "name": "diagnostic/notes",
                    "content_type": "text/plain",
                    "count": 1,
                    "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                }
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            loaded = load_runtime_dump_directory(dump_dir)

        self.assertEqual(body, loaded.sections["diagnostic/notes"])
        self.assertTrue(loaded.report["valid"])
        self.assertEqual("diagnostic/notes", loaded.report["sections"][0]["name"])
        self.assertEqual("text/plain", loaded.report["sections"][0]["content_type"])

    def test_validation_report_rejects_standard_runtime_section_with_non_ndjson_content_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", _phase1_sections())
            recipes_body = (dump_dir / "recipes.ndjson").read_text(encoding="utf-8")
            (dump_dir / "recipes.txt").write_text(recipes_body, encoding="utf-8")
            (dump_dir / "recipes.ndjson").unlink()
            manifest_path = dump_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            recipe_section = next(section for section in manifest["sections"] if section["name"] == "recipes")
            recipe_section["content_type"] = "text/plain"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual([], report["missing_phase1_sections"])
        self.assertEqual(1, report["runtime_index_summary"]["recipes"])
        self.assertEqual([{"name": "recipes", "content_type": "text/plain"}], report["invalid_content_type_sections"])
        self.assertTrue(any("recipes=text/plain" in error for error in report["errors"]))

    def test_validation_report_preserves_manifest_context_for_unsafe_section_path_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", {})
            manifest_path = dump_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sections"].append(
                {
                    "name": "..",
                    "content_type": "text/plain",
                    "count": 1,
                    "sha256": hashlib.sha256(b"diagnostic note\n").hexdigest(),
                }
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = validate_runtime_dump_directory(dump_dir)

        self.assertFalse(report["valid"])
        self.assertEqual("atm9sky-dev-server", report["connector_id"])
        self.assertEqual("dump_1", report["dump_id"])
        self.assertEqual(1, report["section_count"])
        self.assertEqual("..", report["sections"][0]["name"])
        self.assertFalse(report["sections"][0]["present"])
        self.assertIsNone(report["sections"][0]["size_bytes"])
        self.assertTrue(any("current or parent directory" in error for error in report["errors"]))

    def test_validation_report_rejects_duplicate_manifest_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", _phase1_sections())
            manifest_path = dump_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            recipe_section = next(section for section in manifest["sections"] if section["name"] == "recipes")
            manifest["sections"].append(dict(recipe_section))
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual("atm9sky-dev-server", report["connector_id"])
        self.assertEqual("dump_1", report["dump_id"])
        self.assertTrue(any("Duplicate runtime dump sections in manifest: recipes" in error for error in report["errors"]))
        self.assertEqual(8, report["section_count"])
        self.assertEqual(8, len(report["sections"]))

    def test_validation_report_rejects_section_file_path_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", {})
            body = "diagnostic note\n"
            (dump_dir / "diagnostic_notes.txt").write_text(body, encoding="utf-8")
            manifest_path = dump_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for name in ("diagnostic/notes", "diagnostic_notes"):
                manifest["sections"].append(
                    {
                        "name": name,
                        "content_type": "text/plain",
                        "count": 1,
                        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                    }
                )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = validate_runtime_dump_directory(dump_dir)

        self.assertFalse(report["valid"])
        self.assertEqual(
            [{"file": "diagnostic_notes.txt", "section_names": ["diagnostic/notes", "diagnostic_notes"]}],
            report["section_path_collisions"],
        )
        self.assertTrue(any("diagnostic_notes.txt <- diagnostic/notes, diagnostic_notes" in error for error in report["errors"]))

    def test_validation_report_captures_missing_manifest_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = Path(tmp) / "missing_dump"

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertIsNone(report["dump_id"])
        self.assertEqual(str(dump_dir / "manifest.json"), report["manifest_path"])
        self.assertIsNone(report["manifest_size_bytes"])
        self.assertIsNone(report["manifest_sha256"])
        self.assertEqual(0, report["runtime_index_summary"]["recipes"])
        self.assertIn("manifest is missing", report["errors"][0])
        self.assertIn("mods", report["missing_phase1_sections"])

    def test_validation_report_captures_malformed_manifest_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = Path(tmp) / "dump_1"
            dump_dir.mkdir()
            (dump_dir / "manifest.json").write_text("{not json", encoding="utf-8")

            report = validate_runtime_dump_directory(dump_dir)

        self.assertFalse(report["valid"])
        self.assertIsNone(report["connector_id"])
        self.assertEqual(str(dump_dir / "manifest.json"), report["manifest_path"])
        self.assertGreater(report["manifest_size_bytes"], 0)
        self.assertRegex(report["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(report["errors"])

    def test_validation_report_preserves_manifest_context_for_malformed_ndjson(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["recipes"] = '{"id":"minecraft:stone"\n'
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual("atm9sky-dev-server", report["connector_id"])
        self.assertEqual("dump_1", report["dump_id"])
        self.assertEqual("forge", report["loader"])
        self.assertEqual(7, report["section_count"])
        self.assertEqual(7, len(report["sections"]))
        self.assertTrue(any("Runtime section parse error" in error for error in report["errors"]))
        self.assertTrue(any("recipes line 1" in error for error in report["errors"]))
        self.assertEqual(1, report["runtime_index_summary"]["mods"])
        self.assertEqual(1, report["runtime_index_summary"]["items"])
        self.assertEqual(1, report["runtime_index_summary"]["tags"])
        self.assertEqual(0, report["runtime_index_summary"]["recipes"])
        self.assertEqual(["recipes"], report["empty_phase1_core_sections"])
        self.assertEqual(["recipes"], report["empty_phase1_required_sections"])

    def test_validation_report_preserves_manifest_context_for_invalid_section_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["tags"] = '{"registry":"item","tag":"forge:stone","entry_count":-1,"entries":["minecraft:stone"],"source":"runtime"}\n'
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual("atm9sky-dev-server", report["connector_id"])
        self.assertEqual("dump_1", report["dump_id"])
        self.assertTrue(any("entry_count must be a non-negative integer" in error for error in report["errors"]))
        self.assertEqual(1, report["runtime_index_summary"]["mods"])
        self.assertEqual(1, report["runtime_index_summary"]["items"])
        self.assertEqual(0, report["runtime_index_summary"]["tags"])
        self.assertEqual(1, report["runtime_index_summary"]["recipes"])
        self.assertEqual(["tags"], report["empty_phase1_core_sections"])
        self.assertEqual(["tags"], report["empty_phase1_required_sections"])

    def test_validation_report_rejects_recipe_refs_missing_from_item_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["recipes"] = (
                '{"id":"packwise:bad_recipe","type":"minecraft:crafting",'
                '"serializer":"minecraft:crafting_shaped","result_item":"minecraft:dirt",'
                '"result_count":1,"ingredient_items":["minecraft:diamond"],"source":"runtime"}\n'
            )
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual([], report["empty_phase1_required_sections"])
        self.assertIn(
            "Recipe result items missing from items registry: minecraft:dirt",
            report["runtime_consistency_errors"],
        )
        self.assertIn(
            "Recipe ingredient items missing from items registry: minecraft:diamond",
            report["runtime_consistency_errors"],
        )

    def test_validation_report_rejects_tag_refs_missing_from_runtime_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["tags"] = (
                '{"registry":"item","tag":"forge:stone","entry_count":2,'
                '"entries":["minecraft:stone"],"source":"runtime"}\n'
                '{"registry":"block","tag":"minecraft:bad","entry_count":1,'
                '"entries":["minecraft:missing_block"],"source":"runtime"}\n'
            )
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual([], report["empty_phase1_required_sections"])
        self.assertIn(
            "Tag item:forge:stone entry_count mismatch: expected 2, got 1 entries",
            report["runtime_consistency_errors"],
        )
        self.assertIn(
            "Tag block:minecraft:bad entries missing from block registry: minecraft:missing_block",
            report["runtime_consistency_errors"],
        )

    def test_validation_report_rejects_optional_progression_inconsistency(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["ftb_quests"] = (
                '{"quest_id":"quest_root","chapter_id":null,"title":"Root",'
                '"dependencies":[],"task_item_ids":["minecraft:stone"],'
                '"reward_item_ids":[],"source":"runtime:ftb_quests"}\n'
                '{"quest_id":"quest_bad","chapter_id":null,"title":"Bad",'
                '"dependencies":["quest_missing"],"task_item_ids":["minecraft:missing_task"],'
                '"reward_item_ids":[],"source":"runtime:ftb_quests"}\n'
            )
            sections["player_progress"] = (
                '{"subject_type":"player","subject_id":"player-1",'
                '"completed_quests":["quest_unknown"],"completed_advancements":[],'
                '"stages":["missing_stage"],"source":"runtime:ftb_quests",'
                '"player_name":"DevPlayer"}\n'
            )
            sections["stages"] = (
                '{"subject_type":"player","subject_id":"player-1","stage":"stone_age",'
                '"active":true,"source":"runtime:gamestages","player_name":"DevPlayer"}\n'
            )
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual([], report["empty_phase1_required_sections"])
        self.assertIn(
            "FTB quest task items missing from items registry: minecraft:missing_task",
            report["runtime_consistency_errors"],
        )
        self.assertIn(
            "FTB quest dependencies missing from ftb_quests: quest_missing",
            report["runtime_consistency_errors"],
        )
        self.assertIn(
            "Player progress completed quests missing from ftb_quests: quest_unknown",
            report["runtime_consistency_errors"],
        )
        self.assertIn(
            "Player progress stages missing from stages section: player-1:missing_stage",
            report["runtime_consistency_errors"],
        )

    def test_validation_report_keeps_core_counts_when_optional_section_is_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["ftb_quests"] = '{"quest_id":"quest_start"\n'
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual("atm9sky-dev-server", report["connector_id"])
        self.assertEqual([], report["empty_phase1_core_sections"])
        self.assertEqual(1, report["runtime_index_summary"]["mods"])
        self.assertEqual(1, report["runtime_index_summary"]["items"])
        self.assertEqual(1, report["runtime_index_summary"]["tags"])
        self.assertEqual(1, report["runtime_index_summary"]["recipes"])
        self.assertEqual(0, report["runtime_index_summary"]["ftb_quests"])
        self.assertTrue(any("Runtime section parse error in ftb_quests" in error for error in report["errors"]))

    def test_loader_raises_validation_error_for_invalid_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", {"recipes": _phase1_sections()["recipes"]})
            (dump_dir / "recipes.ndjson").write_text('{"id":"minecraft:changed"}\n', encoding="utf-8")

            with self.assertRaises(RuntimeDumpValidationError):
                load_runtime_dump_directory(dump_dir)

    def test_require_phase1_reports_missing_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_dir = _write_dump(Path(tmp) / "dump_1", {"recipes": _phase1_sections()["recipes"]})

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertIn("mods", report["missing_phase1_sections"])
        self.assertTrue(any("Missing phase1 runtime sections" in error for error in report["errors"]))

    def test_require_phase1_reports_empty_core_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["recipes"] = ""
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual(["recipes"], report["empty_phase1_core_sections"])
        self.assertEqual(["recipes"], report["empty_phase1_required_sections"])
        self.assertTrue(any("Empty phase1 runtime sections" in error for error in report["errors"]))

    def test_require_phase1_reports_empty_non_core_required_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            sections = dict(_phase1_sections())
            sections["blocks"] = ""
            dump_dir = _write_dump(Path(tmp) / "dump_1", sections)

            report = validate_runtime_dump_directory(dump_dir, require_phase1=True)

        self.assertFalse(report["valid"])
        self.assertEqual([], report["empty_phase1_core_sections"])
        self.assertEqual(["blocks"], report["empty_phase1_required_sections"])
        self.assertTrue(any("Empty phase1 runtime sections: blocks" in error for error in report["errors"]))


def _write_dump(path: Path, sections: dict[str, str]) -> Path:
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
        "dump_id": path.name,
        "minecraft_version": "1.20.1",
        "loader": "forge",
        "loader_version": "47.4.20",
        "connector_mod_id": "packwise_connector",
        "connector_version": "0.1.0",
        "sections": manifest_sections,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _phase1_sections():
    return {
        "mods": '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.20.1","source":"builtin"}\n',
        "items": '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime"}\n',
        "blocks": '{"id":"minecraft:stone","registry":"block","namespace":"minecraft","path":"stone","source":"runtime"}\n',
        "fluids": '{"id":"minecraft:water","registry":"fluid","namespace":"minecraft","path":"water","source":"runtime"}\n',
        "tags": '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime"}\n',
        "recipes": '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
        "advancements": '{"id":"minecraft:story/mine_stone","source":"runtime"}\n',
    }


if __name__ == "__main__":
    unittest.main()
