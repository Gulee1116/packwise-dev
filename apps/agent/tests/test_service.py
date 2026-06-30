import hashlib
import json
import re
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

    def test_llm_prompt_receives_retrieved_runtime_facts(self):
        chat_client = FakeChatClient("LLM summary from facts")
        service = AgentService(model_name="deepseek-v4-pro", chat_client=chat_client)
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_qa_01",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "热力系列里的 Hardened / Reinforced / Resonant 那堆升级件分别怎么做？升级顺序是什么？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_qa",
                    "item_id": "thermal:upgrade_augment_1",
                },
            }
        )["answer"]

        prompt = chat_client.messages[1].content
        self.assertTrue(answer["summary"].startswith("LLM summary from facts"))
        self.assertIn("强化升级组件（thermal:upgrade_augment_2）", answer["summary"])
        _assert_item_ids_parenthesized(
            self,
            answer["summary"],
            ["thermal:upgrade_augment_1", "thermal:upgrade_augment_2", "thermal:upgrade_augment_3"],
        )
        self.assertIn('"selected_connector_id": "atm9sky-dev-server"', prompt)
        self.assertIn('"selected_dump_id": "dump_qa"', prompt)
        self.assertIn('"runtime_dump_present": true', prompt)
        self.assertIn('"runtime_counts"', prompt)
        self.assertIn('"answer_readiness"', prompt)
        self.assertIn('"matched_recipes"', prompt)
        self.assertIn('"thermal:augments/upgrade_augment_1"', prompt)
        self.assertIn('"thermal:augments/upgrade_augment_2"', prompt)
        self.assertIn('"thermal:augments/upgrade_augment_3"', prompt)
        self.assertIn('"matched_quests"', prompt)
        self.assertIn('"source_refs"', prompt)
        self.assertIn('"item_labels"', prompt)
        self.assertIn("必须区分已验证的 recipe/effect facts", prompt)
        self.assertIn("不要把已验证路线改写成最容易、最早、最便宜、最好、首选或推荐第一", prompt)
        self.assertIn('"thermal:upgrade_augment_1": "硬化升级组件（thermal:upgrade_augment_1）"', prompt)
        self.assertIn("thermal:upgrade_augment_2", prompt)
        self.assertIn("thermal:upgrade_augment_3", prompt)

    def test_llm_conflict_with_validated_dump_falls_back_to_runtime_summary(self):
        service = AgentService(
            model_name="deepseek-v4-pro",
            chat_client=FakeChatClient("我没有 runtime dump，也没有索引，所以没有配方数据。"),
        )
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_qa_02",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "热力系列里的 Hardened / Reinforced / Resonant 那堆升级件分别怎么做？升级顺序是什么？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_qa"},
            }
        )["answer"]

        self.assertNotIn("没有 runtime dump", answer["summary"])
        self.assertNotIn("没有索引", answer["summary"])
        self.assertIn("硬化升级组件（thermal:upgrade_augment_1）", answer["summary"])
        self.assertIn("强化升级组件（thermal:upgrade_augment_2）", answer["summary"])
        self.assertIn("谐振升级组件（thermal:upgrade_augment_3）", answer["summary"])
        _assert_no_naked_item_id_chain(self, answer["summary"])

    def test_llm_route_ranking_claim_without_acquisition_evidence_falls_back(self):
        unsafe_responses = [
            "天使戒指是最容易、最早的创造飞行方案，推荐第一。",
            "天使戒指是创造飞行的优先推荐路线。",
            "天使戒指是创造飞行路线，推荐优先。",
            "建议先做天使戒指作为创造飞行路线。",
            "创造飞行路线推荐先走天使戒指。",
            "优先考虑天使戒指作为创造飞行路线。",
            "首推天使戒指作为创造飞行路线。",
            "天使戒指是创造飞行的第一推荐。",
            "Angel Ring is the priority route for creative flight.",
            "Angel Ring is the first choice for creative flight.",
            "Start with Angel Ring for creative flight.",
            "Use Angel Ring first for creative flight.",
            "Go for Angel Ring as the creative flight route.",
            "它是首选。",
            "建议先做它。",
            "This is the first choice.",
            "Use it first.",
            "它更早。",
            "这个更好。",
            "This is cheaper.",
            "Pick that one.",
            "天使戒指。",
            "Angel Ring.",
            "走天使戒指路线。",
            "用天使戒指路线。",
        ]
        for unsafe_response in unsafe_responses:
            with self.subTest(unsafe_response=unsafe_response):
                service = AgentService(
                    model_name="deepseek-v4-pro",
                    chat_client=FakeChatClient(unsafe_response),
                )
                _upload_sections(
                    service,
                    "atm9sky-dev-server",
                    "dump_runtime",
                    _creative_flight_sections(include_semantics=True),
                )

                answer = service.handle_ask(
                    {
                        "protocol": "packwise.connector.v1",
                        "message_type": "query.ask",
                        "message_id": "msg_route_ranking_policy",
                        "sent_at": "2026-06-14T08:15:00Z",
                        "question": "天使戒指和神龙飞行模块哪个更早？",
                        "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
                    }
                )["answer"]

                self.assertIn("runtime recipes 找到这些结果物品的配方", answer["summary"])
                self.assertNotEqual(unsafe_response, answer["summary"])
                for unsafe_phrase in [
                    "最容易",
                    "最早",
                    "推荐第一",
                    "优先推荐路线",
                    "推荐优先",
                    "建议先",
                    "推荐先",
                    "优先考虑",
                    "首推",
                    "首选",
                    "第一推荐",
                    "priority route",
                    "first choice",
                    "cheaper",
                    "pick that one",
                    "start with",
                    "use angel ring first",
                    "use it first",
                    "go for",
                ]:
                    self.assertNotIn(unsafe_phrase, answer["summary"].lower())

    def test_llm_route_disjunction_question_without_ranking_evidence_falls_back(self):
        service = AgentService(
            model_name="deepseek-v4-pro",
            chat_client=FakeChatClient("Angel Ring."),
        )
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", _creative_flight_sections(include_semantics=True))

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_route_or_policy",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "Angel Ring or Draconic flight module?",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]

        self.assertIn("runtime recipes 找到这些结果物品的配方", answer["summary"])
        self.assertIn("天使戒指", answer["summary"])
        self.assertNotEqual("Angel Ring.", answer["summary"])

    def test_llm_summary_is_supplemented_with_missing_runtime_item_ids(self):
        service = AgentService(
            model_name="deepseek-v4-pro",
            chat_client=FakeChatClient("EverlastingAbilities 已安装。先做 Ability Bottle，再看 Ability Totem 任务。"),
        )
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_qa_02b",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "Everlasting Abilities 这个模组任务书里完全没写，它到底是干什么的？我该怎么开始用？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_qa"},
            }
        )["answer"]

        self.assertIn("能力瓶（everlastingabilities:ability_bottle）", answer["summary"])
        self.assertIn("能力图腾（everlastingabilities:ability_totem）", answer["summary"])
        self.assertIn("先做 Ability Bottle", answer["summary"])
        _assert_item_ids_parenthesized(
            self,
            answer["summary"],
            ["everlastingabilities:ability_bottle", "everlastingabilities:ability_totem"],
        )
        self.assertIn("{atm9.quest.start2.totem}", answer["summary"])

    def test_everlasting_abilities_mod_question_uses_mod_namespace_not_distractor_item(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_qa_03",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "Everlasting Abilities 这个模组任务书里完全没写，它到底是干什么的？我该怎么开始用？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_qa"},
            }
        )["answer"]

        source_refs = str(answer["source_refs"])
        player_text = answer["summary"] + "\n" + "\n".join(answer["next_steps"])
        self.assertIn("EverlastingAbilities 2.3.1", answer["summary"])
        self.assertIn("能力瓶（everlastingabilities:ability_bottle）", player_text)
        self.assertIn("能力图腾（everlastingabilities:ability_totem）", player_text)
        self.assertIn("粉色黏液（industrialforegoing:pink_slime）", answer["summary"])
        self.assertIn("{atm9.quest.start2.totem}", answer["summary"])
        self.assertIn("JEI 搜 @everlastingabilities", answer["summary"])
        _assert_item_ids_parenthesized(
            self,
            player_text,
            [
                "everlastingabilities:ability_bottle",
                "everlastingabilities:ability_totem",
                "industrialforegoing:pink_slime",
            ],
        )
        _assert_no_naked_item_id_chain(self, player_text)
        self.assertIn("everlastingabilities:ability_bottle", source_refs)
        self.assertIn("everlastingabilities:ability_totem_recycle", source_refs)
        self.assertIn("dump_qa/ftb_quests#73921D0DAD4CBDAE", source_refs)
        self.assertNotIn("chemlib:tin", source_refs)
        self.assertNotIn("chemlib:tin", answer["summary"])

    def test_thermal_upgrade_question_uses_upgrade_family_not_itemfilters_or(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_qa_04",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "热力系列里的 Hardened / Reinforced / Resonant 那堆升级件分别怎么做？升级顺序是什么？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_qa"},
            }
        )["answer"]

        source_refs = str(answer["source_refs"])
        player_text = answer["summary"] + "\n" + "\n".join(answer["next_steps"])
        self.assertIn("硬化升级组件（thermal:upgrade_augment_1）", player_text)
        self.assertIn("强化升级组件（thermal:upgrade_augment_2）", player_text)
        self.assertIn("谐振升级组件（thermal:upgrade_augment_3）", player_text)
        self.assertIn("龙钢升级组件（thermal_extra:upgrade_augment）", player_text)
        self.assertIn(
            "硬化升级组件（thermal:upgrade_augment_1） -> 强化升级组件（thermal:upgrade_augment_2） -> 谐振升级组件（thermal:upgrade_augment_3）",
            answer["summary"],
        )
        self.assertNotIn("thermal:upgrade_augment_1 -> thermal:upgrade_augment_2 -> thermal:upgrade_augment_3", answer["summary"])
        _assert_item_ids_parenthesized(
            self,
            player_text,
            [
                "thermal:upgrade_augment_1",
                "thermal:upgrade_augment_2",
                "thermal:upgrade_augment_3",
                "thermal_extra:upgrade_augment",
            ],
        )
        _assert_no_naked_item_id_chain(self, player_text)
        self.assertIn("thermal:augments/upgrade_augment_1", source_refs)
        self.assertIn("thermal:augments/upgrade_augment_2", source_refs)
        self.assertIn("thermal:augments/upgrade_augment_3", source_refs)
        self.assertIn("thermal_extra:crafting/dragonsteel_integral_component", source_refs)
        self.assertIn("dump_qa/ftb_quests#348EAF1F97CA1521", source_refs)
        self.assertNotIn("itemfilters:or", source_refs)
        self.assertNotIn("itemfilters:or", answer["summary"])

    def test_item_id_anchors_keep_correct_source_refs_with_related_items(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        everlasting = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_qa_05",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "Everlasting Abilities 这个模组任务书里完全没写，它到底是干什么的？我该怎么开始用？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_qa",
                    "item_id": "everlastingabilities:ability_totem",
                },
            }
        )["answer"]
        thermal = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_qa_06",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "热力系列里的 Hardened / Reinforced / Resonant 那堆升级件分别怎么做？升级顺序是什么？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_qa",
                    "item_id": "thermal:upgrade_augment_1",
                },
            }
        )["answer"]

        everlasting_refs = str(everlasting["source_refs"])
        thermal_refs = str(thermal["source_refs"])
        self.assertIn("dump_qa/ftb_quests#73921D0DAD4CBDAE", everlasting_refs)
        self.assertIn("everlastingabilities:ability_totem_recycle", everlasting_refs)
        self.assertIn("能力瓶（everlastingabilities:ability_bottle）", everlasting["summary"])
        _assert_item_ids_parenthesized(
            self,
            everlasting["summary"] + "\n" + "\n".join(everlasting["next_steps"]),
            ["everlastingabilities:ability_bottle", "everlastingabilities:ability_totem"],
        )
        self.assertIn("thermal:augments/upgrade_augment_1", thermal_refs)
        self.assertIn("thermal:augments/upgrade_augment_2", thermal_refs)
        self.assertIn("thermal:augments/upgrade_augment_3", thermal_refs)
        self.assertIn("dump_qa/ftb_quests#348EAF1F97CA1521", thermal_refs)
        self.assertIn("强化升级组件（thermal:upgrade_augment_2）", thermal["summary"])
        self.assertIn("谐振升级组件（thermal:upgrade_augment_3）", thermal["summary"])
        _assert_item_ids_parenthesized(
            self,
            thermal["summary"] + "\n" + "\n".join(thermal["next_steps"]),
            ["thermal:upgrade_augment_1", "thermal:upgrade_augment_2", "thermal:upgrade_augment_3"],
        )

    def test_exact_item_question_does_not_expand_to_upgrade_family(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_exact_upgrade",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "thermal:upgrade_augment_1 怎么做？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_qa"},
            }
        )["answer"]

        player_text = answer["summary"] + "\n" + "\n".join(answer["next_steps"])
        source_refs = str(answer["source_refs"])
        direct_recipe_refs = [ref for ref in answer["source_refs"] if ref["kind"] == "recipe"]
        self.assertIn({"kind": "recipe", "path": "thermal:augments/upgrade_augment_1", "label": "thermal:upgrade_augment_1"}, direct_recipe_refs)
        self.assertNotIn("thermal:augments/upgrade_augment_2", str(direct_recipe_refs))
        self.assertNotIn("thermal:augments/upgrade_augment_3", str(direct_recipe_refs))
        self.assertNotIn("thermal_extra:crafting/dragonsteel_integral_component", str(direct_recipe_refs))
        self.assertNotIn("thermal:augments/upgrade_augment_2", source_refs)
        self.assertIn("硬化升级组件（thermal:upgrade_augment_1）", player_text)
        self.assertNotIn("强化升级组件（thermal:upgrade_augment_2）", player_text)
        self.assertNotIn("谐振升级组件（thermal:upgrade_augment_3）", player_text)

    def test_item_labels_prefer_runtime_names_and_match_display_name_questions(self):
        service = AgentService(model_name="deepseek-v4-pro")
        sections = {
            "items": (
                '{"id":"examplemod:translated_item","registry":"item","namespace":"examplemod","path":"translated_item","source":"runtime:built_in_registry","translation_key":"item.examplemod.translated_item","display_name":"Example Display","translated_name":"运行时译名"}\n'
                '{"id":"examplemod:old_dump_item","registry":"item","namespace":"examplemod","path":"old_dump_item","source":"runtime:built_in_registry"}\n'
            ),
            "recipes": (
                '{"id":"examplemod:translated_recipe","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"examplemod:translated_item","result_count":1,"ingredient_items":["examplemod:old_dump_item"],"source":"runtime:recipe_manager"}\n'
            ),
        }
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime_names", sections)

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_runtime_names",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "运行时译名 需要什么材料？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime_names"},
            }
        )["answer"]

        self.assertIn("运行时译名（examplemod:translated_item）", answer["summary"])
        self.assertIn("Old Dump Item（examplemod:old_dump_item）", answer["summary"])
        self.assertNotIn("Example Display（examplemod:translated_item）", answer["summary"])
        self.assertIn({"kind": "recipe", "path": "examplemod:translated_recipe", "label": "examplemod:translated_item"}, answer["source_refs"])

        display_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_runtime_display_name",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "Example Display 需要什么材料？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime_names"},
            }
        )["answer"]

        self.assertIn("运行时译名（examplemod:translated_item）", display_answer["summary"])
        self.assertIn({"kind": "recipe", "path": "examplemod:translated_recipe", "label": "examplemod:translated_item"}, display_answer["source_refs"])

    def test_item_id_namespace_selects_exact_mod_before_prefix_mod(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_qa", _qa_quality_sections())

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_thermal_extra_exact",
                "sent_at": "2026-06-14T08:15:00Z",
                "question": "thermal_extra:upgrade_augment 怎么做？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_qa"},
            }
        )["answer"]

        self.assertIn({"kind": "mod", "path": "dump_qa/mods#thermal_extra", "label": "Thermal Extra 3.0.0"}, answer["source_refs"])
        self.assertNotIn({"kind": "mod", "path": "dump_qa/mods#thermal", "label": "Thermal Series 11.0.0"}, answer["source_refs"])
        self.assertIn({"kind": "recipe", "path": "thermal_extra:crafting/dragonsteel_integral_component", "label": "thermal_extra:upgrade_augment"}, answer["source_refs"])

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

    def test_connector_scoped_runtime_prompt_does_not_mark_other_connector_dump_ready(self):
        chat_client = FakeChatClient("LLM scoped response")
        service = AgentService(model_name="deepseek-v4-pro", chat_client=chat_client)
        _upload_sections(
            service,
            "forge-alpha",
            "dump_shared",
            {
                "items": '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
                "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":[],"source":"runtime:recipe_manager"}\n',
            },
        )

        service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0103",
                "sent_at": "2026-06-14T08:18:00Z",
                "question": "minecraft:stone 怎么做？",
                "context": {
                    "connector_id": "forge-beta",
                    "dump_id": "dump_shared",
                    "item_id": "minecraft:stone",
                },
            }
        )

        prompt = chat_client.messages[1].content
        self.assertIn('"runtime_dump_present": false', prompt)
        self.assertIn('"runtime_dump": "selected_dump_id_without_manifest"', prompt)
        self.assertIn('"pack_index": "empty"', prompt)
        self.assertNotIn("minecraft:stonecutting/stone", prompt)

    def test_usage_recipes_do_not_get_reported_as_direct_item_recipes(self):
        service = AgentService(model_name="deepseek-v4-pro")
        sections = {
            "items": (
                '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
                '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
                '{"id":"minecraft:stone_button","registry":"item","namespace":"minecraft","path":"stone_button","source":"runtime:built_in_registry"}\n'
            ),
            "recipes": (
                '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n'
                '{"id":"minecraft:crafting/stone_button","type":"minecraft:crafting","serializer":"minecraft:crafting_shaped","result_item":"minecraft:stone_button","result_count":1,"ingredient_items":["minecraft:stone"],"source":"runtime:recipe_manager"}\n'
            ),
        }
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", sections)

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0104",
                "sent_at": "2026-06-14T08:19:00Z",
                "question": "minecraft:stone 怎么做？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_runtime",
                    "item_id": "minecraft:stone",
                },
            }
        )["answer"]

        self.assertIn("1 条配方", answer["summary"])
        self.assertIn({"kind": "recipe", "path": "minecraft:stonecutting/stone", "label": "minecraft:stone"}, answer["source_refs"])
        self.assertNotIn("minecraft:crafting/stone_button", str([ref for ref in answer["source_refs"] if ref["kind"] == "recipe"]))

    def test_mod_level_item_summary_cites_runtime_items_section(self):
        service = AgentService(model_name="deepseek-v4-pro")
        sections = {
            "mods": '{"mod_id":"examplemod","display_name":"Example Mod","version":"1.0.0","source":"forge:ModList"}\n',
            "items": '{"id":"examplemod:starter","registry":"item","namespace":"examplemod","path":"starter","source":"runtime:built_in_registry"}\n',
        }
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", sections)

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0105",
                "sent_at": "2026-06-14T08:20:00Z",
                "question": "Example Mod 这个 mod 怎么开始用？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]

        self.assertIn("examplemod:starter", answer["summary"])
        self.assertIn({"kind": "runtime_dump_section", "path": "dump_runtime/items", "label": "Runtime items"}, answer["source_refs"])

    def test_creative_flight_answer_reports_verified_flying_charm_route_without_ranking(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", _creative_flight_sections(include_semantics=True))

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_creative_flight",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "如何获取创造飞行？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]

        self.assertIn("已验证的一条创造飞行路线", answer["summary"])
        self.assertIn("飞行护符", answer["summary"])
        self.assertIn("3 瓶飞行药水 + 6 个烈焰粉 -> 飞行护符 -> 创造飞行", answer["summary"])
        self.assertIn("右键启用", answer["summary"])
        self.assertIn("背包", answer["summary"])
        self.assertIn("Curios", answer["summary"])
        self.assertIn("还没有排名飞行药水的获取难度", answer["summary"])
        self.assertIn("没有比较酿造、掉落、战利品、机器链、任务/stage 或玩家进度成本", answer["summary"])
        self.assertIn("其他可见路线仍可查", answer["summary"])
        self.assertIn("这些路线的 runtime 配方中出现了看起来更后期的材料", answer["summary"])
        for unsafe_phrase in ["优先路线", "飞行护符应排在", "最容易", "最早", "最便宜", "最好", "最佳", "首选", "推荐第一"]:
            self.assertNotIn(unsafe_phrase, answer["summary"])
        self.assertLess(answer["summary"].index("飞行护符"), answer["summary"].index("天使戒指"))
        refs = str(answer["source_refs"])
        self.assertIn("apotheosis:potion_charm", refs)
        self.assertIn("dump_runtime/potions#apotheosis:flying", refs)
        self.assertIn("dump_runtime/mob_effects#attributeslib:flying", refs)
        self.assertIn("attributeslib:creative_flight", refs)
        self.assertEqual("high", answer["confidence"])

    def test_creative_flight_answer_omits_later_material_hint_without_recipe_markers(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(
            service,
            "atm9sky-dev-server",
            "dump_runtime",
            _creative_flight_sections(include_semantics=True, other_route_late_materials=False),
        )

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_creative_flight_no_late_hint",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "如何获取创造飞行？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]

        self.assertIn("已验证的一条创造飞行路线", answer["summary"])
        self.assertIn("其他可见路线仍可查", answer["summary"])
        self.assertNotIn("看起来更后期", answer["summary"])
        self.assertNotIn("应排在", answer["summary"])

    def test_creative_flight_answer_does_not_invent_charm_route_without_potion_effect_sections(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", _creative_flight_sections(include_semantics=False))

        answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_creative_flight_missing",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "如何获取创造飞行？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]

        self.assertIn("不能验证", answer["summary"])
        self.assertIn("runtime potions", answer["summary"])
        self.assertIn("runtime mob_effects", answer["summary"])
        self.assertNotIn("3 瓶飞行药水 + 6 个烈焰粉", answer["summary"])
        self.assertEqual("low", answer["confidence"])

    def test_existing_creative_flight_route_items_remain_directly_discoverable(self):
        service = AgentService(model_name="deepseek-v4-pro")
        _upload_sections(service, "atm9sky-dev-server", "dump_runtime", _creative_flight_sections(include_semantics=True))

        angel_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_angel_ring",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "天使戒指怎么做？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]
        swiftwolf_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_swiftwolf",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "疾风戒指怎么做？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]
        draconic_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_draconic_flight",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "神龙飞行模块怎么做？",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]
        english_draconic_answer = service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_draconic_flight_en",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "How do I craft Draconic flight module?",
                "context": {"connector_id": "atm9sky-dev-server", "dump_id": "dump_runtime"},
            }
        )["answer"]

        self.assertIn("天使戒指", angel_answer["summary"])
        self.assertIn({"kind": "recipe", "path": "angelring:angel_ring", "label": "angelring:angel_ring"}, angel_answer["source_refs"])
        self.assertIn("疾风戒指", swiftwolf_answer["summary"])
        self.assertIn(
            {"kind": "recipe", "path": "projecte:swiftwolf_rending_gale", "label": "projecte:swiftwolf_rending_gale"},
            swiftwolf_answer["source_refs"],
        )
        self.assertIn("神龙飞行模块", draconic_answer["summary"])
        self.assertIn(
            {"kind": "recipe", "path": "draconicevolution:modules/item_draconic_flight", "label": "draconicevolution:item_draconic_flight"},
            draconic_answer["source_refs"],
        )
        self.assertIn("神龙飞行模块", english_draconic_answer["summary"])
        self.assertIn(
            {"kind": "recipe", "path": "draconicevolution:modules/item_draconic_flight", "label": "draconicevolution:item_draconic_flight"},
            english_draconic_answer["source_refs"],
        )

    def test_llm_prompt_redacts_unapproved_context_fields(self):
        chat_client = FakeChatClient("LLM summary")
        service = AgentService(model_name="deepseek-v4-pro", chat_client=chat_client)

        service.handle_ask(
            {
                "protocol": "packwise.connector.v1",
                "message_type": "query.ask",
                "message_id": "msg_0106",
                "sent_at": "2026-06-14T08:21:00Z",
                "question": "这个东西从哪来？",
                "context": {
                    "connector_id": "atm9sky-dev-server",
                    "dump_id": "dump_runtime",
                    "item_id": "minecraft:stone",
                    "api_key": "secret-value",
                    "session_token": "session-secret",
                    "nested": {"token": "nested-secret"},
                },
            }
        )

        prompt = chat_client.messages[1].content
        self.assertIn('"connector_id": "atm9sky-dev-server"', prompt)
        self.assertIn('"item_id": "minecraft:stone"', prompt)
        self.assertNotIn("api_key", prompt)
        self.assertNotIn("secret-value", prompt)
        self.assertNotIn("session_token", prompt)
        self.assertNotIn("session-secret", prompt)
        self.assertNotIn("nested-secret", prompt)


