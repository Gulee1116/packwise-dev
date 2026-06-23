import json
import tempfile
import unittest
from pathlib import Path

from packwise_agent.static_inspector import inspect_instance


class StaticInspectorTest(unittest.TestCase):
    def test_inspects_pcl2_instance_without_reading_runtime_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "FTB StoneBlock 4"
            (root / "PCL").mkdir(parents=True)
            (root / "PCL" / "Setup.ini").write_text(
                "\n".join(
                    [
                        "VersionVanillaName:1.21.1",
                        "VersionNeoForge:21.1.233",
                        "VersionArgumentIndieV2:True",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "modpackinfo.json").write_text(
                json.dumps({"modpack": {"name": "StoneBlock Test", "version": "1.0.0"}}),
                encoding="utf-8",
            )
            (root / "FTB StoneBlock 4.json").write_text(json.dumps({"id": "1.21.1"}), encoding="utf-8")
            _touch(root / "mods" / "minecraft.jar")
            _touch(root / "mods" / "neoforge.jar")
            _touch(root / "config" / "ftbquests" / "quests" / "data.snbt")
            _touch(root / "config" / "ftbquests" / "quests" / "chapters" / "welcome.snbt")
            _touch(root / "kubejs" / "server_scripts" / "recipes" / "early.js")
            _touch(root / "kubejs" / "server_scripts" / "systems" / "stage_sync.js")
            _touch(root / "kubejs" / "data" / "packwise" / "test.json")
            _touch(root / "datapacks" / "ftb" / "data" / "packwise" / "recipes" / "thing.json")
            _touch(root / "defaultconfigs" / "server.toml")
            _touch(root / "logs" / "latest.log")
            _touch(root / "saves" / "World" / "level.dat")

            summary = inspect_instance(root)

        self.assertEqual("packwise.static_inspect.v1", summary["schema_version"])
        self.assertEqual("pcl2_installed_instance", summary["instance"]["kind"])
        self.assertTrue(summary["instance"]["version_isolated"])
        self.assertEqual("StoneBlock Test", summary["pack"]["name"])
        self.assertEqual("1.21.1", summary["loader"]["minecraft_version"])
        self.assertEqual("neoforge", summary["loader"]["name"])
        self.assertEqual("21.1.233", summary["loader"]["version"])
        self.assertEqual(2, summary["counts"]["mod_jars"])
        self.assertEqual(2, summary["counts"]["ftbquests_snbt_files"])
        self.assertEqual(1, summary["counts"]["ftbquests_chapter_files"])
        self.assertEqual(2, summary["counts"]["kubejs_server_js_files"])
        self.assertEqual(1, summary["counts"]["kubejs_recipe_js_files"])
        self.assertEqual(1, summary["counts"]["datapack_recipe_json_files"])
        self.assertEqual(["minecraft.jar", "neoforge.jar"], summary["safe_samples"]["mod_jars"])
        self.assertIn("logs", summary["ignored_present"])
        self.assertIn("saves", summary["ignored_present"])

    def test_rejects_missing_path(self):
        with self.assertRaises(ValueError):
            inspect_instance("does-not-exist")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
