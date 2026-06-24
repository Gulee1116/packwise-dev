import unittest

from packwise_agent.runtime_index import (
    RuntimePackIndex,
    parse_advancements_ndjson,
    parse_ftb_quests_ndjson,
    parse_progress_ndjson,
    parse_recipes_ndjson,
    parse_registry_entries_ndjson,
    parse_stages_ndjson,
    parse_tags_ndjson,
    runtime_consistency_errors,
)


class RuntimeIndexTest(unittest.TestCase):
    def test_parses_phase_one_runtime_sections(self):
        items = parse_registry_entries_ndjson(
            '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime"}\n'
        )
        tags = parse_tags_ndjson(
            '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime"}\n'
        )
        recipes = parse_recipes_ndjson(
            '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime"}\n'
        )
        advancements = parse_advancements_ndjson(
            '{"id":"minecraft:story/mine_stone","source":"runtime"}\n'
        )

        self.assertEqual("minecraft:stone", items[0].id)
        self.assertEqual("forge:stone", tags[0].tag)
        self.assertEqual("minecraft:stone", recipes[0].result_item)
        self.assertEqual(["minecraft:cobblestone"], recipes[0].ingredient_items)
        self.assertEqual("minecraft:story/mine_stone", advancements[0].id)

    def test_parses_optional_progression_runtime_sections(self):
        quests = parse_ftb_quests_ndjson(
            '{"quest_id":"quest_start","chapter_id":null,"title":"Start",'
            '"dependencies":["root"],"dependency_types":{"root":"quest"},'
            '"task_item_ids":["minecraft:stone"],"reward_item_ids":[],"source":"runtime:ftb_quests"}\n'
        )
        player_progress = parse_progress_ndjson(
            '{"subject_type":"player","subject_id":"player-1","completed_quests":["quest_start"],"completed_advancements":["minecraft:story/mine_stone"],"stages":["stone_age"],"source":"runtime:ftb_quests","player_name":"DevPlayer","team_id":"team-1"}\n',
            "player_progress",
        )
        team_progress = parse_progress_ndjson(
            '{"subject_type":"team","subject_id":"team-1","completed_quests":["quest_start"],"completed_advancements":[],"stages":[],"source":"runtime:ftb_quests","team_name":"DevTeam#00000000","members":["player-1"]}\n',
            "team_progress",
        )
        stages = parse_stages_ndjson(
            '{"subject_type":"player","subject_id":"player-1","stage":"stone_age","active":true,"source":"runtime:gamestages","player_name":"DevPlayer"}\n'
        )

        self.assertEqual("quest_start", quests[0].quest_id)
        self.assertIsNone(quests[0].chapter_id)
        self.assertEqual({"root": "quest"}, quests[0].dependency_types)
        self.assertEqual(["root"], quests[0].quest_dependencies())
        self.assertEqual(["minecraft:stone"], quests[0].task_item_ids)
        self.assertEqual(["quest_start"], player_progress[0].completed_quests)
        self.assertEqual("DevPlayer", player_progress[0].player_name)
        self.assertEqual("team-1", player_progress[0].team_id)
        self.assertEqual(["quest_start"], team_progress[0].completed_quests)
        self.assertEqual("DevTeam#00000000", team_progress[0].team_name)
        self.assertEqual(["player-1"], team_progress[0].members)
        self.assertEqual("stone_age", stages[0].stage)
        self.assertTrue(stages[0].active)
        self.assertEqual("DevPlayer", stages[0].player_name)

    def test_runtime_pack_index_tracks_section_counts(self):
        index = RuntimePackIndex.empty()
        index = index.with_section(
            "items",
            '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime"}\n',
        )
        index = index.with_section(
            "recipes",
            '{"id":"minecraft:stone","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone","result_count":1,"source":"runtime"}\n',
        )

        self.assertEqual(1, index.summary()["items"])
        self.assertEqual(1, index.summary()["recipes"])
        self.assertEqual(0, index.summary()["ftb_quests"])

    def test_runtime_consistency_errors_cover_optional_progression_sections(self):
        index = RuntimePackIndex.empty()
        index = index.with_section(
            "items",
            '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime"}\n',
        )
        index = index.with_section(
            "ftb_quests",
            (
                '{"quest_id":"quest_root","chapter_id":null,"title":"Root",'
                '"dependencies":[],"task_item_ids":["minecraft:stone"],'
                '"reward_item_ids":[],"source":"runtime:ftb_quests"}\n'
                '{"quest_id":"quest_bad","chapter_id":null,"title":"Bad",'
                '"dependencies":["quest_missing"],"task_item_ids":["minecraft:missing_task"],'
                '"reward_item_ids":["minecraft:missing_reward"],"source":"runtime:ftb_quests"}\n'
            ),
        )
        index = index.with_section(
            "player_progress",
            (
                '{"subject_type":"player","subject_id":"player-1",'
                '"completed_quests":["quest_root","quest_unknown"],'
                '"completed_advancements":[],"stages":["stone_age","missing_stage"],'
                '"source":"runtime:ftb_quests","player_name":"DevPlayer"}\n'
            ),
        )
        index = index.with_section(
            "team_progress",
            (
                '{"subject_type":"team","subject_id":"team-1",'
                '"completed_quests":["quest_missing_team"],'
                '"completed_advancements":[],"stages":["team_stage"],'
                '"source":"runtime:ftb_quests","members":["player-1"]}\n'
            ),
        )
        index = index.with_section(
            "stages",
            (
                '{"subject_type":"player","subject_id":"player-1","stage":"stone_age",'
                '"active":true,"source":"runtime:gamestages","player_name":"DevPlayer"}\n'
            ),
        )

        errors = runtime_consistency_errors(index)

        self.assertIn(
            "FTB quest task items missing from items registry: minecraft:missing_task",
            errors,
        )
        self.assertIn(
            "FTB quest reward items missing from items registry: minecraft:missing_reward",
            errors,
        )
        self.assertIn("FTB quest dependencies missing from ftb_quests: quest_missing", errors)
        self.assertIn(
            "Player progress completed quests missing from ftb_quests: quest_unknown",
            errors,
        )
        self.assertIn(
            "Team progress completed quests missing from ftb_quests: quest_missing_team",
            errors,
        )
        self.assertIn(
            "Player progress stages missing from stages section: player-1:missing_stage",
            errors,
        )
        self.assertNotIn(
            "Team progress stages missing from stages section: team-1:team_stage",
            errors,
        )

    def test_runtime_consistency_uses_typed_ftb_quest_dependencies_when_present(self):
        index = RuntimePackIndex.empty()
        index = index.with_section(
            "ftb_quests",
            (
                '{"quest_id":"quest_root","chapter_id":null,"title":"Root",'
                '"dependencies":[],"dependency_types":{},'
                '"task_item_ids":[],"reward_item_ids":[],"source":"runtime:ftb_quests"}\n'
                '{"quest_id":"quest_typed","chapter_id":null,"title":"Typed",'
                '"dependencies":["quest_root","task_missing","quest_missing"],'
                '"dependency_types":{"quest_root":"quest","task_missing":"task","quest_missing":"quest"},'
                '"task_item_ids":[],"reward_item_ids":[],"source":"runtime:ftb_quests"}\n'
            ),
        )

        errors = runtime_consistency_errors(index)

        self.assertIn("FTB quest dependencies missing from ftb_quests: quest_missing", errors)
        self.assertTrue(all("task_missing" not in error for error in errors))


if __name__ == "__main__":
    unittest.main()
