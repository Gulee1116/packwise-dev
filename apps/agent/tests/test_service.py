import hashlib
import unittest

from packwise_agent.protocol import ConnectorHello, ConnectorInfo, ConnectorSide
from packwise_agent.service import AgentService


class AgentServiceTest(unittest.TestCase):
    def test_connector_hello_returns_ack(self):
        service = AgentService(model_name="deepseek-v4-pro")
        hello = ConnectorHello.create(
            message_id="msg_0001",
            sent_at="2026-06-14T08:00:00Z",
            connector=ConnectorInfo(
                id="stoneblock4-dev-server",
                side=ConnectorSide.SERVER,
                loader="neoforge",
                loader_version="21.1.233",
                minecraft_version="1.21.1",
                pack_id="ftb-stoneblock-4",
                pack_name="FTB StoneBlock 4",
                pack_version="1.14.2",
                connector_mod_id="packwise_connector",
                connector_version="0.1.0",
                capabilities=["runtime_dump", "commands"],
            ),
        )

        ack = service.handle_connector_hello(hello.to_dict())
        self.assertEqual("connector.ack", ack["message_type"])
        self.assertEqual("msg_0001", ack["in_reply_to"])
        self.assertTrue(ack["accepted"])
        self.assertIn("stoneblock4-dev-server", service.connectors)

    def test_ask_returns_answer_packet_shape(self):
        service = AgentService(model_name="deepseek-v4-pro")
        response = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:05:00Z",
                "question": "我下一步该干什么？",
                "locale": "zh_cn",
                "context": {
                    "connector_id": "stoneblock4-dev-server",
                    "server_id": "local-dev",
                    "team_id": "team-main",
                    "known_progress": {"completed_quests": [], "stages": []},
                },
            }
        )

        self.assertEqual("answer.packet", response["message_type"])
        self.assertEqual("msg_0100", response["in_reply_to"])
        answer = response["answer"]
        self.assertTrue(answer["summary"])
        self.assertIsInstance(answer["next_steps"], list)
        self.assertIsInstance(answer["source_refs"], list)
        self.assertEqual("low", answer["confidence"])
        self.assertEqual("deepseek-v4-pro", answer["model"])

    def test_ask_can_use_injected_llm_client(self):
        service = AgentService(model_name="deepseek-v4-pro", chat_client=FakeChatClient("LLM summary"))
        response = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:05:00Z",
                "question": "这个东西从哪来？",
                "locale": "zh_cn",
                "context": {},
            }
        )

        self.assertEqual("LLM summary", response["answer"]["summary"])
        self.assertEqual("deepseek-v4-pro", response["answer"]["model"])

    def test_runtime_dump_manifest_is_stored(self):
        service = AgentService(model_name="deepseek-v4-pro")
        ack = service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_20260614_081000",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 404,
                        "sha256": "sha-mods",
                    }
                ],
            },
        )

        self.assertEqual("runtime_dump.ack", ack["message_type"])
        self.assertEqual("msg_0200", ack["in_reply_to"])
        self.assertIn("dump_20260614_081000", service.runtime_dumps)

    def test_runtime_dump_manifest_rejects_duplicate_sections(self):
        service = AgentService(model_name="deepseek-v4-pro")
        with self.assertRaisesRegex(ValueError, "Duplicate runtime dump sections in manifest: recipes"):
            service.handle_runtime_dump_manifest(
                "atm9sky-dev-server",
                {
                    "protocol": "packwise.connector.v1",
                    "message_type": "runtime_dump.manifest",
                    "message_id": "msg_0200",
                    "sent_at": "2026-06-14T08:10:00Z",
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_duplicate",
                    "minecraft_version": "1.20.1",
                    "loader": "forge",
                    "loader_version": "47.4.20",
                    "sections": [
                        {
                            "name": "recipes",
                            "content_type": "application/x-ndjson",
                            "count": 1,
                            "sha256": "sha-recipes-a",
                        },
                        {
                            "name": "recipes",
                            "content_type": "application/x-ndjson",
                            "count": 1,
                            "sha256": "sha-recipes-b",
                        },
                    ],
                },
            )
        self.assertNotIn("dump_duplicate", service.runtime_dumps)

    def test_runtime_dump_manifest_rejects_standard_section_with_non_ndjson_content_type(self):
        service = AgentService(model_name="deepseek-v4-pro")
        with self.assertRaisesRegex(ValueError, "recipes=text/plain"):
            service.handle_runtime_dump_manifest(
                "atm9sky-dev-server",
                {
                    "protocol": "packwise.connector.v1",
                    "message_type": "runtime_dump.manifest",
                    "message_id": "msg_0200",
                    "sent_at": "2026-06-14T08:10:00Z",
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_text_recipe",
                    "minecraft_version": "1.20.1",
                    "loader": "forge",
                    "loader_version": "47.4.20",
                    "sections": [
                        {
                            "name": "recipes",
                            "content_type": "text/plain",
                            "count": 1,
                            "sha256": "sha-recipes",
                        }
                    ],
                },
            )
        self.assertNotIn("dump_text_recipe", service.runtime_dumps)

    def test_runtime_dump_manifest_rejects_connector_mismatch(self):
        service = AgentService(model_name="deepseek-v4-pro")
        with self.assertRaises(Exception):
            service.handle_runtime_dump_manifest(
                "other-server",
                {
                    "protocol": "packwise.connector.v1",
                    "message_type": "runtime_dump.manifest",
                    "message_id": "msg_0200",
                    "sent_at": "2026-06-14T08:10:00Z",
                    "connector_id": "stoneblock4-dev-server",
                    "dump_id": "dump_20260614_081000",
                    "minecraft_version": "1.21.1",
                    "loader": "neoforge",
                    "loader_version": "21.1.233",
                    "sections": [],
                },
            )

    def test_runtime_dump_section_is_stored_after_manifest(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}\n'
        service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )

        ack = service.handle_runtime_dump_section(
            connector_id="stoneblock4-dev-server",
            dump_id="dump_1",
            section_name="mods",
            content_type="application/x-ndjson",
            body=body,
        )

        self.assertEqual("runtime_dump.section_ack", ack["message_type"])
        self.assertEqual(1, ack["line_count"])
        self.assertEqual(body, service.runtime_dump_sections[("dump_1", "mods")].body)
        self.assertEqual("minecraft", service.runtime_mods["dump_1"][0].mod_id)

    def test_runtime_dump_section_rejects_unknown_section(self):
        service = AgentService(model_name="deepseek-v4-pro")
        service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [],
            },
        )
        with self.assertRaises(Exception):
            service.handle_runtime_dump_section(
                connector_id="stoneblock4-dev-server",
                dump_id="dump_1",
                section_name="mods",
                content_type="application/x-ndjson",
                body="",
            )

    def test_mods_section_indexes_multiple_mods(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = (
            '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}\n'
            '{"mod_id":"neoforge","display_name":"NeoForge","version":"21.1.233","source":"neoforge:ModList"}\n'
        )
        service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 2,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )

        service.handle_runtime_dump_section(
            connector_id="stoneblock4-dev-server",
            dump_id="dump_1",
            section_name="mods",
            content_type="application/x-ndjson",
            body=body,
        )

        mods = service.list_runtime_mods("dump_1")
        self.assertEqual(2, len(mods))
        self.assertEqual("minecraft", mods[0]["mod_id"])
        self.assertEqual("NeoForge", mods[1]["display_name"])

    def test_recipe_section_indexes_and_answers_with_source_refs(self):
        service = AgentService(model_name="deepseek-v4-pro")
        items = (
            '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
            '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
        )
        recipes = '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n'
        service.handle_runtime_dump_manifest(
            "atm9sky-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_atm9sky",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "sections": [
                    {"name": "items", "content_type": "application/x-ndjson", "count": 2, "sha256": _sha256(items)},
                    {"name": "recipes", "content_type": "application/x-ndjson", "count": 1, "sha256": _sha256(recipes)},
                ],
            },
        )
        service.handle_runtime_dump_section(
            connector_id="atm9sky-dev-server",
            dump_id="dump_atm9sky",
            section_name="items",
            content_type="application/x-ndjson",
            body=items,
        )
        service.handle_runtime_dump_section(
            connector_id="atm9sky-dev-server",
            dump_id="dump_atm9sky",
            section_name="recipes",
            content_type="application/x-ndjson",
            body=recipes,
        )

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "minecraft:stone 怎么做？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_atm9sky"},
            }
        )["answer"]

        self.assertIn("minecraft:stone", answer["summary"])
        self.assertEqual("medium", answer["confidence"])
        self.assertIn({"kind": "recipe", "path": "minecraft:stonecutting/stone", "label": "minecraft:stone"}, answer["source_refs"])
        self.assertEqual(2, service.runtime_index_summary("dump_atm9sky")["items"])
        self.assertEqual(1, service.runtime_index_summary("dump_atm9sky")["recipes"])
        self.assertEqual(0, service.runtime_index_summary("dump_atm9sky")["team_progress"])

        blocker_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0101",
                "sent_at": "2026-06-14T08:16:00Z",
                "question": "当前目标缺哪些前置机器/任务/材料？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_atm9sky", "item_id": "minecraft:stone"},
            }
        )["answer"]
        self.assertIn("minecraft:cobblestone", blocker_answer["summary"])
        self.assertIn("minecraft:cobblestone", blocker_answer["next_steps"][0])

    def test_static_and_quest_payloads_build_packwise_index_and_unlock_answer(self):
        service = AgentService(model_name="deepseek-v4-pro")
        items = (
            '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
            '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
        )
        recipes = '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n'
        service.handle_static_inspect("atm9sky-dev-server", _static_summary())
        service.handle_quest_book("atm9sky-dev-server", _quest_summary())
        service.handle_runtime_dump_manifest(
            "atm9sky-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_atm9sky",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "sections": [
                    {"name": "items", "content_type": "application/x-ndjson", "count": 2, "sha256": _sha256(items)},
                    {"name": "recipes", "content_type": "application/x-ndjson", "count": 1, "sha256": _sha256(recipes)},
                ],
            },
        )
        service.handle_runtime_dump_section("atm9sky-dev-server", "dump_atm9sky", "items", "application/x-ndjson", items)
        service.handle_runtime_dump_section("atm9sky-dev-server", "dump_atm9sky", "recipes", "application/x-ndjson", recipes)

        index = service.build_packwise_index("atm9sky-dev-server", "dump_atm9sky")
        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "这个物品怎么解锁？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_atm9sky",
                    "item_id": "minecraft:stone",
                },
            }
        )["answer"]

        self.assertEqual("atm9sky", index["profile"]["profile_id"])
        self.assertEqual("runtime_authoritative", index["source_policy"]["reconciliation"]["recipes"])
        self.assertEqual("static_preload_needs_runtime_progress", index["source_policy"]["reconciliation"]["quests"])
        self.assertIn("Stone Start", answer["summary"])
        self.assertIn({"kind": "quest", "path": "chapters/start.snbt#quest_start", "label": "Stone Start"}, answer["source_refs"])

    def test_runtime_quest_progress_sections_drive_unlock_and_next_step_answers(self):
        service = AgentService(model_name="deepseek-v4-pro")
        sections = {
            "items": (
                '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
                '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
            ),
            "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
            "ftb_quests": "\n".join(
                [
                    '{"quest_id":"quest_root","chapter_id":"chapter_start","title":"Root","dependencies":[],"task_item_ids":[],"reward_item_ids":[],"source":"runtime:ftb_quests"}',
                    '{"quest_id":"quest_stone","chapter_id":"chapter_start","title":"Runtime Stone","dependencies":["quest_root"],"task_item_ids":["minecraft:stone"],"reward_item_ids":[],"source":"runtime:ftb_quests"}',
                    "",
                ]
            ),
            "team_progress": '{"subject_type":"team","subject_id":"team-main","completed_quests":["quest_root"],"completed_advancements":[],"stages":[],"source":"runtime:ftb_quests"}\n',
            "stages": '{"subject_type":"player","subject_id":"player-1","stage":"stone_age","active":true,"source":"runtime:gamestages"}\n',
        }
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", sections)

        unlock_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "这个物品怎么解锁？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_runtime",
                    "item_id": "minecraft:stone",
                },
            }
        )["answer"]

        self.assertEqual("high", unlock_answer["confidence"])
        self.assertIn("Runtime Stone", unlock_answer["summary"])
        self.assertIn("未完成", unlock_answer["summary"])
        self.assertIn({"kind": "runtime_dump_section", "path": "dump_runtime/ftb_quests", "label": "Runtime FTB Quests"}, unlock_answer["source_refs"])
        self.assertIn({"kind": "runtime_dump_section", "path": "dump_runtime/progress", "label": "Runtime player/team progress"}, unlock_answer["source_refs"])
        self.assertIn({"kind": "quest", "path": "dump_runtime/ftb_quests#quest_stone", "label": "Runtime Stone"}, unlock_answer["source_refs"])

        next_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0101",
                "sent_at": "2026-06-14T08:16:00Z",
                "question": "下一步该干什么？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]
        self.assertIn("Runtime Stone", next_answer["summary"])
        self.assertIn("Runtime Stone", next_answer["next_steps"][0])

    def test_runtime_progress_answers_are_scoped_by_player_context(self):
        service = AgentService(model_name="deepseek-v4-pro")
        sections = {
            "items": (
                '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
                '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
            ),
            "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
            "ftb_quests": '{"quest_id":"quest_stone","chapter_id":"chapter_start","title":"Runtime Stone","dependencies":[],"task_item_ids":["minecraft:stone"],"reward_item_ids":[],"source":"runtime:ftb_quests"}\n',
            "team_progress": "\n".join(
                [
                    '{"subject_type":"team","subject_id":"team-alpha","completed_quests":["quest_stone"],"completed_advancements":[],"stages":[],"source":"runtime:ftb_quests","members":["player-alpha"]}',
                    '{"subject_type":"team","subject_id":"team-beta","completed_quests":[],"completed_advancements":[],"stages":[],"source":"runtime:ftb_quests","members":["player-beta"]}',
                    "",
                ]
            ),
        }
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", sections)

        alpha_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "这个物品怎么解锁？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_runtime",
                    "item_id": "minecraft:stone",
                    "player_id": "player-alpha",
                },
            }
        )["answer"]
        beta_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0101",
                "sent_at": "2026-06-14T08:16:00Z",
                "question": "这个物品怎么解锁？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_runtime",
                    "item_id": "minecraft:stone",
                    "player_id": "player-beta",
                },
            }
        )["answer"]

        self.assertIn("Runtime Stone=已完成", alpha_answer["summary"])
        self.assertIn("Runtime Stone=未完成", beta_answer["summary"])
        self.assertEqual("high", alpha_answer["confidence"])
        self.assertEqual("high", beta_answer["confidence"])

    def test_jei_difference_answer_cites_runtime_tags_with_recipes(self):
        service = AgentService(model_name="deepseek-v4-pro")
        sections = {
            "items": (
                '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
                '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
            ),
            "tags": '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime:registry_tags"}\n',
            "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
        }
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", sections)

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "为什么 JEI/网上配方和服务器不一样？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]

        self.assertIn("服务器 runtime recipes", answer["summary"])
        self.assertIn("tags=1", answer["summary"])
        self.assertIn({"kind": "runtime_dump_section", "path": "dump_runtime/recipes", "label": "Runtime recipes"}, answer["source_refs"])
        self.assertIn({"kind": "runtime_dump_section", "path": "dump_runtime/tags", "label": "Runtime tags"}, answer["source_refs"])

    def test_runtime_dump_section_rejects_sha_mismatch(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}\n'
        service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": "0" * 64,
                    }
                ],
            },
        )

        with self.assertRaises(Exception):
            service.handle_runtime_dump_section(
                connector_id="stoneblock4-dev-server",
                dump_id="dump_1",
                section_name="mods",
                content_type="application/x-ndjson",
                body=body,
            )

    def test_runtime_dump_section_rejects_count_mismatch(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}\n'
        service.handle_runtime_dump_manifest(
            "stoneblock4-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "stoneblock4-dev-server",
                "dump_id": "dump_1",
                "minecraft_version": "1.21.1",
                "loader": "neoforge",
                "loader_version": "21.1.233",
                "sections": [
                    {
                        "name": "mods",
                        "content_type": "application/x-ndjson",
                        "count": 2,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )

        with self.assertRaises(Exception):
            service.handle_runtime_dump_section(
                connector_id="stoneblock4-dev-server",
                dump_id="dump_1",
                section_name="mods",
                content_type="application/x-ndjson",
                body=body,
            )

    def test_runtime_dump_section_parse_error_does_not_mark_section_uploaded(self):
        service = AgentService(model_name="deepseek-v4-pro")
        body = '{"id":"minecraft:stone"\n'
        service.handle_runtime_dump_manifest(
            "atm9sky-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0200",
                "sent_at": "2026-06-14T08:10:00Z",
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_parse_error",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "sections": [
                    {
                        "name": "recipes",
                        "content_type": "application/x-ndjson",
                        "count": 1,
                        "sha256": _sha256(body),
                    }
                ],
            },
        )

        with self.assertRaisesRegex(ValueError, "recipes line 1 is not valid JSON"):
            service.handle_runtime_dump_section(
                connector_id="atm9sky-dev-server",
                dump_id="dump_parse_error",
                section_name="recipes",
                content_type="application/x-ndjson",
                body=body,
            )

        self.assertNotIn(("dump_parse_error", "recipes"), service.runtime_dump_sections)
        self.assertNotIn(("atm9sky-dev-server", "dump_parse_error", "recipes"), service.runtime_dump_sections_by_connector)
        self.assertEqual(0, service.runtime_index_summary("dump_parse_error", connector_id="atm9sky-dev-server")["recipes"])
        status = service.connector_status("atm9sky-dev-server")
        runtime_dump = status["runtime_dumps"][0]
        self.assertEqual([], runtime_dump["uploaded_sections"])
        self.assertEqual(["recipes"], runtime_dump["missing_sections"])
        self.assertFalse(runtime_dump["upload_complete"])

    def test_reingested_runtime_dump_manifest_clears_stale_sections(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "atm9sky-dev-server",
            "dump_reused",
            {
                "items": '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
                "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
            },
        )
        self.assertEqual(1, service.runtime_index_summary("dump_reused", connector_id="atm9sky-dev-server")["items"])

        recipes = '{"id":"minecraft:crafting/dirt","type":"minecraft:crafting","serializer":"minecraft:crafting_shapeless","result_item":"minecraft:dirt","result_count":1,"ingredient_items":["minecraft:coarse_dirt"],"source":"runtime:recipe_manager"}\n'
        service.handle_runtime_dump_manifest(
            "atm9sky-dev-server",
            {
                "protocol": "packwise.connector.v1",
                "message_type": "runtime_dump.manifest",
                "message_id": "msg_0201",
                "sent_at": "2026-06-14T08:20:00Z",
                "connector_id": "atm9sky-dev-server",
                "dump_id": "dump_reused",
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "loader_version": "47.4.20",
                "sections": [
                    {"name": "recipes", "content_type": "application/x-ndjson", "count": 1, "sha256": _sha256(recipes)}
                ],
            },
        )
        service.handle_runtime_dump_section(
            connector_id="atm9sky-dev-server",
            dump_id="dump_reused",
            section_name="recipes",
            content_type="application/x-ndjson",
            body=recipes,
        )

        summary = service.runtime_index_summary("dump_reused", connector_id="atm9sky-dev-server")
        self.assertEqual(0, summary["items"])
        self.assertEqual(1, summary["recipes"])
        self.assertEqual("minecraft:dirt", service.list_runtime_recipes("dump_reused", connector_id="atm9sky-dev-server")[0]["result_item"])
        self.assertNotIn(("atm9sky-dev-server", "dump_reused", "items"), service.runtime_dump_sections_by_connector)

    def test_runtime_dump_state_is_connector_scoped_when_dump_ids_collide(self):
        service = AgentService(model_name="deepseek-v4-pro")
        alpha_sections = {
            "items": (
                '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
                '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
            ),
            "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
        }
        beta_sections = {
            "items": (
                '{"id":"minecraft:coarse_dirt","registry":"item","namespace":"minecraft","path":"coarse_dirt","source":"runtime:built_in_registry"}\n'
                '{"id":"minecraft:dirt","registry":"item","namespace":"minecraft","path":"dirt","source":"runtime:built_in_registry"}\n'
            ),
            "recipes": '{"id":"minecraft:crafting/dirt","type":"minecraft:crafting","serializer":"minecraft:crafting_shapeless","result_item":"minecraft:dirt","result_count":1,"ingredient_items":["minecraft:coarse_dirt"],"source":"runtime:recipe_manager"}\n',
        }
        _upload_sections(service, "forge-alpha", "dump_shared", alpha_sections)
        _upload_sections(service, "forge-beta", "dump_shared", beta_sections)

        self.assertEqual(
            "minecraft:stone",
            service.list_runtime_recipes("dump_shared", connector_id="forge-alpha")[0]["result_item"],
        )
        self.assertEqual(
            "minecraft:dirt",
            service.list_runtime_recipes("dump_shared", connector_id="forge-beta")[0]["result_item"],
        )
        self.assertEqual(1, service.runtime_index_summary("dump_shared", connector_id="forge-alpha")["recipes"])
        self.assertEqual(1, service.runtime_index_summary("dump_shared", connector_id="forge-beta")["recipes"])

        alpha_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0100",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "minecraft:stone 怎么做？",
                "context": {
                    "connector_id": "forge-alpha",
                    "dump_id": "dump_shared",
                    "item_id": "minecraft:stone",
                },
            }
        )["answer"]
        beta_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0101",
                "sent_at": "2026-06-14T08:16:00Z",
                "question": "minecraft:dirt 怎么做？",
                "context": {
                    "connector_id": "forge-beta",
                    "dump_id": "dump_shared",
                    "item_id": "minecraft:dirt",
                },
            }
        )["answer"]

        self.assertIn("minecraft:stone", alpha_answer["summary"])
        self.assertNotIn("minecraft:dirt", alpha_answer["summary"])
        self.assertIn({"kind": "recipe", "path": "minecraft:stonecutting/stone", "label": "minecraft:stone"}, alpha_answer["source_refs"])
        self.assertIn("minecraft:dirt", beta_answer["summary"])
        self.assertNotIn("minecraft:stone", beta_answer["summary"])
        self.assertIn({"kind": "recipe", "path": "minecraft:crafting/dirt", "label": "minecraft:dirt"}, beta_answer["source_refs"])

    def test_connector_scoped_runtime_lookup_does_not_fall_back_to_other_connector_with_same_dump_id(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "forge-alpha",
            "dump_shared",
            {
                "items": '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
                "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
            },
        )

        self.assertEqual(0, service.runtime_index_summary("dump_shared", connector_id="forge-beta")["recipes"])
        self.assertEqual([], service.list_runtime_recipes("dump_shared", connector_id="forge-beta"))

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0102",
                "sent_at": "2026-06-14T08:17:00Z",
                "question": "minecraft:stone 怎么做？",
                "context": {
                    "connector_id": "forge-beta",
                    "dump_id": "dump_shared",
                    "item_id": "minecraft:stone",
                },
            }
        )["answer"]

        self.assertNotIn("minecraft:stonecutting/stone", str(answer["source_refs"]))
        self.assertNotIn("minecraft:cobblestone", answer["summary"])
        self.assertIn({"kind": "protocol", "path": "docs/protocol/CONNECTOR_AGENT_PROTOCOL.md", "label": "Packwise protocol draft"}, answer["source_refs"])


