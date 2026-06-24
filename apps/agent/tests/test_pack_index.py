import json
import tempfile
import unittest
from pathlib import Path

from packwise_agent.pack_index import build_packwise_index_from_instance, runtime_index_from_sections


class PackIndexTest(unittest.TestCase):
    def test_builds_atm9sky_index_from_static_sources_and_runtime_dump_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "All the Mods 9 - To the Sky"
            _write_setup(root, "1.20.1", "47.4.20")
            (root / "modpackinfo.json").write_text(
                json.dumps({"modpack": {"name": "All the Mods 9 - To the Sky", "version": "1.1.0"}}),
                encoding="utf-8",
            )
            _touch(root / "mods" / "ftb-quests-forge.jar")
            _touch(root / "mods" / "ftb-teams-forge.jar")
            _touch(root / "mods" / "kubejs-forge.jar")
            _write_quest_book(root)

            index = build_packwise_index_from_instance(root, _runtime_sections()).to_dict()

        self.assertEqual("packwise.index.v1", index["schema_version"])
        self.assertEqual("atm9sky", index["profile"]["profile_id"])
        self.assertEqual("all-the-mods-9-to-the-sky", index["identity"]["pack_id"])
        self.assertTrue(index["source_policy"]["runtime_truth_authoritative"])
        self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["registries"])
        self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["recipes"])
        self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["quests"])
        self.assertEqual(1, index["runtime"]["counts"]["recipes"])
        self.assertEqual(1, index["quests"]["counts"]["quests"])
        self.assertTrue(index["answer_readiness"]["recipe_questions"])
        self.assertEqual("ready", index["answer_readiness"]["next_step_questions"])

    def test_runtime_index_from_sections_keeps_dump_formats_generic(self):
        runtime_index = runtime_index_from_sections(_runtime_sections())

        self.assertEqual(1, runtime_index.summary()["items"])
        self.assertEqual(1, runtime_index.summary()["blocks"])
        self.assertEqual(1, runtime_index.summary()["fluids"])
        self.assertEqual(1, runtime_index.summary()["tags"])
        self.assertEqual(1, runtime_index.summary()["ftb_quests"])
        self.assertEqual(1, runtime_index.summary()["team_progress"])
        self.assertEqual(1, runtime_index.summary()["stages"])
        self.assertEqual("minecraft:stone", runtime_index.recipes[0].result_item)

    def test_second_forge_1201_pack_uses_generic_profile_without_architectural_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Second Forge Pack"
            _write_setup(root, "1.20.1", "47.4.20")
            (root / "modpackinfo.json").write_text(
                json.dumps({"modpack": {"name": "Second Forge Pack", "version": "2.0.0"}}),
                encoding="utf-8",
            )

            index = build_packwise_index_from_instance(root, _runtime_sections()).to_dict()

        self.assertEqual("generic-forge-1201", index["profile"]["profile_id"])
        self.assertEqual("second-forge-pack", index["identity"]["pack_id"])
        self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["registries"])
        self.assertEqual([], index["quests"]["stages"])

    def test_partial_registry_runtime_sections_do_not_claim_authoritative_registries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Second Forge Pack"
            _write_setup(root, "1.20.1", "47.4.20")
            (root / "modpackinfo.json").write_text(
                json.dumps({"modpack": {"name": "Second Forge Pack", "version": "2.0.0"}}),
                encoding="utf-8",
            )
            sections = dict(_runtime_sections())
            sections.pop("blocks")

            index = build_packwise_index_from_instance(root, sections).to_dict()

        self.assertEqual("missing_runtime", index["source_policy"]["reconciliation"]["registries"])
        self.assertIn("blocks", index["runtime"]["missing_phase1_sections"])
        self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["recipes"])


def _runtime_sections():
    return {
        "items": '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
        "blocks": '{"id":"minecraft:stone","registry":"block","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
        "fluids": '{"id":"minecraft:water","registry":"fluid","namespace":"minecraft","path":"water","source":"runtime:built_in_registry"}\n',
        "tags": '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime:registry_tags"}\n',
        "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
        "advancements": '{"id":"minecraft:story/mine_stone","source":"runtime:server_advancements"}\n',
        "ftb_quests": '{"quest_id":"quest_start","chapter_id":"chapter_start","title":"Start","dependencies":[],"task_item_ids":["minecraft:stone"],"reward_item_ids":[],"source":"runtime:ftb_quests"}\n',
        "team_progress": '{"subject_type":"team","subject_id":"team-main","completed_quests":["quest_start"],"completed_advancements":[],"stages":["stone_age"],"source":"runtime:ftb_teams"}\n',
        "stages": '{"subject_type":"team","subject_id":"team-main","stage":"stone_age","active":true,"source":"runtime:gamestages"}\n',
    }


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


def _write_quest_book(root: Path) -> None:
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
              title: "Start"
              tasks: [{ id: "task_stone" type: "item" item: { id: "minecraft:stone" count: 1 } }]
              rewards: [{ id: "reward_stage" type: "gamestage" stage: "stone_age" }]
            }
          ]
        }
        """,
        encoding="utf-8",
    )


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
