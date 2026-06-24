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
        self.assertEqual("stoneblock-test", summary["adapter"]["pack_id"])
        self.assertEqual("neoforge", summary["adapter"]["loader"])
        self.assertEqual("ftbquests", summary["adapter"]["quest_mod"])
        self.assertIn("ftbquests", summary["adapter"]["known_progression_sources"])
        self.assertTrue(summary["adapter"]["source_inventory"]["kubejs"]["present"])
        self.assertIn("server_scripts/recipes/early.js", summary["adapter"]["source_inventory"]["kubejs"]["sample_files"])
        self.assertIn("ftb/data/packwise/recipes/thing.json", summary["adapter"]["source_inventory"]["datapacks"]["sample_files"])
        self.assertIn("server.toml", summary["adapter"]["source_inventory"]["defaultconfigs"]["sample_files"])
        self.assertIn("ftbquests/quests/chapters/welcome.snbt", summary["adapter"]["source_inventory"]["config"]["sample_files"])
        self.assertTrue(summary["adapter"]["optional_integrations"]["kubejs"]["present"])
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

    def test_detects_forge_1201_instance_without_pack_specific_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
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
            _touch(root / "mods" / "ftb-teams-forge.jar")
            _touch(root / "mods" / "gamestages-forge.jar")
            _touch(root / "mods" / "kubejs-forge.jar")
            _touch(root / "config" / "ftbquests" / "quests" / "chapters" / "start.snbt")
            _touch(root / "kubejs" / "server_scripts" / "atm.js")
            _touch(root / "defaultconfigs" / "ftbquests-server.snbt")

            summary = inspect_instance(root)

        self.assertEqual("forge", summary["loader"]["name"])
        self.assertEqual("47.4.20", summary["loader"]["version"])
        self.assertEqual("1.20.1", summary["loader"]["minecraft_version"])
        self.assertEqual("all-the-mods-9-to-the-sky", summary["adapter"]["pack_id"])
        self.assertEqual("ftbquests", summary["adapter"]["quest_mod"])
        self.assertIn("ftbquests", summary["adapter"]["known_progression_sources"])
        self.assertIn("gamestages", summary["adapter"]["known_progression_sources"])
        self.assertTrue(summary["adapter"]["optional_integrations"]["ftb_teams"]["present"])
        self.assertTrue(summary["adapter"]["source_inventory"]["defaultconfigs"]["present"])

    def test_detects_curseforge_manifest_atm9sky_without_launcher_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "server"
            root.mkdir()
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifestType": "minecraftModpack",
                        "name": "All the Mods 9 - To the Sky",
                        "version": "1.1.0",
                        "minecraft": {
                            "version": "1.20.1",
                            "modLoaders": [{"id": "forge-47.4.20", "primary": True}],
                        },
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )
            _touch(root / "mods" / "ftb-quests-forge.jar")
            _touch(root / "config" / "ftbquests" / "quests" / "chapters" / "start.snbt")

            summary = inspect_instance(root)

        self.assertEqual("curseforge_manifest", summary["instance"]["kind"])
        self.assertEqual("CurseForge", summary["instance"]["launcher"])
        self.assertEqual("All the Mods 9 - To the Sky", summary["pack"]["name"])
        self.assertEqual("1.1.0", summary["pack"]["version"])
        self.assertEqual("forge", summary["loader"]["name"])
        self.assertEqual("47.4.20", summary["loader"]["version"])
        self.assertEqual("1.20.1", summary["loader"]["minecraft_version"])
        self.assertEqual("all-the-mods-9-to-the-sky", summary["adapter"]["pack_id"])
        self.assertEqual(["manifest.json"], summary["adapter"]["source_inventory"]["manifest"]["files"])

    def test_detects_modrinth_index_for_generic_forge_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "download"
            root.mkdir()
            (root / "modrinth.index.json").write_text(
                json.dumps(
                    {
                        "formatVersion": 1,
                        "game": "minecraft",
                        "name": "Second Forge Pack",
                        "versionId": "2.0.0",
                        "dependencies": {
                            "minecraft": "1.20.1",
                            "forge": "47.4.20",
                        },
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )

            summary = inspect_instance(root)

        self.assertEqual("modrinth_index", summary["instance"]["kind"])
        self.assertEqual("Modrinth", summary["instance"]["launcher"])
        self.assertEqual("Second Forge Pack", summary["pack"]["name"])
        self.assertEqual("2.0.0", summary["pack"]["version"])
        self.assertEqual("forge", summary["loader"]["name"])
        self.assertEqual("47.4.20", summary["loader"]["version"])
        self.assertEqual("1.20.1", summary["loader"]["minecraft_version"])
        self.assertEqual("second-forge-pack", summary["adapter"]["pack_id"])

    def test_detects_plain_forge_server_library_layout_without_launcher_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Second Forge Server"
            (root / "libraries" / "net" / "minecraftforge" / "forge" / "1.20.1-47.4.20").mkdir(parents=True)
            _touch(root / "mods" / "jei-forge.jar")

            summary = inspect_instance(root)

        self.assertEqual("directory", summary["instance"]["kind"])
        self.assertIsNone(summary["instance"]["launcher"])
        self.assertEqual("Second Forge Server", summary["pack"]["name"])
        self.assertEqual("forge", summary["loader"]["name"])
        self.assertEqual("47.4.20", summary["loader"]["version"])
        self.assertEqual("1.20.1", summary["loader"]["minecraft_version"])
        self.assertEqual("second-forge-server", summary["adapter"]["pack_id"])
        self.assertEqual("forge", summary["adapter"]["loader"])
        self.assertEqual("1.20.1", summary["adapter"]["minecraft_version"])
        self.assertFalse(summary["adapter"]["source_inventory"]["manifest"]["present"])

    def test_detects_plain_neoforge_server_root_jar_without_launcher_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "StoneBlock Server"
            root.mkdir()
            _touch(root / "neoforge-21.1.233-server.jar")

            summary = inspect_instance(root)

        self.assertEqual("directory", summary["instance"]["kind"])
        self.assertEqual("neoforge", summary["loader"]["name"])
        self.assertEqual("21.1.233", summary["loader"]["version"])
        self.assertEqual("1.21.1", summary["loader"]["minecraft_version"])
        self.assertEqual("stoneblock-server", summary["adapter"]["pack_id"])


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