class FakeChatClient:
    def __init__(self, response):
        self.response = response

    def complete(self, messages):
        self.messages = messages
        return self.response


def _creative_flight_sections(include_semantics=True, other_route_late_materials=True):
    items = _ndjson(
        [
            "apotheosis:potion_charm",
            "minecraft:potion",
            "minecraft:blaze_powder",
            "angelring:angel_ring",
            "minecraft:diamond",
            "minecraft:feather",
            "minecraft:nether_star",
            "projecte:swiftwolf_rending_gale",
            "projecte:dark_matter",
            "projecte:iron_band",
            "draconicevolution:item_draconic_flight",
            "draconicevolution:item_wyvern_flight",
            "draconicevolution:awakened_draconium_ingot",
            "draconicevolution:wyvern_core",
        ],
        item_payload=True,
    )
    angel_second_item = "minecraft:nether_star" if other_route_late_materials else "minecraft:feather"
    swiftwolf_first_item = "projecte:dark_matter" if other_route_late_materials else "minecraft:diamond"
    draconic_materials = (
        [
            "draconicevolution:item_wyvern_flight",
            "draconicevolution:awakened_draconium_ingot",
            "draconicevolution:wyvern_core",
        ]
        if other_route_late_materials
        else ["minecraft:diamond", "projecte:iron_band", "minecraft:feather"]
    )
    recipes = _ndjson(
        [
            {
                "id": "apotheosis:potion_charm",
                "type": "minecraft:crafting",
                "serializer": "apotheosis:potion_charm",
                "result_item": "apotheosis:potion_charm",
                "result_count": 1,
                "ingredient_items": ["minecraft:potion", "minecraft:blaze_powder"],
                "ingredient_slots": [
                    {"slot": 0, "empty": False, "item_ids": ["minecraft:potion"], "candidates": [{"item_id": "minecraft:potion", "count": 1}]},
                    {"slot": 1, "empty": False, "item_ids": ["minecraft:potion"], "candidates": [{"item_id": "minecraft:potion", "count": 1}]},
                    {"slot": 2, "empty": False, "item_ids": ["minecraft:potion"], "candidates": [{"item_id": "minecraft:potion", "count": 1}]},
                    {"slot": 3, "empty": False, "item_ids": ["minecraft:blaze_powder"], "candidates": [{"item_id": "minecraft:blaze_powder", "count": 1}]},
                    {"slot": 4, "empty": False, "item_ids": ["minecraft:blaze_powder"], "candidates": [{"item_id": "minecraft:blaze_powder", "count": 1}]},
                    {"slot": 5, "empty": False, "item_ids": ["minecraft:blaze_powder"], "candidates": [{"item_id": "minecraft:blaze_powder", "count": 1}]},
                    {"slot": 6, "empty": False, "item_ids": ["minecraft:blaze_powder"], "candidates": [{"item_id": "minecraft:blaze_powder", "count": 1}]},
                    {"slot": 7, "empty": False, "item_ids": ["minecraft:blaze_powder"], "candidates": [{"item_id": "minecraft:blaze_powder", "count": 1}]},
                    {"slot": 8, "empty": False, "item_ids": ["minecraft:blaze_powder"], "candidates": [{"item_id": "minecraft:blaze_powder", "count": 1}]},
                ],
                "width": 3,
                "height": 3,
                "source": "runtime:recipe_manager",
            },
            {
                "id": "angelring:angel_ring",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "angelring:angel_ring",
                "result_count": 1,
                "ingredient_items": ["minecraft:diamond", angel_second_item],
                "ingredient_slots": [
                    {"slot": 0, "empty": False, "item_ids": ["minecraft:diamond"], "candidates": [{"item_id": "minecraft:diamond", "count": 1}]},
                    {"slot": 1, "empty": False, "item_ids": [angel_second_item], "candidates": [{"item_id": angel_second_item, "count": 1}]},
                ],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "projecte:swiftwolf_rending_gale",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "projecte:swiftwolf_rending_gale",
                "result_count": 1,
                "ingredient_items": [swiftwolf_first_item, "projecte:iron_band", "minecraft:feather"],
                "ingredient_slots": [
                    {"slot": 0, "empty": False, "item_ids": [swiftwolf_first_item], "candidates": [{"item_id": swiftwolf_first_item, "count": 1}]},
                    {"slot": 1, "empty": False, "item_ids": ["minecraft:feather"], "candidates": [{"item_id": "minecraft:feather", "count": 1}]},
                    {"slot": 4, "empty": False, "item_ids": ["projecte:iron_band"], "candidates": [{"item_id": "projecte:iron_band", "count": 1}]},
                ],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "draconicevolution:modules/item_draconic_flight",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "draconicevolution:item_draconic_flight",
                "result_count": 1,
                "ingredient_items": draconic_materials,
                "ingredient_slots": [
                    {"slot": 0, "empty": False, "item_ids": [draconic_materials[1]], "candidates": [{"item_id": draconic_materials[1], "count": 1}]},
                    {"slot": 4, "empty": False, "item_ids": [draconic_materials[0]], "candidates": [{"item_id": draconic_materials[0], "count": 1}]},
                    {"slot": 5, "empty": False, "item_ids": [draconic_materials[2]], "candidates": [{"item_id": draconic_materials[2], "count": 1}]},
                ],
                "source": "runtime:recipe_manager",
            },
        ]
    )
    sections = {"items": items, "recipes": recipes}
    if include_semantics:
        sections["potions"] = _ndjson(
            [
                {
                    "id": "apotheosis:flying",
                    "translation_key": "item.minecraft.potion.effect.flying",
                    "display_name": "Potion of Flying",
                    "effects": [{"effect_id": "attributeslib:flying", "duration": 3600, "amplifier": 0}],
                    "source": "runtime:potion_registry",
                }
            ]
        )
        sections["mob_effects"] = _ndjson(
            [
                {
                    "id": "attributeslib:flying",
                    "translation_key": "effect.attributeslib.flying",
                    "display_name": "Flying",
                    "attribute_modifiers": [
                        {
                            "attribute_id": "attributeslib:creative_flight",
                            "name": "Creative flight",
                            "uuid": "00000000-0000-0000-0000-000000000001",
                            "operation": "ADDITION",
                            "amount": 1.0,
                        }
                    ],
                    "source": "runtime:mob_effect_registry",
                }
            ]
        )
    return sections