class FakeChatClient:
    def __init__(self, response):
        self.response = response

    def complete(self, messages):
        self.messages = messages
        return self.response


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _upload_sections(service, connector_id, dump_id, sections):
    service.handle_runtime_dump_manifest(
        connector_id,
        {
            "protocol": "packwise.connector.v1",
            "message_type": "runtime_dump.manifest",
            "message_id": "msg_0200",
            "sent_at": "2026-06-14T08:10:00Z",
            "connector_id": connector_id,
            "dump_id": dump_id,
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "loader_version": "47.4.20",
            "sections": [
                {
                    "name": name,
                    "content_type": "application/x-ndjson",
                    "count": len([line for line in body.splitlines() if line.strip()]),
                    "sha256": _sha256(body),
                }
                for name, body in sections.items()
            ],
        },
    )
    for name, body in sections.items():
        service.handle_runtime_dump_section(connector_id, dump_id, name, "application/x-ndjson", body)


def _static_summary():
    return {
        "schema_version": "packwise.static_inspect.v1",
        "path": "/tmp/atm9sky",
        "pack": {"name": "All the Mods 9 - To the Sky", "version": "1.1.0", "translation_language": None},
        "loader": {"minecraft_version": "1.20.1", "name": "forge", "version": "47.4.20"},
        "adapter": {
            "pack_id": "all-the-mods-9-to-the-sky",
            "loader": "forge",
            "minecraft_version": "1.20.1",
            "quest_mod": "ftbquests",
            "known_progression_sources": ["advancements", "ftbquests", "kubejs"],
            "source_inventory": {},
            "optional_integrations": {"ftb_quests": {"present": True}},
        },
        "counts": {},
    }


def _quest_summary():
    return {
        "schema_version": "packwise.ftbquests.v1",
        "path": "/tmp/atm9sky/config/ftbquests/quests",
        "counts": {"chapters": 1, "quests": 1, "tasks": 1, "rewards": 0, "dependency_edges": 0},
        "stages": [],
        "chapters": [
            {
                "source_file": "chapters/start.snbt",
                "quests": [
                    {
                        "id": "quest_start",
                        "title": "Stone Start",
                        "tasks": [{"id": "task_stone", "type": "item", "item_id": "minecraft:stone", "item_count": 1}],
                        "rewards": [],
                        "dependencies": [],
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
