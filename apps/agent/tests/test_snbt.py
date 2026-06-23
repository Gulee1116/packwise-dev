import unittest

from packwise_agent.snbt import parse_snbt


class SnbtParserTest(unittest.TestCase):
    def test_parses_ftbquests_style_without_commas(self):
        payload = parse_snbt(
            """
            {
                id: "chapter"
                quests: [
                    { id: "a" dependencies: ["root"] x: 1.5d y: -2.0d }
                    { id: "b" tasks: [{ type: "item" item: { count: 4, id: "minecraft:stone" } }] }
                ]
            }
            """
        )

        self.assertEqual("chapter", payload["id"])
        self.assertEqual("a", payload["quests"][0]["id"])
        self.assertEqual(["root"], payload["quests"][0]["dependencies"])
        self.assertEqual(1.5, payload["quests"][0]["x"])
        self.assertEqual("minecraft:stone", payload["quests"][1]["tasks"][0]["item"]["id"])

    def test_parses_typed_int_array(self):
        payload = parse_snbt("{ position: [I; -75 -22 15] enabled: true }")

        self.assertEqual([-75, -22, 15], payload["position"])
        self.assertTrue(payload["enabled"])


if __name__ == "__main__":
    unittest.main()
