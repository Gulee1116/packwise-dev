import json
import tempfile
import unittest
from pathlib import Path

from packwise_agent.pack_profiles import load_pack_profiles, select_pack_profile
from packwise_agent.static_inspector import inspect_instance


class PackProfilesTest(unittest.TestCase):
    def test_selects_atm9sky_profile_by_static_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            _write_setup(root, "1.20.1", "47.4.20")
            (root / "modpackinfo.json").write_text(
                json.dumps({"modpack": {"name": "All the Mods 9 - To the Sky", "version": "1.1.0"}}),
                encoding="utf-8",
            )

            profile = select_pack_profile(inspect_instance(root), load_pack_profiles())

        self.assertEqual("atm9sky", profile.profile_id)
        self.assertEqual("ftbquests", profile.adapter["quest_mod"])

    def test_selects_generic_forge_1201_for_second_pack_without_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Second Forge Sky Pack"
            _write_setup(root, "1.20.1", "47.4.20")
            (root / "modpackinfo.json").write_text(
                json.dumps({"modpack": {"name": "Second Forge Sky Pack", "version": "2.0.0"}}),
                encoding="utf-8",
            )

            profile = select_pack_profile(inspect_instance(root), load_pack_profiles())

        self.assertEqual("generic-forge-1201", profile.profile_id)
        self.assertEqual("forge", profile.adapter["loader"])

    def test_selects_atm9sky_profile_from_curseforge_manifest_without_path_hint(self):
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

            profile = select_pack_profile(inspect_instance(root), load_pack_profiles())

        self.assertEqual("atm9sky", profile.profile_id)

    def test_selects_profile_with_case_insensitive_identity(self):
        summary = {
            "pack": {"name": "ALL THE MODS 9 - TO THE SKY"},
            "loader": {"name": "Forge", "minecraft_version": "1.20.1"},
            "adapter": {"pack_id": "ATM9SKY", "loader": "Forge", "minecraft_version": "1.20.1"},
        }

        profile = select_pack_profile(summary, load_pack_profiles())

        self.assertEqual("atm9sky", profile.profile_id)

    def test_selects_generic_forge_1201_with_case_insensitive_loader(self):
        summary = {
            "pack": {"name": "Second Pack"},
            "loader": {"name": "Forge", "minecraft_version": "1.20.1"},
            "adapter": {"pack_id": "SECOND-PACK", "loader": "Forge", "minecraft_version": "1.20.1"},
        }

        profile = select_pack_profile(summary, load_pack_profiles())

        self.assertEqual("generic-forge-1201", profile.profile_id)


def _write_setup(root: Path, minecraft: str, forge: str) -> None:
    (root / "PCL").mkdir(parents=True)
    (root / "PCL" / "Setup.ini").write_text(
        "\n".join(
            [
                f"VersionVanillaName:{minecraft}",
                f"VersionForge:{forge}",
                "VersionArgumentIndieV2:True",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
