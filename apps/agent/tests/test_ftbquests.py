import tempfile
import unittest
from pathlib import Path

from packwise_agent.ftbquests import inspect_quest_book


class FtbQuestsTest(unittest.TestCase):
    def test_inspects_quest_book_skeleton(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "instance"
            quests_root = root / "config" / "ftbquests" / "quests"
            chapters = quests_root / "chapters"
            chapters.mkdir(parents=True)
            (quests_root / "data.snbt").write_text(
                '{ version: 13 progression_mode: "flexible" default_quest_shape: "circle" }',
                encoding="utf-8",
            )
            (chapters / "getting_started.snbt").write_text(
                """
                {
                    filename: "getting_started"
                    group: "group_1"
                    icon: { id: "minecraft:crafting_table" }
                    id: "chapter_1"
                    order_index: 0
                    quests: [
                        {
                            id: "quest_1"
                            icon: { id: "minecraft:stone" }
                            rewards: [
                                { id: "reward_1" type: "currency" amount: 1 }
                                { id: "reward_2" type: "gamestage" stage: "stone_age" team_reward: false }
                            ]
                            tasks: [
                                { id: "task_1" type: "item" item: { count: 4 id: "minecraft:stone" } }
                            ]
                            x: 0.0d
                            y: 1.0d
                        }
                        {
                            id: "quest_2"
                            dependencies: ["quest_1"]
                            min_required_dependencies: 1
                            tasks: [{ id: "task_2" type: "checkmark" }]
                        }
                    ]
                }
                """,
                encoding="utf-8",
            )

            summary = inspect_quest_book(root)

        self.assertEqual("packwise.ftbquests.v1", summary["schema_version"])
        self.assertEqual(13, summary["settings"]["version"])
        self.assertEqual(1, summary["counts"]["chapters"])
        self.assertEqual(2, summary["counts"]["quests"])
        self.assertEqual(2, summary["counts"]["tasks"])
        self.assertEqual(2, summary["counts"]["rewards"])
        self.assertEqual(1, summary["counts"]["dependency_edges"])
        self.assertEqual(["stone_age"], summary["stages"])
        chapter = summary["chapters"][0]
        self.assertEqual("chapter_1", chapter["id"])
        self.assertEqual("minecraft:crafting_table", chapter["icon"])
        quest = chapter["quests"][0]
        self.assertEqual("minecraft:stone", quest["tasks"][0]["item_id"])
        self.assertEqual(4, quest["tasks"][0]["item_count"])
        self.assertEqual("stone_age", quest["rewards"][1]["stage"])


if __name__ == "__main__":
    unittest.main()