def _qa_quality_sections():
    mods = _ndjson(
        [
            {"mod_id": "everlastingabilities", "display_name": "EverlastingAbilities", "version": "2.3.1", "source": "forge:ModList"},
            {"mod_id": "thermal", "display_name": "Thermal Series", "version": "11.0.0", "source": "forge:ModList"},
            {"mod_id": "thermal_extra", "display_name": "Thermal Extra", "version": "3.0.0", "source": "forge:ModList"},
            {"mod_id": "chemlib", "display_name": "ChemLib", "version": "2.0.0", "source": "forge:ModList"},
            {"mod_id": "itemfilters", "display_name": "Item Filters", "version": "2001.1.0", "source": "forge:ModList"},
        ]
    )
    items = _ndjson(
        [
            "everlastingabilities:ability_bottle",
            "everlastingabilities:ability_totem",
            "industrialforegoing:pink_slime",
            "minecraft:bucket",
            "minecraft:gold_nugget",
            "minecraft:potion",
            "minecraft:slime_ball",
            "minecraft:white_dye",
            "xycraft_machines:resin_ball",
            "thermal:upgrade_augment_1",
            "thermal:upgrade_augment_2",
            "thermal:upgrade_augment_3",
            "thermal_extra:upgrade_augment",
            "thermal:gold_gear",
            "thermal:invar_ingot",
            "minecraft:glass",
            "minecraft:redstone",
            "thermal:signalum_gear",
            "minecraft:quartz",
            "thermal:lumium_gear",
            "thermal:enderium_ingot",
            "thermal_extra:ancient_dust",
            "thermal_extra:dragonsteel_gear",
            "chemlib:tin",
            "itemfilters:or",
        ],
        item_payload=True,
    )
    recipes = _ndjson(
        [
            {
                "id": "everlastingabilities:ability_bottle",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "everlastingabilities:ability_bottle",
                "result_count": 1,
                "ingredient_items": [
                    "industrialforegoing:pink_slime",
                    "minecraft:bucket",
                    "minecraft:gold_nugget",
                    "minecraft:slime_ball",
                    "minecraft:white_dye",
                    "xycraft_machines:resin_ball",
                ],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "everlastingabilities:ability_totem_recycle",
                "type": "minecraft:crafting",
                "serializer": "everlastingabilities:crafting_special_totem_recycle",
                "result_item": "everlastingabilities:ability_totem",
                "result_count": 1,
                "ingredient_items": [],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "everlastingabilities:gold_nugget_from_blasting",
                "type": "minecraft:blasting",
                "serializer": "minecraft:blasting",
                "result_item": "minecraft:gold_nugget",
                "result_count": 1,
                "ingredient_items": ["everlastingabilities:ability_totem"],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "thermal:augments/upgrade_augment_1",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "thermal:upgrade_augment_1",
                "result_count": 1,
                "ingredient_items": ["thermal:gold_gear", "thermal:invar_ingot", "minecraft:glass", "minecraft:redstone"],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "thermal:augments/upgrade_augment_2",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "thermal:upgrade_augment_2",
                "result_count": 1,
                "ingredient_items": ["thermal:upgrade_augment_1", "thermal:signalum_gear", "minecraft:quartz"],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "thermal:augments/upgrade_augment_3",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "thermal:upgrade_augment_3",
                "result_count": 1,
                "ingredient_items": ["thermal:upgrade_augment_2", "thermal:lumium_gear", "thermal:enderium_ingot"],
                "source": "runtime:recipe_manager",
            },
            {
                "id": "thermal_extra:crafting/dragonsteel_integral_component",
                "type": "minecraft:crafting",
                "serializer": "minecraft:crafting_shaped",
                "result_item": "thermal_extra:upgrade_augment",
                "result_count": 1,
                "ingredient_items": ["thermal:upgrade_augment_3", "thermal_extra:ancient_dust", "thermal_extra:dragonsteel_gear"],
                "source": "runtime:recipe_manager",
            },
        ]
    )
    quests = _ndjson(
        [
            {
                "quest_id": "73921D0DAD4CBDAE",
                "chapter_id": "02AFCEFE247BAD9F",
                "title": "{atm9.quest.start2.totem}",
                "dependencies": [],
                "dependency_types": {},
                "task_item_ids": ["everlastingabilities:ability_totem"],
                "reward_item_ids": ["minecraft:potion"],
                "source": "runtime:ftb_quests",
            },
            {
                "quest_id": "348EAF1F97CA1521",
                "chapter_id": "0F96DC3563DA78EF",
                "title": "{atm9.quest.ma.Upgrades}",
                "dependencies": [],
                "dependency_types": {},
                "task_item_ids": ["thermal:upgrade_augment_1"],
                "reward_item_ids": [],
                "source": "runtime:ftb_quests",
            },
            {
                "quest_id": "246CD1925FD6761C",
                "chapter_id": "658721DF03EC997D",
                "title": "Thermal Reinforced Upgrade",
                "dependencies": [],
                "dependency_types": {},
                "task_item_ids": ["thermal:upgrade_augment_2"],
                "reward_item_ids": [],
                "source": "runtime:ftb_quests",
            },
            {
                "quest_id": "034FC4BCCCD7D154",
                "chapter_id": "658721DF03EC997D",
                "title": "Thermal Resonant Upgrade",
                "dependencies": [],
                "dependency_types": {},
                "task_item_ids": ["thermal:upgrade_augment_3"],
                "reward_item_ids": [],
                "source": "runtime:ftb_quests",
            },
            {
                "quest_id": "76BCB8C0448EFE50",
                "chapter_id": "658721DF03EC997D",
                "title": "Thermal Extra Upgrade",
                "dependencies": [],
                "dependency_types": {},
                "task_item_ids": ["thermal_extra:upgrade_augment"],
                "reward_item_ids": [],
                "source": "runtime:ftb_quests",
            },
        ]
    )
    return {"mods": mods, "items": items, "recipes": recipes, "ftb_quests": quests}


