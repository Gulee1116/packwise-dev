import hashlib
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from packwise_agent import phase1_acceptance as phase1_acceptance_module
from packwise_agent.http_api import make_server
from packwise_agent.phase1_acceptance import build_phase1_acceptance_report
from packwise_agent.runtime_dump_importer import import_runtime_dump_directory
from packwise_agent.service import AgentService


class Phase1AcceptanceTest(unittest.TestCase):
    def test_acceptance_report_passes_with_live_atm9sky_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertTrue(report["valid"])
        self.assertEqual("passed", report["status"])
        self.assertEqual("atm9sky", report["pack_index_summary"]["profile_id"])
        self.assertEqual([], report["next_actions"])
        jar_evidence = _check(report, "forge_jar_built")["evidence"]
        self.assertEqual("packwise_connector", jar_evidence["metadata"]["mod_id"])
        self.assertEqual("[47.0.0,48.0.0)", jar_evidence["metadata"]["forge_dependency_range"])
        self.assertEqual("[1.20.1,1.21)", jar_evidence["metadata"]["minecraft_dependency_range"])
        self.assertEqual([], jar_evidence["missing_metadata"])
        self.assertEqual([], jar_evidence["missing_entries"])
        self.assertEqual([], jar_evidence["forbidden_entries"])
        self.assertEqual([], jar_evidence["pack_specific_string_matches"])
        self.assertGreater(jar_evidence["size_bytes"], 0)
        self.assertRegex(jar_evidence["sha256"], r"^[0-9a-f]{64}$")
        dump_validation = _check(report, "runtime_dump_valid")["evidence"]
        self.assertEqual(str(dump_dir / "manifest.json"), dump_validation["manifest_path"])
        self.assertGreater(dump_validation["manifest_size_bytes"], 0)
        self.assertRegex(dump_validation["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("packwise_connector", dump_validation["connector_mod_id"])
        self.assertEqual("0.1.0", dump_validation["connector_version"])
        self.assertEqual([], dump_validation["runtime_consistency_errors"])
        section_evidence = {section["name"]: section for section in dump_validation["sections"]}
        self.assertGreater(section_evidence["recipes"]["size_bytes"], 0)
        self.assertRegex(section_evidence["recipes"]["sha256"], r"^[0-9a-f]{64}$")
        dump_connector = _check(report, "runtime_dump_connector_matches_jar")
        self.assertTrue(dump_connector["passed"])
        self.assertEqual("packwise_connector", dump_connector["evidence"]["manifest_connector_mod_id"])
        self.assertEqual("0.1.0", dump_connector["evidence"]["manifest_connector_version"])
        runtime_sections = _check(report, "phase1_runtime_sections_non_empty")
        self.assertTrue(runtime_sections["passed"])
        self.assertEqual([], runtime_sections["evidence"]["missing_or_empty"])
        self.assertEqual(1, runtime_sections["evidence"]["counts"]["blocks"])
        self.assertEqual(1, runtime_sections["evidence"]["counts"]["fluids"])
        self.assertEqual(1, runtime_sections["evidence"]["counts"]["advancements"])
        self.assertTrue(_check(report, "live_connector_loaded_seen")["passed"])
        loaded_evidence = _check(report, "live_connector_loaded_seen")["evidence"]
        self.assertTrue(loaded_evidence["generic_loaded_seen"])
        self.assertTrue(loaded_evidence["loaded_connector_mod_seen"])
        self.assertTrue(_check(report, "live_packwise_status_seen")["passed"])
        status_evidence = _check(report, "live_packwise_status_seen")["evidence"]
        self.assertGreater(status_evidence["size_bytes"], 0)
        self.assertRegex(status_evidence["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(status_evidence["status_identity_seen"])
        self.assertTrue(status_evidence["status_forge_major_seen"])
        self.assertTrue(status_evidence["status_connector_mod_seen"])
        self.assertEqual("packwise_connector 0.1.0", status_evidence["expected_connector_mod"])
        self.assertTrue(status_evidence["status_connector_id_seen"])
        self.assertTrue(status_evidence["status_pack_seen"])
        self.assertTrue(status_evidence["status_capabilities_seen"])
        self.assertTrue(status_evidence["status_optional_integrations_seen"])
        self.assertTrue(status_evidence["status_agent_url_seen"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        dump_evidence = _check(report, "live_packwise_dump_seen")["evidence"]
        self.assertTrue(dump_evidence["generic_dump_seen"])
        self.assertTrue(dump_evidence["dump_connector_id_seen"])
        self.assertTrue(dump_evidence["dump_id_detail_seen"])
        self.assertTrue(dump_evidence["dump_id_seen"])
        self.assertTrue(dump_evidence["dump_path_seen"])
        self.assertTrue(_check(report, "live_optional_diagnostics_seen")["passed"])
        self.assertTrue(_check(report, "live_packwise_ask_sources_seen")["passed"])
        ask_evidence = _check(report, "live_packwise_ask_sources_seen")["evidence"]
        self.assertTrue(ask_evidence["ask_answer_seen"])
        self.assertTrue(ask_evidence["ask_source_refs_seen"])
        self.assertIn("recipe:minecraft:stonecutting/stone", ask_evidence["ask_source_refs"])
        self.assertIn("runtime_dump_section:dump_1/recipes", ask_evidence["ask_dump_source_refs"])
        self.assertTrue(_check(report, "agent_runtime_dump_imports")["passed"])
        progression_truth = _check(report, "runtime_progression_truth_ready")
        self.assertFalse(progression_truth["required"])
        self.assertFalse(progression_truth["passed"])
        self.assertIn("player_progress", progression_truth["evidence"]["missing_or_not_runtime_authoritative"])
        self.assertIn("team_progress", progression_truth["evidence"]["missing_or_not_runtime_authoritative"])
        self.assertIn("stages", progression_truth["evidence"]["missing_or_not_runtime_authoritative"])
        second_pack = _check(report, "second_forge_1201_profile_available")
        self.assertTrue(second_pack["passed"])
        self.assertEqual("generic-forge-1201", second_pack["evidence"]["selected_profile_id"])
        self.assertIn("atm9sky", second_pack["evidence"]["profile_ids"])
        self.assertIn("generic-forge-1201", second_pack["evidence"]["profile_ids"])
        agent_import = report["agent_import_summary"]
        self.assertTrue(agent_import["passed"])
        self.assertEqual("atm9sky", agent_import["pack_index"]["profile_id"])
        self.assertEqual(1, agent_import["runtime_index_summary"]["recipes"])
        self.assertEqual(
            ["mods", "items", "blocks", "fluids", "tags", "recipes", "advancements"],
            agent_import["imported_sections"],
        )
        self.assertTrue(agent_import["instance_import"]["valid"])
        self.assertTrue(_check(report, "local_answer_has_source_refs")["passed"])
        local_answer_evidence = _check(report, "local_answer_has_source_refs")["evidence"]
        self.assertEqual("item_specific", local_answer_evidence["source_requirement"]["kind"])
        self.assertTrue(local_answer_evidence["source_requirement"]["passed"])
        self.assertTrue(local_answer_evidence["dump_source_requirement"]["passed"])
        self.assertEqual("dump_1", local_answer_evidence["dump_source_requirement"]["expected_dump_id"])
        self.assertTrue(_check(report, "local_answer_scenarios_have_source_refs")["passed"])
        self.assertEqual(
            ["next_step", "unlock", "jei_difference", "blocker"],
            [scenario["id"] for scenario in report["local_answer_scenarios"]],
        )
        self.assertTrue(all(scenario["source_refs"] for scenario in report["local_answer_scenarios"]))
        self.assertTrue(all(scenario["source_requirement"]["passed"] for scenario in report["local_answer_scenarios"]))
        self.assertTrue(all(scenario["dump_source_requirement"]["passed"] for scenario in report["local_answer_scenarios"]))

    def test_acceptance_report_marks_progression_runtime_truth_ready_when_optional_sections_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir, include_progression=True)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertTrue(report["valid"])
        progression_truth = _check(report, "runtime_progression_truth_ready")
        self.assertFalse(progression_truth["required"])
        self.assertTrue(progression_truth["passed"])
        self.assertEqual([], progression_truth["evidence"]["missing_or_not_runtime_authoritative"])
        self.assertEqual("runtime_authoritative", progression_truth["evidence"]["reconciliation"]["quests"])
        self.assertEqual("runtime_authoritative", progression_truth["evidence"]["reconciliation"]["player_progress"])
        self.assertEqual("runtime_authoritative", progression_truth["evidence"]["reconciliation"]["team_progress"])
        self.assertEqual("runtime_authoritative", progression_truth["evidence"]["reconciliation"]["stages"])
        self.assertEqual(2, progression_truth["evidence"]["runtime_counts"]["ftb_quests"])
        self.assertEqual("ready", progression_truth["evidence"]["answer_readiness"]["next_step_questions"])

    def test_acceptance_report_verifies_online_agent_when_agent_url_is_supplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = AgentService()
            _seed_online_agent(service, dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertTrue(report["valid"])
        online = _check(report, "online_agent_connector_status_seen")
        self.assertTrue(online["required"])
        self.assertTrue(online["passed"])
        self.assertTrue(online["evidence"]["hello_present"])
        self.assertTrue(online["evidence"]["connector_id_seen"])
        self.assertTrue(online["evidence"]["connector_mod_seen"])
        self.assertEqual("packwise_connector 0.1.0", online["evidence"]["expected_connector_mod"])
        self.assertTrue(online["evidence"]["dump_seen"])
        self.assertTrue(online["evidence"]["dump_identity_matches"])
        self.assertTrue(online["evidence"]["dump_connector_mod_seen"])
        self.assertTrue(online["evidence"]["dump_upload_complete"])
        self.assertEqual([], online["evidence"]["dump_missing_uploaded_sections"])
        self.assertTrue(online["evidence"]["dump_required_sections_non_empty"])
        self.assertEqual([], online["evidence"]["dump_missing_required_sections"])
        self.assertTrue(online["evidence"]["dump_runtime_consistency_valid"])
        self.assertEqual([], online["evidence"]["dump_runtime_consistency_errors"])
        self.assertTrue(online["evidence"]["pack_index_seen"])
        self.assertEqual("atm9sky", online["evidence"]["pack_index_profile_id"])
        self.assertTrue(online["evidence"]["pack_index_runtime_truth_ready"])
        self.assertEqual(1, online["evidence"]["pack_index_runtime_counts"]["recipes"])
        self.assertEqual("atm9sky-dev-server", online["evidence"]["connector"]["id"])
        self.assertEqual("dump_1", online["evidence"]["matching_dump"]["dump_id"])
        self.assertEqual("packwise_connector", online["evidence"]["matching_dump"]["connector_mod_id"])
        self.assertEqual("0.1.0", online["evidence"]["matching_dump"]["connector_version"])
        self.assertTrue(online["evidence"]["matching_dump"]["upload_complete"])
        self.assertEqual([], online["evidence"]["matching_dump"]["runtime_consistency_errors"])
        self.assertEqual(report["online_agent_summary"], online["evidence"])
        online_answer = _check(report, "online_agent_answer_has_source_refs")
        self.assertTrue(online_answer["required"])
        self.assertTrue(online_answer["passed"])
        self.assertTrue(online_answer["evidence"]["answer_seen"])
        self.assertEqual("item_specific", online_answer["evidence"]["source_requirement"]["kind"])
        self.assertTrue(online_answer["evidence"]["source_requirement"]["passed"])
        self.assertTrue(online_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual("dump_1", online_answer["evidence"]["dump_source_requirement"]["expected_dump_id"])
        self.assertTrue(
            any(ref["kind"] == "recipe" for ref in online_answer["evidence"]["source_refs"])
        )
        self.assertEqual(report["online_answer_summary"], online_answer["evidence"])

    def test_acceptance_report_blocks_when_online_agent_dump_connector_version_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            online_dump_dir = root / "online-packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_dump(online_dump_dir, connector_version="0.0.9")
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = AgentService()
            _seed_online_agent(service, online_dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        online = _check(report, "online_agent_connector_status_seen")
        self.assertTrue(online["required"])
        self.assertFalse(online["passed"])
        self.assertTrue(online["evidence"]["connector_mod_seen"])
        self.assertTrue(online["evidence"]["dump_seen"])
        self.assertTrue(online["evidence"]["dump_identity_matches"])
        self.assertFalse(online["evidence"]["dump_connector_mod_seen"])
        self.assertEqual("0.1.0", online["evidence"]["expected_connector_version"])
        self.assertEqual("0.0.9", online["evidence"]["matching_dump"]["connector_version"])
        self.assertTrue(_check(report, "online_agent_answer_has_source_refs")["passed"])
        self.assertTrue(
            _check(report, "online_agent_answer_has_source_refs")["evidence"]["dump_source_requirement"]["passed"]
        )
        self.assertEqual(
            ["online_agent_connector_status_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_blocks_when_online_agent_dump_has_runtime_consistency_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            online_dump_dir = root / "online-packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_dump(
                online_dump_dir,
                section_overrides={
                    "tags": (
                        '{"registry":"item","tag":"forge:stone","entry_count":1,'
                        '"entries":["minecraft:missing_stone"],"source":"runtime:registry_tags"}\n'
                    ),
                },
            )
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = AgentService()
            _seed_online_agent_without_file_validation(service, online_dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertTrue(_check(report, "runtime_dump_valid")["passed"])
        online = _check(report, "online_agent_connector_status_seen")
        self.assertTrue(online["required"])
        self.assertFalse(online["passed"])
        self.assertTrue(online["evidence"]["dump_seen"])
        self.assertTrue(online["evidence"]["dump_identity_matches"])
        self.assertTrue(online["evidence"]["dump_required_sections_non_empty"])
        self.assertFalse(online["evidence"]["dump_runtime_consistency_valid"])
        consistency_errors = online["evidence"]["dump_runtime_consistency_errors"]
        self.assertEqual(consistency_errors, online["evidence"]["matching_dump"]["runtime_consistency_errors"])
        self.assertIn(
            "Tag item:forge:stone entries missing from item registry: minecraft:missing_stone",
            consistency_errors,
        )
        self.assertTrue(online["evidence"]["pack_index_seen"])
        self.assertTrue(online["evidence"]["pack_index_runtime_truth_ready"])
        self.assertFalse(_check(report, "online_agent_answer_has_source_refs")["passed"])
        self.assertEqual(
            ["online_agent_connector_status_seen", "online_agent_answer_has_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_blocks_when_online_answer_lacks_expected_dump_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = RecipeOnlyAnswerService()
            _seed_online_agent(service, dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertTrue(_check(report, "online_agent_connector_status_seen")["passed"])
        online_answer = _check(report, "online_agent_answer_has_source_refs")
        self.assertTrue(online_answer["required"])
        self.assertFalse(online_answer["passed"])
        self.assertTrue(online_answer["evidence"]["source_requirement"]["passed"])
        self.assertFalse(online_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual([], online_answer["evidence"]["dump_source_requirement"]["matching_refs"])
        self.assertEqual(
            ["online_agent_answer_has_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_local_answer_without_expected_dump_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            original_ask_local = phase1_acceptance_module.ask_local
            phase1_acceptance_module.ask_local = _recipe_only_local_answer
            try:
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    item_id="minecraft:stone",
                )
            finally:
                phase1_acceptance_module.ask_local = original_ask_local

        self.assertFalse(report["valid"])
        self.assertTrue(_check(report, "runtime_dump_valid")["passed"])
        local_answer = _check(report, "local_answer_has_source_refs")
        self.assertFalse(local_answer["passed"])
        self.assertTrue(local_answer["evidence"]["source_requirement"]["passed"])
        self.assertFalse(local_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual([], local_answer["evidence"]["dump_source_requirement"]["matching_refs"])
        scenarios = _check(report, "local_answer_scenarios_have_source_refs")
        self.assertFalse(scenarios["passed"])
        self.assertEqual(
            ["next_step", "unlock", "jei_difference", "blocker"],
            scenarios["evidence"]["failed_scenarios"],
        )
        self.assertTrue(all(
            scenario["source_requirement"]["passed"]
            for scenario in report["local_answer_scenarios"]
        ))
        self.assertFalse(any(
            scenario["dump_source_requirement"]["passed"]
            for scenario in report["local_answer_scenarios"]
        ))
        self.assertEqual(
            ["local_answer_has_source_refs", "local_answer_scenarios_have_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_local_answer_with_wrong_item_recipe_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            original_ask_local = phase1_acceptance_module.ask_local
            phase1_acceptance_module.ask_local = _wrong_recipe_local_answer
            try:
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    item_id="minecraft:stone",
                )
            finally:
                phase1_acceptance_module.ask_local = original_ask_local

        self.assertFalse(report["valid"])
        local_answer = _check(report, "local_answer_has_source_refs")
        source_requirement = local_answer["evidence"]["source_requirement"]
        self.assertFalse(local_answer["passed"])
        self.assertFalse(source_requirement["passed"])
        self.assertEqual(["minecraft:stonecutting/stone"], source_requirement["expected_recipe_ids"])
        self.assertEqual(["chapters/start.snbt#quest_start"], source_requirement["expected_quest_paths"])
        self.assertEqual([], source_requirement["matching_recipe_refs"])
        self.assertEqual(
            [{"kind": "recipe", "path": "minecraft:crafting/dirt", "label": "minecraft:dirt"}],
            source_requirement["recipe_refs"],
        )
        self.assertTrue(local_answer["evidence"]["dump_source_requirement"]["passed"])
        scenarios = {scenario["id"]: scenario for scenario in report["local_answer_scenarios"]}
        self.assertTrue(scenarios["next_step"]["passed"])
        self.assertFalse(scenarios["unlock"]["passed"])
        self.assertTrue(scenarios["jei_difference"]["passed"])
        self.assertFalse(scenarios["blocker"]["passed"])
        self.assertEqual(
            ["local_answer_has_source_refs", "local_answer_scenarios_have_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_online_answer_with_wrong_item_recipe_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = WrongRecipeAnswerService()
            _seed_online_agent(service, dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertTrue(_check(report, "online_agent_connector_status_seen")["passed"])
        online_answer = _check(report, "online_agent_answer_has_source_refs")
        self.assertFalse(online_answer["passed"])
        self.assertFalse(online_answer["evidence"]["source_requirement"]["passed"])
        self.assertTrue(online_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual(
            ["online_agent_answer_has_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_local_answer_with_wrong_item_quest_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            original_ask_local = phase1_acceptance_module.ask_local
            phase1_acceptance_module.ask_local = _wrong_quest_local_answer
            try:
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    item_id="minecraft:stone",
                )
            finally:
                phase1_acceptance_module.ask_local = original_ask_local

        self.assertFalse(report["valid"])
        local_answer = _check(report, "local_answer_has_source_refs")
        source_requirement = local_answer["evidence"]["source_requirement"]
        self.assertFalse(local_answer["passed"])
        self.assertFalse(source_requirement["passed"])
        self.assertEqual(["chapters/start.snbt#quest_start"], source_requirement["expected_quest_paths"])
        self.assertEqual([], source_requirement["matching_quest_refs"])
        self.assertEqual(
            [{"kind": "quest", "path": "chapters/start.snbt#quest_wrong", "label": "Wrong quest"}],
            source_requirement["quest_refs"],
        )
        self.assertTrue(local_answer["evidence"]["dump_source_requirement"]["passed"])
        scenarios = {scenario["id"]: scenario for scenario in report["local_answer_scenarios"]}
        self.assertTrue(scenarios["next_step"]["passed"])
        self.assertFalse(scenarios["unlock"]["passed"])
        self.assertTrue(scenarios["jei_difference"]["passed"])
        self.assertFalse(scenarios["blocker"]["passed"])
        self.assertEqual(
            ["local_answer_has_source_refs", "local_answer_scenarios_have_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_online_answer_with_wrong_item_quest_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = WrongQuestAnswerService()
            _seed_online_agent(service, dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertTrue(_check(report, "online_agent_connector_status_seen")["passed"])
        online_answer = _check(report, "online_agent_answer_has_source_refs")
        self.assertFalse(online_answer["passed"])
        self.assertFalse(online_answer["evidence"]["source_requirement"]["passed"])
        self.assertTrue(online_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual(
            ["online_agent_answer_has_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_local_answer_for_absent_item_with_generic_recipe_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            original_ask_local = phase1_acceptance_module.ask_local
            phase1_acceptance_module.ask_local = _wrong_recipe_local_answer
            try:
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    item_id="minecraft:dirt",
                )
            finally:
                phase1_acceptance_module.ask_local = original_ask_local

        self.assertFalse(report["valid"])
        local_answer = _check(report, "local_answer_has_source_refs")
        source_requirement = local_answer["evidence"]["source_requirement"]
        self.assertFalse(local_answer["passed"])
        self.assertFalse(source_requirement["passed"])
        self.assertTrue(source_requirement["source_expectation_checked"])
        self.assertFalse(source_requirement["item_present"])
        self.assertEqual([], source_requirement["expected_recipe_ids"])
        self.assertEqual([], source_requirement["expected_quest_paths"])
        self.assertTrue(local_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual(
            ["local_answer_has_source_refs", "local_answer_scenarios_have_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_online_answer_for_absent_item_with_generic_recipe_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = WrongRecipeAnswerService()
            _seed_online_agent(service, dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:dirt",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertTrue(_check(report, "online_agent_connector_status_seen")["passed"])
        online_answer = _check(report, "online_agent_answer_has_source_refs")
        source_requirement = online_answer["evidence"]["source_requirement"]
        self.assertFalse(online_answer["passed"])
        self.assertFalse(source_requirement["passed"])
        self.assertTrue(source_requirement["source_expectation_checked"])
        self.assertFalse(source_requirement["item_present"])
        self.assertTrue(online_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual(
            [
                "local_answer_has_source_refs",
                "local_answer_scenarios_have_source_refs",
                "online_agent_answer_has_source_refs",
            ],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_blocks_when_online_agent_dump_missing_required_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            online_dump_dir = root / "online-packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_dump(online_dump_dir, section_overrides={"advancements": ""})
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = AgentService()
            _seed_online_agent(service, online_dump_dir, require_phase1=False)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertTrue(_check(report, "phase1_runtime_sections_non_empty")["passed"])
        online = _check(report, "online_agent_connector_status_seen")
        self.assertTrue(online["required"])
        self.assertFalse(online["passed"])
        self.assertTrue(online["evidence"]["dump_seen"])
        self.assertTrue(online["evidence"]["dump_identity_matches"])
        self.assertTrue(online["evidence"]["dump_upload_complete"])
        self.assertEqual([], online["evidence"]["dump_missing_uploaded_sections"])
        self.assertFalse(online["evidence"]["dump_required_sections_non_empty"])
        self.assertEqual(["advancements"], online["evidence"]["dump_missing_required_sections"])
        self.assertTrue(online["evidence"]["pack_index_seen"])
        self.assertTrue(online["evidence"]["pack_index_runtime_truth_ready"])
        self.assertTrue(_check(report, "online_agent_answer_has_source_refs")["passed"])
        self.assertTrue(
            _check(report, "online_agent_answer_has_source_refs")["evidence"]["dump_source_requirement"]["passed"]
        )
        self.assertEqual(
            ["online_agent_connector_status_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_blocks_when_online_agent_dump_has_no_indexed_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            service = AgentService()
            _seed_online_agent_manifest_only(service, dump_dir)
            server = make_server(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        online = _check(report, "online_agent_connector_status_seen")
        self.assertTrue(online["required"])
        self.assertFalse(online["passed"])
        self.assertTrue(online["evidence"]["hello_present"])
        self.assertTrue(online["evidence"]["dump_seen"])
        self.assertFalse(online["evidence"]["dump_upload_complete"])
        self.assertIn("recipes", online["evidence"]["dump_missing_uploaded_sections"])
        self.assertEqual([], online["evidence"]["dump_uploaded_sections"])
        self.assertFalse(online["evidence"]["dump_required_sections_non_empty"])
        self.assertIn("recipes", online["evidence"]["dump_missing_required_sections"])
        self.assertTrue(online["evidence"]["pack_index_seen"])
        self.assertFalse(online["evidence"]["pack_index_runtime_truth_ready"])
        self.assertEqual("atm9sky", online["evidence"]["pack_index_profile_id"])
        self.assertEqual(0, online["evidence"]["pack_index_runtime_counts"]["recipes"])
        self.assertEqual(0, online["evidence"]["pack_index_runtime_counts"]["tags"])
        online_answer = _check(report, "online_agent_answer_has_source_refs")
        self.assertTrue(online_answer["required"])
        self.assertFalse(online_answer["passed"])
        self.assertTrue(online_answer["evidence"]["answer_seen"])
        self.assertFalse(online_answer["evidence"]["source_requirement"]["passed"])
        self.assertFalse(online_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual(
            ["online_agent_connector_status_seen", "online_agent_answer_has_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_blocks_when_supplied_agent_url_has_no_matching_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)
            server = make_server(("127.0.0.1", 0), AgentService())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                agent_url = f"http://127.0.0.1:{server.server_address[1]}"
                report = build_phase1_acceptance_report(
                    instance_path=instance,
                    runtime_dump_dir=dump_dir,
                    forge_jar=forge_jar,
                    server_log=server_log,
                    agent_url=agent_url,
                    item_id="minecraft:stone",
                )
            finally:
                server.shutdown()
                server.server_close()

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        online = _check(report, "online_agent_connector_status_seen")
        self.assertTrue(online["required"])
        self.assertFalse(online["passed"])
        self.assertTrue(online["evidence"]["checked"])
        self.assertEqual(404, online["evidence"]["http_status"])
        online_answer = _check(report, "online_agent_answer_has_source_refs")
        self.assertTrue(online_answer["required"])
        self.assertFalse(online_answer["passed"])
        self.assertTrue(online_answer["evidence"]["answer_seen"])
        self.assertFalse(online_answer["evidence"]["source_requirement"]["passed"])
        self.assertFalse(online_answer["evidence"]["dump_source_requirement"]["passed"])
        self.assertEqual(
            ["online_agent_connector_status_seen", "online_agent_answer_has_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_stays_blocked_without_live_server_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        self.assertFalse(_check(report, "live_connector_loaded_seen")["passed"])
        self.assertFalse(_check(report, "live_packwise_status_seen")["passed"])
        self.assertFalse(_check(report, "live_packwise_dump_seen")["passed"])
        self.assertTrue(_check(report, "agent_runtime_dump_imports")["passed"])
        self.assertTrue(_check(report, "local_answer_scenarios_have_source_refs")["passed"])
        self.assertIn("remediation", _check(report, "live_packwise_status_seen"))
        self.assertEqual(
            ["live_connector_loaded_seen", "live_packwise_status_seen", "live_packwise_dump_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )
        self.assertTrue(all(action.get("action") for action in report["next_actions"]))

    def test_acceptance_report_rejects_log_for_different_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            other_dump_dir = root / "packwise-dumps" / "dump_2"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, other_dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        self.assertTrue(_check(report, "live_connector_loaded_seen")["passed"])
        self.assertTrue(_check(report, "live_packwise_status_seen")["passed"])
        live_dump = _check(report, "live_packwise_dump_seen")
        self.assertFalse(live_dump["passed"])
        self.assertTrue(live_dump["evidence"]["generic_dump_seen"])
        self.assertTrue(live_dump["evidence"]["dump_connector_id_seen"])
        self.assertFalse(live_dump["evidence"]["dump_id_detail_seen"])
        self.assertFalse(live_dump["evidence"]["dump_id_seen"])
        self.assertFalse(live_dump["evidence"]["dump_path_seen"])
        self.assertEqual(
            ["live_packwise_dump_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_accepts_status_pack_line_without_configured_pack_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, pack_line="Pack: Unknown Pack (unknown-pack unknown)")

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertTrue(report["valid"])
        self.assertTrue(_check(report, "live_packwise_status_seen")["passed"])
        self.assertTrue(_check(report, "live_packwise_status_seen")["evidence"]["status_pack_seen"])
        self.assertEqual("atm9sky", report["pack_index_summary"]["profile_id"])

    def test_acceptance_report_rejects_startup_line_without_status_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, include_status_details=False)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        self.assertTrue(_check(report, "live_connector_loaded_seen")["passed"])
        status = _check(report, "live_packwise_status_seen")
        self.assertFalse(status["passed"])
        self.assertTrue(status["evidence"]["status_identity_seen"])
        self.assertFalse(status["evidence"]["status_capabilities_seen"])
        self.assertFalse(status["evidence"]["status_optional_integrations_seen"])
        self.assertFalse(status["evidence"]["status_agent_url_seen"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        self.assertEqual(
            ["live_packwise_status_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_status_without_optional_integrations_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, include_status_optional_integrations=False)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        status = _check(report, "live_packwise_status_seen")
        self.assertFalse(status["passed"])
        self.assertTrue(status["evidence"]["status_identity_seen"])
        self.assertTrue(status["evidence"]["status_pack_seen"])
        self.assertTrue(status["evidence"]["status_capabilities_seen"])
        self.assertFalse(status["evidence"]["status_optional_integrations_seen"])
        self.assertTrue(status["evidence"]["status_agent_url_seen"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        self.assertTrue(_check(report, "live_optional_diagnostics_seen")["passed"])
        self.assertEqual(
            ["live_packwise_status_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_does_not_count_live_ask_ref_without_expected_dump_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, ask_runtime_dump_ref="runtime_dump_section:recipes")

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertTrue(report["valid"])
        ask = _check(report, "live_packwise_ask_sources_seen")
        self.assertFalse(ask["required"])
        self.assertFalse(ask["passed"])
        self.assertTrue(ask["evidence"]["ask_answer_seen"])
        self.assertIn("runtime_dump_section:recipes", ask["evidence"]["ask_source_refs"])
        self.assertEqual([], ask["evidence"]["ask_dump_source_refs"])
        self.assertEqual("dump_1", ask["evidence"]["ask_expected_dump_id"])

    def test_acceptance_report_rejects_wrong_forge_status_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, status_forge_version="46.2.0")

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        self.assertTrue(_check(report, "runtime_dump_targets_forge_1201")["passed"])
        status = _check(report, "live_packwise_status_seen")
        self.assertFalse(status["passed"])
        self.assertFalse(status["evidence"]["status_identity_seen"])
        self.assertFalse(status["evidence"]["status_forge_major_seen"])
        self.assertTrue(status["evidence"]["status_pack_seen"])
        self.assertTrue(status["evidence"]["status_capabilities_seen"])
        self.assertTrue(status["evidence"]["status_optional_integrations_seen"])
        self.assertTrue(status["evidence"]["status_agent_url_seen"])
        self.assertEqual(
            ["live_packwise_status_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_mismatched_connector_mod_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, status_connector_version="0.0.9")

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        status = _check(report, "live_packwise_status_seen")
        self.assertFalse(status["passed"])
        self.assertFalse(status["evidence"]["status_connector_mod_seen"])
        self.assertEqual("packwise_connector 0.1.0", status["evidence"]["expected_connector_mod"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        self.assertEqual(
            ["live_packwise_status_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_mismatched_loaded_connector_mod_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, loaded_connector_version="0.0.9")

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        loaded = _check(report, "live_connector_loaded_seen")
        self.assertFalse(loaded["passed"])
        self.assertTrue(loaded["evidence"]["generic_loaded_seen"])
        self.assertFalse(loaded["evidence"]["loaded_connector_mod_seen"])
        self.assertTrue(_check(report, "live_packwise_status_seen")["passed"])
        self.assertEqual(
            ["live_connector_loaded_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_mismatched_status_connector_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, status_connector_id="different-connector")

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        status = _check(report, "live_packwise_status_seen")
        self.assertFalse(status["passed"])
        self.assertFalse(status["evidence"]["status_connector_id_seen"])
        self.assertEqual("atm9sky-dev-server", status["evidence"]["expected_connector_id"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        self.assertEqual(
            ["live_packwise_status_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_mismatched_dump_connector_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir, dump_connector_id="different-connector")

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        self.assertTrue(_check(report, "live_packwise_status_seen")["passed"])
        live_dump = _check(report, "live_packwise_dump_seen")
        self.assertFalse(live_dump["passed"])
        self.assertFalse(live_dump["evidence"]["dump_connector_id_seen"])
        self.assertEqual("atm9sky-dev-server", live_dump["evidence"]["expected_connector_id"])
        self.assertTrue(live_dump["evidence"]["dump_id_detail_seen"])
        self.assertEqual(
            ["live_packwise_dump_seen"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_unmatched_item_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:dirt",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        local_answer = _check(report, "local_answer_has_source_refs")
        self.assertFalse(local_answer["passed"])
        self.assertEqual("item_specific", local_answer["evidence"]["source_requirement"]["kind"])
        self.assertFalse(local_answer["evidence"]["source_requirement"]["passed"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        scenarios = {scenario["id"]: scenario for scenario in report["local_answer_scenarios"]}
        self.assertFalse(scenarios["unlock"]["passed"])
        self.assertFalse(scenarios["blocker"]["passed"])
        self.assertTrue(scenarios["next_step"]["passed"])
        self.assertTrue(scenarios["jei_difference"]["passed"])
        self.assertEqual(
            ["local_answer_has_source_refs", "local_answer_scenarios_have_source_refs"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_wrong_forge_runtime_dump_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir, loader_version="46.2.0")
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        identity_check = _check(report, "runtime_dump_targets_forge_1201")
        self.assertFalse(identity_check["passed"])
        self.assertEqual("46.2.0", identity_check["evidence"]["loader_version"])
        self.assertEqual("47", identity_check["evidence"]["expected_forge_major"])
        self.assertTrue(_check(report, "runtime_dump_valid")["passed"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        self.assertEqual(
            ["runtime_dump_targets_forge_1201"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_empty_required_phase1_runtime_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir, section_overrides={"blocks": ""})
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        dump_valid = _check(report, "runtime_dump_valid")
        self.assertFalse(dump_valid["passed"])
        self.assertEqual(["blocks"], dump_valid["evidence"]["empty_phase1_required_sections"])
        self.assertTrue(any("Empty phase1 runtime sections: blocks" in error for error in dump_valid["evidence"]["errors"]))
        self.assertTrue(_check(report, "phase1_core_sections_non_empty")["passed"])
        sections = _check(report, "phase1_runtime_sections_non_empty")
        self.assertFalse(sections["passed"])
        self.assertEqual(["blocks"], sections["evidence"]["missing_or_empty"])
        self.assertEqual(0, sections["evidence"]["counts"]["blocks"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        local_answer = _check(report, "local_answer_has_source_refs")
        self.assertFalse(local_answer["passed"])
        self.assertIn("Runtime dump validation failed", local_answer["evidence"]["error"])
        local_answer_scenarios = _check(report, "local_answer_scenarios_have_source_refs")
        self.assertFalse(local_answer_scenarios["passed"])
        self.assertEqual(
            ["next_step", "unlock", "jei_difference", "blocker"],
            local_answer_scenarios["evidence"]["failed_scenarios"],
        )
        self.assertEqual(
            [
                "runtime_dump_valid",
                "phase1_runtime_sections_non_empty",
                "pack_index_builds",
                "atm9sky_profile_selected",
                "runtime_truth_authoritative",
                "agent_runtime_dump_imports",
                "local_answer_has_source_refs",
                "local_answer_scenarios_have_source_refs",
            ],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_runtime_dump_from_different_connector_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir, connector_version="0.0.9")
            _write_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        connector_check = _check(report, "runtime_dump_connector_matches_jar")
        self.assertFalse(connector_check["passed"])
        self.assertTrue(connector_check["evidence"]["comparable"])
        self.assertEqual("0.1.0", connector_check["evidence"]["expected_connector_version"])
        self.assertEqual("0.0.9", connector_check["evidence"]["manifest_connector_version"])
        self.assertTrue(_check(report, "runtime_dump_valid")["passed"])
        self.assertTrue(_check(report, "live_packwise_dump_seen")["passed"])
        self.assertEqual(
            ["runtime_dump_connector_matches_jar"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_non_packwise_forge_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "not_packwise.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_bad_forge_jar(forge_jar)
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        jar_check = _check(report, "forge_jar_built")
        self.assertFalse(jar_check["passed"])
        self.assertIn("dev/packwise/connector/forge/PackwiseForgeCommands.class", jar_check["evidence"]["missing_entries"])
        self.assertIn("dev/packwise/connector/protocol/ConnectorHello.class", jar_check["evidence"]["missing_entries"])
        self.assertIn("dev/packwise/connector/protocol/RuntimeDumpManifest.class", jar_check["evidence"]["missing_entries"])
        self.assertIn("dev/packwise/connector/protocol/NdjsonSectionDumper.class", jar_check["evidence"]["missing_entries"])
        self.assertIn("modId=packwise_connector", jar_check["evidence"]["missing_metadata"])
        self.assertIn("minecraft dependency includes 1.20.1", jar_check["evidence"]["missing_metadata"])
        self.assertEqual(
            ["forge_jar_built"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_forge_jar_with_python_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(forge_jar, extra_entries={"scripts/packwise_agent.py": b"print('no')\n"})
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        jar_check = _check(report, "forge_jar_built")
        self.assertFalse(jar_check["passed"])
        self.assertEqual([], jar_check["evidence"]["missing_entries"])
        self.assertEqual([], jar_check["evidence"]["missing_metadata"])
        self.assertEqual(["scripts/packwise_agent.py"], jar_check["evidence"]["forbidden_entries"])
        self.assertEqual(
            ["forge_jar_built"],
            [action["check_id"] for action in report["next_actions"]],
        )

    def test_acceptance_report_rejects_forge_jar_with_pack_specific_connector_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "All the Mods 9 - To the Sky"
            dump_dir = root / "packwise-dumps" / "dump_1"
            forge_jar = root / "packwise_connector-0.1.0.jar"
            server_log = root / "latest.log"
            _write_instance(instance)
            _write_dump(dump_dir)
            _write_forge_jar(
                forge_jar,
                extra_entries={"dev/packwise/connector/forge/HardcodedPack.class": b"ATM9Sky"},
            )
            _write_server_log(server_log, dump_dir)

            report = build_phase1_acceptance_report(
                instance_path=instance,
                runtime_dump_dir=dump_dir,
                forge_jar=forge_jar,
                server_log=server_log,
                item_id="minecraft:stone",
            )

        self.assertFalse(report["valid"])
        self.assertEqual("blocked", report["status"])
        jar_check = _check(report, "forge_jar_built")
        self.assertFalse(jar_check["passed"])
        self.assertEqual([], jar_check["evidence"]["missing_entries"])
        self.assertEqual([], jar_check["evidence"]["missing_metadata"])
        self.assertEqual([], jar_check["evidence"]["forbidden_entries"])
        self.assertEqual(
            [{"entry": "dev/packwise/connector/forge/HardcodedPack.class", "match": "atm9sky"}],
            jar_check["evidence"]["pack_specific_string_matches"],
        )
        self.assertEqual(
            ["forge_jar_built"],
            [action["check_id"] for action in report["next_actions"]],
        )


def _check(report, check_id):
    return next(check for check in report["checks"] if check["id"] == check_id)


class RecipeOnlyAnswerService(AgentService):
    def handle_ask(self, payload):
        return {
            "protocol": "packwise.connector.v1",
            "message_type": "answer.packet",
            "message_id": "ans_recipe_only",
            "in_reply_to": payload.get("message_id"),
            "sent_at": "2026-06-14T08:10:00Z",
            "answer": {
                "summary": "Found a recipe ref without a dump-scoped runtime section ref.",
                "next_steps": ["Use the uploaded runtime dump before accepting online answer evidence."],
                "source_refs": [
                    {
                        "kind": "recipe",
                        "path": "minecraft:stonecutting/stone",
                        "label": "minecraft:stone",
                    }
                ],
                "confidence": "medium",
                "model": "test",
            },
        }


class WrongRecipeAnswerService(AgentService):
    def handle_ask(self, payload):
        return _wrong_recipe_answer_packet(payload.get("message_id"))


class WrongQuestAnswerService(AgentService):
    def handle_ask(self, payload):
        return _wrong_quest_answer_packet(payload.get("message_id"))


def _recipe_only_local_answer(**kwargs):
    return {
        "schema_version": "packwise.local_answer.v1",
        "valid": True,
        "connector_id": "atm9sky-dev-server",
        "dump_id": "dump_1",
        "question": kwargs.get("question"),
        "answer": {
            "summary": "Found a recipe ref without a dump-scoped runtime section ref.",
            "next_steps": ["Use the imported runtime dump before accepting local answer evidence."],
            "source_refs": [
                {
                    "kind": "recipe",
                    "path": "minecraft:stonecutting/stone",
                    "label": "minecraft:stone",
                }
            ],
            "confidence": "medium",
            "model": "test",
        },
    }


def _wrong_recipe_local_answer(**kwargs):
    payload = _wrong_recipe_answer_packet("msg_local_ask")
    return {
        "schema_version": "packwise.local_answer.v1",
        "valid": True,
        "connector_id": "atm9sky-dev-server",
        "dump_id": "dump_1",
        "question": kwargs.get("question"),
        "answer": payload["answer"],
    }


def _wrong_quest_local_answer(**kwargs):
    payload = _wrong_quest_answer_packet("msg_local_ask")
    return {
        "schema_version": "packwise.local_answer.v1",
        "valid": True,
        "connector_id": "atm9sky-dev-server",
        "dump_id": "dump_1",
        "question": kwargs.get("question"),
        "answer": payload["answer"],
    }


def _wrong_recipe_answer_packet(in_reply_to):
    return {
        "protocol": "packwise.connector.v1",
        "message_type": "answer.packet",
        "message_id": "ans_wrong_recipe",
        "in_reply_to": in_reply_to,
        "sent_at": "2026-06-14T08:10:00Z",
        "answer": {
            "summary": "Found a recipe ref for a different item.",
            "next_steps": ["Do not accept recipe refs that do not produce the requested item."],
            "source_refs": [
                {
                    "kind": "runtime_dump_section",
                    "path": "dump_1/recipes",
                    "label": "Runtime recipes",
                },
                {
                    "kind": "recipe",
                    "path": "minecraft:crafting/dirt",
                    "label": "minecraft:dirt",
                },
            ],
            "confidence": "medium",
            "model": "test",
        },
    }


def _wrong_quest_answer_packet(in_reply_to):
    return {
        "protocol": "packwise.connector.v1",
        "message_type": "answer.packet",
        "message_id": "ans_wrong_quest",
        "in_reply_to": in_reply_to,
        "sent_at": "2026-06-14T08:10:00Z",
        "answer": {
            "summary": "Found a quest ref for a different target.",
            "next_steps": ["Do not accept quest refs that do not mention the requested item."],
            "source_refs": [
                {
                    "kind": "runtime_dump_section",
                    "path": "dump_1/recipes",
                    "label": "Runtime recipes",
                },
                {
                    "kind": "quest",
                    "path": "chapters/start.snbt#quest_wrong",
                    "label": "Wrong quest",
                },
            ],
            "confidence": "medium",
            "model": "test",
        },
    }


def _seed_online_agent(service: AgentService, dump_dir: Path, require_phase1: bool = True) -> None:
    _seed_online_agent_hello(service)
    import_runtime_dump_directory(service, dump_dir, require_phase1=require_phase1)


def _seed_online_agent_without_file_validation(service: AgentService, dump_dir: Path) -> None:
    _seed_online_agent_hello(service)
    manifest = json.loads((dump_dir / "manifest.json").read_text(encoding="utf-8"))
    connector_id = manifest["connector_id"]
    dump_id = manifest["dump_id"]
    service.handle_runtime_dump_manifest(connector_id, manifest)
    for section in manifest["sections"]:
        name = section["name"]
        body = (dump_dir / f"{name}.ndjson").read_text(encoding="utf-8")
        service.handle_runtime_dump_section(connector_id, dump_id, name, section["content_type"], body)


def _seed_online_agent_manifest_only(service: AgentService, dump_dir: Path) -> None:
    _seed_online_agent_hello(service)
    manifest = json.loads((dump_dir / "manifest.json").read_text(encoding="utf-8"))
    service.handle_runtime_dump_manifest("atm9sky-dev-server", manifest)


def _seed_online_agent_hello(service: AgentService) -> None:
    service.handle_connector_hello(
        {
            "protocol": "packwise.connector.v1",
            "message_type": "connector.hello",
            "message_id": "msg_0001",
            "sent_at": "2026-06-14T08:00:00Z",
            "connector": {
                "id": "atm9sky-dev-server",
                "side": "server",
                "loader": "forge",
                "loader_version": "47.4.20",
                "minecraft_version": "1.20.1",
                "pack_id": "atm9sky",
                "pack_name": "All the Mods 9 - To the Sky",
                "pack_version": "1.1.0",
                "connector_mod_id": "packwise_connector",
                "connector_version": "0.1.0",
                "capabilities": ["runtime_dump", "commands"],
            },
        }
    )


def _write_instance(root: Path) -> None:
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
              title: "Stone Start"
              tasks: [{ id: "task_stone" type: "item" item: { id: "minecraft:stone" count: 1 } }]
            }
          ]
        }
        """,
        encoding="utf-8",
    )


def _write_dump(
    path: Path,
    loader_version: str = "47.4.20",
    connector_mod_id: str = "packwise_connector",
    connector_version: str = "0.1.0",
    include_progression: bool = False,
    section_overrides: dict[str, str] | None = None,
) -> None:
    sections = {
        "mods": '{"mod_id":"minecraft","display_name":"Minecraft","version":"1.20.1","source":"runtime:mod_list"}\n',
        "items": (
            '{"id":"minecraft:cobblestone","registry":"item","namespace":"minecraft","path":"cobblestone","source":"runtime:built_in_registry"}\n'
            '{"id":"minecraft:stone","registry":"item","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n'
        ),
        "blocks": '{"id":"minecraft:stone","registry":"block","namespace":"minecraft","path":"stone","source":"runtime:built_in_registry"}\n',
        "fluids": '{"id":"minecraft:water","registry":"fluid","namespace":"minecraft","path":"water","source":"runtime:built_in_registry"}\n',
        "tags": '{"registry":"item","tag":"forge:stone","entry_count":1,"entries":["minecraft:stone"],"source":"runtime:registry_tags"}\n',
        "recipes": '{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"source":"runtime:recipe_manager"}\n',
        "advancements": '{"id":"minecraft:story/mine_stone","source":"runtime:server_advancements"}\n',
    }
    if include_progression:
        sections.update(
            {
                "ftb_quests": "\n".join(
                    [
                        '{"quest_id":"quest_root","chapter_id":"chapter_start","title":"Root","dependencies":[],"task_item_ids":[],"reward_item_ids":[],"source":"runtime:ftb_quests"}',
                        '{"quest_id":"quest_stone","chapter_id":"chapter_start","title":"Runtime Stone","dependencies":["quest_root"],"task_item_ids":["minecraft:stone"],"reward_item_ids":[],"source":"runtime:ftb_quests"}',
                        "",
                    ]
                ),
                "player_progress": '{"subject_type":"player","subject_id":"player-1","completed_quests":["quest_root"],"completed_advancements":[],"stages":["stone_age"],"source":"runtime:ftb_quests","player_name":"DevPlayer","team_id":"team-main"}\n',
                "team_progress": '{"subject_type":"team","subject_id":"team-main","completed_quests":["quest_root"],"completed_advancements":[],"stages":["stone_age"],"source":"runtime:ftb_quests","team_name":"DevTeam","members":["player-1"]}\n',
                "stages": '{"subject_type":"player","subject_id":"player-1","stage":"stone_age","active":true,"source":"runtime:gamestages","player_name":"DevPlayer"}\n',
            }
        )
    if section_overrides:
        sections.update(section_overrides)
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
        "dump_id": "dump_1",
        "minecraft_version": "1.20.1",
        "loader": "forge",
        "loader_version": loader_version,
        "connector_mod_id": connector_mod_id,
        "connector_version": connector_version,
        "sections": manifest_sections,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_forge_jar(path: Path, extra_entries: dict[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "META-INF/mods.toml",
            """
            modLoader="javafml"
            loaderVersion="[47,)"
            license="MIT"

            [[mods]]
            modId="packwise_connector"
            version="0.1.0"
            displayName="Packwise Connector"
            authors="Packwise"
            description='''Read-only Packwise runtime connector for Forge Minecraft modpack servers.'''

            [[dependencies.packwise_connector]]
            modId="forge"
            mandatory=true
            versionRange="[47.0.0,48.0.0)"
            ordering="NONE"
            side="BOTH"

            [[dependencies.packwise_connector]]
            modId="minecraft"
            mandatory=true
            versionRange="[1.20.1,1.21)"
            ordering="NONE"
            side="BOTH"
            """,
        )
        archive.writestr("dev/packwise/connector/forge/PackwiseForgeMod.class", b"")
        archive.writestr("dev/packwise/connector/forge/PackwiseForgeCommands.class", b"")
        archive.writestr("dev/packwise/connector/forge/ForgePackMetadata.class", b"")
        archive.writestr("dev/packwise/connector/forge/ForgeRuntimeDumpCollector.class", b"")
        archive.writestr("dev/packwise/connector/forge/ForgeOptionalRuntimeDumpCollector.class", b"")
        for entry in _common_protocol_class_entries():
            archive.writestr(entry, b"")
        for name, body in (extra_entries or {}).items():
            archive.writestr(name, body)


def _write_bad_forge_jar(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "META-INF/mods.toml",
            """
            modLoader="javafml"
            loaderVersion="[47,)"
            license="MIT"

            [[mods]]
            modId="other_connector"
            version="0.1.0"
            displayName="Other Connector"

            [[dependencies.other_connector]]
            modId="forge"
            mandatory=true
            versionRange="[47.0.0,48.0.0)"
            ordering="NONE"
            side="BOTH"

            [[dependencies.other_connector]]
            modId="minecraft"
            mandatory=true
            versionRange="[1.19.2,1.20)"
            ordering="NONE"
            side="BOTH"
            """,
        )
        archive.writestr("dev/packwise/connector/forge/PackwiseForgeMod.class", b"")
        archive.writestr("dev/packwise/connector/protocol/RuntimeDumpFileWriter.class", b"")
        archive.writestr("dev/packwise/connector/protocol/RuntimeDumpUploader.class", b"")


def _common_protocol_class_entries() -> list[str]:
    names = [
        "AgentAnswer",
        "AgentHttpClient",
        "CommandResponse",
        "ConnectorHello",
        "ConnectorInfo",
        "ConnectorSide",
        "JsonText",
        "ModSnapshot",
        "ModsSectionDumper",
        "NdjsonSectionDumper",
        "QueryAsk",
        "RuntimeDumpContent",
        "RuntimeDumpFileWriter",
        "RuntimeDumpManifest",
        "RuntimeDumpSection",
        "RuntimeDumpUploader",
        "RuntimeDumpUploadResult",
        "RuntimeSectionNames",
    ]
    return [f"dev/packwise/connector/protocol/{name}.class" for name in names]


def _write_server_log(
    path: Path,
    dump_dir: Path,
    include_status_details: bool = True,
    include_status_optional_integrations: bool = True,
    pack_line: str = "Pack: All the Mods 9 - To the Sky (atm9sky 1.1.0)",
    status_forge_version: str = "47.4.20",
    status_connector_version: str = "0.1.0",
    loaded_connector_version: str = "0.1.0",
    status_connector_id: str = "atm9sky-dev-server",
    dump_connector_id: str = "atm9sky-dev-server",
    ask_runtime_dump_ref: str | None = None,
) -> None:
    dump_id = dump_dir.name
    runtime_ref = ask_runtime_dump_ref or f"runtime_dump_section:{dump_id}/recipes"
    status_lines = [
        f"[Server thread/INFO] Packwise connector: forge {status_forge_version} / Minecraft 1.20.1",
    ]
    if include_status_details:
        status_lines.extend(
            [
                f"[Server thread/INFO] Connector Mod: packwise_connector {status_connector_version}",
                f"[Server thread/INFO] Connector ID: {status_connector_id}",
                f"[Server thread/INFO] {pack_line}",
                "[Server thread/INFO] Capabilities: runtime_dump, commands, server_progress, quest_progress, team_progress, stage_state, kubejs_static_sources",
                "[Server thread/INFO] Agent URL: not configured",
            ]
        )
        if include_status_optional_integrations:
            status_lines.insert(
                -1,
                "[Server thread/INFO] Optional integrations: ftbquests=loaded, ftbteams=loaded, gamestages=loaded, kubejs=loaded",
            )
    path.write_text(
        "\n".join(
            status_lines
            + [
                f"[modloading-worker-0/INFO] Packwise connector loaded: mod_id=packwise_connector, version={loaded_connector_version}",
                "[Server thread/INFO] Packwise: runtime dump written locally; upload skipped because PACKWISE_BACKEND_BASE_URL/PACKWISE_AGENT_BASE_URL/PACKWISE_AGENT_URL is not configured",
                f"[Server thread/INFO] mods=1, items=1, tags=1, recipes=1, connector_id={dump_connector_id}, dump_id={dump_id}, "
                "optional_integrations=ftbquests=loaded|ftbteams=loaded|gamestages=loaded|kubejs=loaded, "
                f"optional_sections=ftb_quests|player_progress, path={dump_dir}",
                "[Server thread/INFO] Packwise: Stone can be produced from the runtime recipe dump.",
                "[Server thread/INFO] - Use the recipe manager result for minecraft:stone.",
                f"[Server thread/INFO] Sources: recipe:minecraft:stonecutting/stone, {runtime_ref}",
                "[Server thread/INFO] Confidence: medium",
            ]
        ),
        encoding="utf-8",
    )


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