def _ndjson(values, item_payload=False):
    payloads = []
    for value in values:
        if item_payload:
            namespace, _, path = value.partition(":")
            payloads.append(
                {
                    "id": value,
                    "registry": "item",
                    "namespace": namespace,
                    "path": path,
                    "source": "runtime:built_in_registry",
                }
            )
        else:
            payloads.append(value)
    return "\n".join(json.dumps(payload, separators=(",", ":")) for payload in payloads) + "\n"


def _assert_item_ids_parenthesized(test_case, text, item_ids):
    for item_id in item_ids:
        matches = list(re.finditer(re.escape(item_id), text))
        test_case.assertTrue(matches, f"{item_id} missing from player-facing text")
        for match in matches:
            before = text[match.start() - 1] if match.start() > 0 else ""
            after = text[match.end()] if match.end() < len(text) else ""
            test_case.assertIn(before, {"（", "("}, f"{item_id} is not parenthesized in {text!r}")
            test_case.assertIn(after, {"）", ")"}, f"{item_id} is not parenthesized in {text!r}")


def _assert_no_naked_item_id_chain(test_case, text):
    test_case.assertIsNone(
        re.search(r"\b[a-z0-9_.-]+:[a-z0-9_./-]+(?:\s*(?:,|->)\s*[a-z0-9_.-]+:[a-z0-9_./-]+)+", text),
        f"found naked registry ID chain/list in {text!r}",
    )


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
