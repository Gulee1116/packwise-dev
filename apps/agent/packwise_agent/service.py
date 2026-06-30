from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol
from uuid import uuid4

from .llm import ChatMessage
from .pack_index import RUNTIME_SECTIONS, build_packwise_index
from .protocol import (
    ConnectorHello,
    PROTOCOL_VERSION,
    RUNTIME_DUMP_NDJSON_CONTENT_TYPE,
    RuntimeDumpManifest,
    validate_ask,
)
from .runtime_index import (
    RuntimeMobEffect,
    RuntimeMod,
    RuntimePackIndex,
    RuntimePotion,
    RuntimeQuest,
    RuntimeRegistryEntry,
    RuntimeRecipe,
    runtime_consistency_errors,
)


class ChatClient(Protocol):
    def complete(self, messages: list[ChatMessage]) -> str:
        ...


@dataclass(frozen=True)
class RuntimeDumpStoredSection:
    connector_id: str
    dump_id: str
    section_name: str
    content_type: str
    body: str
    line_count: int


@dataclass(frozen=True)
class ProgressScope:
    team_id: Optional[str]
    player_id: Optional[str]
    player_name: Optional[str]

    def is_scoped(self) -> bool:
        return bool(self.team_id or self.player_id or self.player_name)


@dataclass(frozen=True)
class CreativeFlightRoute:
    recipe: RuntimeRecipe
    potion: RuntimePotion
    effect: RuntimeMobEffect
    creative_flight_attribute: str
    potion_count: int
    blaze_powder_count: int
    charm_item_id: str
    other_route_items: list[str]


class AgentService:
    def __init__(self, model_name: str = "deepseek-v4-pro", chat_client: Optional[ChatClient] = None) -> None:
        self.model_name = model_name
        self.chat_client = chat_client
        self.connectors: Dict[str, ConnectorHello] = {}
        self.runtime_dumps: Dict[str, RuntimeDumpManifest] = {}
        self.runtime_dumps_by_connector: Dict[tuple[str, str], RuntimeDumpManifest] = {}
        self.runtime_dump_sections: Dict[tuple[str, str], RuntimeDumpStoredSection] = {}
        self.runtime_dump_sections_by_connector: Dict[tuple[str, str, str], RuntimeDumpStoredSection] = {}
        self.runtime_mods: Dict[str, list[RuntimeMod]] = {}
        self.runtime_mods_by_connector: Dict[tuple[str, str], list[RuntimeMod]] = {}
        self.runtime_indexes: Dict[str, RuntimePackIndex] = {}
        self.runtime_indexes_by_connector: Dict[tuple[str, str], RuntimePackIndex] = {}
        self.static_summaries: Dict[str, Mapping[str, Any]] = {}
        self.quest_summaries: Dict[str, Mapping[str, Any]] = {}

    def handle_connector_hello(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        hello = ConnectorHello.from_dict(payload)
        self.connectors[hello.connector.id] = hello
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "connector.ack",
            "message_id": _new_message_id("ack"),
            "in_reply_to": hello.message_id,
            "sent_at": _now_iso(),
            "accepted": True,
            "agent": {
                "name": "packwise-agent",
                "capabilities": ["ask", "next_steps", "goal_planning"],
            },
        }

    def handle_ask(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        request = validate_ask(payload)
        answer = self._draft_answer(request["question"], request["context"])
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "answer.packet",
            "message_id": _new_message_id("ans"),
            "in_reply_to": request["message_id"],
            "sent_at": _now_iso(),
            "answer": answer,
        }

    def handle_runtime_dump_manifest(self, connector_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        manifest = RuntimeDumpManifest.from_dict(payload)
        manifest.require_connector_id(connector_id)
        duplicate_sections = _duplicate_section_names([section.name for section in manifest.sections])
        if duplicate_sections:
            raise ValueError("Duplicate runtime dump sections in manifest: " + ", ".join(duplicate_sections))
        invalid_content_type_sections = _invalid_runtime_content_types(manifest)
        if invalid_content_type_sections:
            raise ValueError(
                "Runtime dump sections must use "
                + RUNTIME_DUMP_NDJSON_CONTENT_TYPE
                + ": "
                + ", ".join(invalid_content_type_sections)
            )
        self._clear_runtime_dump_state(connector_id, manifest.dump_id)
        self.runtime_dumps_by_connector[(connector_id, manifest.dump_id)] = manifest
        self.runtime_dumps[manifest.dump_id] = manifest
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "runtime_dump.ack",
            "message_id": _new_message_id("dump_ack"),
            "in_reply_to": manifest.message_id,
            "sent_at": _now_iso(),
            "accepted": True,
            "dump_id": manifest.dump_id,
            "section_count": len(manifest.sections),
        }

    def handle_runtime_dump_section(
        self,
        connector_id: str,
        dump_id: str,
        section_name: str,
        content_type: str,
        body: str,
    ) -> Dict[str, Any]:
        manifest = self._runtime_manifest(connector_id, dump_id)
        if manifest is None:
            raise ValueError(f"Unknown runtime dump for connector {connector_id}: {dump_id}")
        manifest.require_connector_id(connector_id)
        expected_section = next((section for section in manifest.sections if section.name == section_name), None)
        if expected_section is None:
            raise ValueError(f"Runtime dump {dump_id} did not declare section {section_name}")
        if expected_section.content_type != content_type:
            raise ValueError(f"Expected content type {expected_section.content_type}, got {content_type}")
        line_count = len([line for line in body.splitlines() if line.strip()])
        if expected_section.count != line_count:
            raise ValueError(f"Section {section_name} count mismatch: expected {expected_section.count}, got {line_count}")
        actual_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if expected_section.sha256 != actual_sha256:
            raise ValueError(f"Section {section_name} sha256 mismatch: expected {expected_section.sha256}, got {actual_sha256}")
        key = (connector_id, dump_id)
        current_index = self.runtime_indexes_by_connector.get(key, RuntimePackIndex.empty())
        updated_index = current_index.with_section(section_name, body)
        stored = RuntimeDumpStoredSection(
            connector_id=connector_id,
            dump_id=dump_id,
            section_name=section_name,
            content_type=content_type,
            body=body,
            line_count=line_count,
        )
        self.runtime_dump_sections_by_connector[(connector_id, dump_id, section_name)] = stored
        self.runtime_dump_sections[(dump_id, section_name)] = stored
        self.runtime_indexes_by_connector[key] = updated_index
        self.runtime_indexes[dump_id] = updated_index
        if section_name == "mods":
            mods = updated_index.mods
            self.runtime_mods_by_connector[key] = mods
            self.runtime_mods[dump_id] = mods
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "runtime_dump.section_ack",
            "message_id": _new_message_id("section_ack"),
            "sent_at": _now_iso(),
            "accepted": True,
            "dump_id": dump_id,
            "section_name": section_name,
            "line_count": line_count,
        }

    def list_runtime_mods(self, dump_id: str, connector_id: str | None = None) -> list[Dict[str, str]]:
        if connector_id:
            mods = self.runtime_mods_by_connector.get((connector_id, dump_id), [])
        else:
            mods = self.runtime_mods.get(dump_id, [])
        return [mod.to_dict() for mod in mods]

    def runtime_index_summary(self, dump_id: str, connector_id: str | None = None) -> Dict[str, int]:
        return self._runtime_index(connector_id, dump_id).summary()

    def list_runtime_recipes(self, dump_id: str, connector_id: str | None = None) -> list[Dict[str, Any]]:
        return [recipe.to_dict() for recipe in self._runtime_index(connector_id, dump_id).recipes]

    def runtime_consistency_errors(self, dump_id: str, connector_id: str | None = None) -> list[str]:
        return runtime_consistency_errors(self._runtime_index(connector_id, dump_id))

    def has_runtime_dump(self, connector_id: str, dump_id: str) -> bool:
        return self._runtime_manifest(connector_id, dump_id) is not None

    def runtime_dump_connector_ids(self, dump_id: str) -> list[str]:
        connector_ids = [
            connector_id
            for connector_id, stored_dump_id in self.runtime_dumps_by_connector
            if stored_dump_id == dump_id
        ]
        if connector_ids:
            return connector_ids
        legacy_manifest = self.runtime_dumps.get(dump_id)
        return [legacy_manifest.connector_id] if legacy_manifest is not None else []

    def connector_status(self, connector_id: str) -> Dict[str, Any] | None:
        hello = self.connectors.get(connector_id)
        runtime_dumps: list[Dict[str, Any]] = []
        for (stored_connector_id, dump_id), manifest in self.runtime_dumps_by_connector.items():
            if stored_connector_id != connector_id:
                continue
            upload_state = self._runtime_dump_upload_state(connector_id, dump_id, manifest)
            runtime_dumps.append(
                {
                    "dump_id": dump_id,
                    "minecraft_version": manifest.minecraft_version,
                    "loader": manifest.loader,
                    "loader_version": manifest.loader_version,
                    "connector_mod_id": manifest.connector_mod_id,
                    "connector_version": manifest.connector_version,
                    "section_count": len(manifest.sections),
                    **upload_state,
                    "indexed_summary": self.runtime_index_summary(dump_id, connector_id=connector_id),
                    "runtime_consistency_errors": self.runtime_consistency_errors(dump_id, connector_id=connector_id),
                }
            )
        static_inspect_present = connector_id in self.static_summaries
        quest_book_present = connector_id in self.quest_summaries
        if hello is None and not runtime_dumps and not static_inspect_present and not quest_book_present:
            return None
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "connector.status",
            "connector_id": connector_id,
            "hello_present": hello is not None,
            "hello": None
            if hello is None
            else {
                "message_id": hello.message_id,
                "sent_at": hello.sent_at,
            },
            "connector": None if hello is None else hello.connector.to_dict(),
            "static_inspect_present": static_inspect_present,
            "quest_book_present": quest_book_present,
            "runtime_dumps": runtime_dumps,
        }

    def handle_static_inspect(self, connector_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if payload.get("schema_version") != "packwise.static_inspect.v1":
            raise ValueError("Expected static inspect schema packwise.static_inspect.v1")
        self.static_summaries[connector_id] = dict(payload)
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "static_inspect.ack",
            "message_id": _new_message_id("static_ack"),
            "sent_at": _now_iso(),
            "accepted": True,
            "connector_id": connector_id,
        }

    def handle_quest_book(self, connector_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if payload.get("schema_version") != "packwise.ftbquests.v1":
            raise ValueError("Expected quest book schema packwise.ftbquests.v1")
        self.quest_summaries[connector_id] = dict(payload)
        return {
            "protocol": PROTOCOL_VERSION,
            "message_type": "quest_book.ack",
            "message_id": _new_message_id("quest_ack"),
            "sent_at": _now_iso(),
            "accepted": True,
            "connector_id": connector_id,
        }

    def build_packwise_index(self, connector_id: str, dump_id: str) -> Dict[str, Any]:
        static_summary = self.static_summaries.get(connector_id)
        if static_summary is None:
            static_summary = self._static_summary_from_connector(connector_id)
        runtime_index = self._runtime_index(connector_id, dump_id)
        quest_summary = self.quest_summaries.get(connector_id)
        return build_packwise_index(static_summary, runtime_index, quest_summary).to_dict()

    def _draft_answer(self, question: str, context: Mapping[str, Any]) -> Dict[str, Any]:
        connector_id: Optional[str] = context.get("connector_id") if isinstance(context.get("connector_id"), str) else None
        dump_id: Optional[str] = context.get("dump_id") if isinstance(context.get("dump_id"), str) else None
        if dump_id is None and connector_id:
            dump_id = self._latest_dump_id_for_connector(connector_id)
        source_refs: list[Dict[str, str]] = []
        if connector_id and connector_id in self.connectors:
            source_refs.append(
                {
                    "kind": "connector",
                    "path": connector_id,
                    "label": self.connectors[connector_id].connector.pack_name,
                }
            )
        index = self._runtime_index(connector_id, dump_id) if dump_id else RuntimePackIndex.empty()
        consistency_errors = self.runtime_consistency_errors(dump_id, connector_id=connector_id) if dump_id else []
        if consistency_errors:
            return _inconsistent_runtime_answer(source_refs, dump_id, consistency_errors, self.model_name)
        progress_scope = _progress_scope(context)
        if _question_requests_creative_flight(question):
            creative_answer = _creative_flight_answer(
                question=question,
                index=index,
                dump_id=dump_id,
                base_source_refs=source_refs,
                model_name=self.model_name,
            )
            if creative_answer is not None:
                return creative_answer
        matched_mod = self._match_mod(question, index)
        family_requested = _question_requests_item_family(question)
        matched_items = self._match_items(question, context, index, matched_mod)
        related_items = self._related_items(question, index, matched_items, matched_mod)
        item_scope = _unique_strings([*matched_items, *related_items])
        matched_item = matched_items[0] if len(matched_items) == 1 else None
        matched_recipes = self._recipes_for_items(item_scope, index) if item_scope else []
        quest_matches = (
            self._quest_matches_for_items(connector_id, item_scope, index, dump_id)
            if connector_id and item_scope
            else []
        )
        matched_usage_recipes = _usage_recipes_for_items(item_scope, index) if item_scope and family_requested else []
        item_labels = _item_label_map(
            index,
            _evidence_item_ids(item_scope, matched_recipes, matched_usage_recipes, quest_matches),
        )
        runtime_dump_present = self._runtime_dump_present(connector_id, dump_id)
        runtime_counts = index.summary()
        answer_readiness = _answer_readiness(runtime_counts, bool(dump_id), runtime_dump_present)
        source_refs.extend(
            _runtime_section_source_refs(dump_id, index, include_mods=matched_mod is not None, include_items=bool(item_scope))
        )
        if dump_id and matched_mod is not None:
            source_refs.append(
                {
                    "kind": "mod",
                    "path": f"{dump_id}/mods#{matched_mod.mod_id}",
                    "label": _mod_label(matched_mod),
                }
            )
        for quest in quest_matches[:8]:
            source_refs.append(
                {
                    "kind": "quest",
                    "path": quest["path"],
                    "label": quest["label"],
                }
            )
        for recipe in matched_recipes[:8]:
            source_refs.append(
                {
                    "kind": "recipe",
                    "path": recipe.id,
                    "label": recipe.result_item or recipe.id,
                }
            )
        for recipe in matched_usage_recipes[:4]:
            source_refs.append(
                {
                    "kind": "recipe_usage",
                    "path": recipe.id,
                    "label": recipe.result_item or recipe.id,
                }
            )

        source_refs = _dedupe_source_refs(source_refs)
        if not source_refs:
            source_refs.append(
                {
                    "kind": "protocol",
                    "path": "docs/protocol/CONNECTOR_AGENT_PROTOCOL.md",
                    "label": "Packwise protocol draft",
                }
            )

        route_ranking_context = _route_ranking_context(question, matched_items, related_items)
        evidence = _ask_evidence(
            connector_id=connector_id,
            dump_id=dump_id,
            runtime_dump_present=runtime_dump_present,
            runtime_counts=runtime_counts,
            answer_readiness=answer_readiness,
            route_ranking_context=route_ranking_context,
            route_ranking_question=_route_ranking_question(question, route_ranking_context),
            matched_mod=matched_mod,
            matched_items=matched_items,
            related_items=related_items,
            matched_recipes=matched_recipes,
            matched_usage_recipes=matched_usage_recipes,
            quest_matches=quest_matches,
            source_refs=source_refs,
            item_labels=item_labels,
        )
        fallback_summary = _fallback_summary(
            question,
            index,
            matched_item,
            matched_recipes,
            quest_matches,
            progress_scope,
            matched_items=matched_items,
            related_items=related_items,
            matched_mod=matched_mod,
            usage_recipes=matched_usage_recipes,
        )
        if self.chat_client:
            llm_summary = self._llm_summary(question, context, evidence)
            summary = _enforce_source_policy(llm_summary, fallback_summary, evidence)
        else:
            summary = fallback_summary
        summary = _localize_summary_item_ids(summary, evidence)
        next_steps = self._next_steps(
            question,
            index,
            matched_item,
            matched_recipes,
            quest_matches,
            progress_scope,
            matched_items=matched_items,
            related_items=related_items,
            matched_mod=matched_mod,
            usage_recipes=matched_usage_recipes,
        )
        next_steps = [_localize_summary_item_ids(step, evidence) for step in next_steps]
        confidence = _confidence(matched_recipes, quest_matches, index, bool(dump_id), progress_scope)

        return {
            "summary": summary,
            "next_steps": next_steps,
            "source_refs": source_refs,
            "confidence": confidence,
            "model": self.model_name,
        }

    def _latest_dump_id_for_connector(self, connector_id: str) -> Optional[str]:
        matching = [
            dump_id
            for key_connector_id, dump_id in self.runtime_dumps_by_connector
            if key_connector_id == connector_id
        ]
        return matching[-1] if matching else None

    def _runtime_manifest(self, connector_id: str, dump_id: str) -> RuntimeDumpManifest | None:
        manifest = self.runtime_dumps_by_connector.get((connector_id, dump_id))
        if manifest is not None:
            return manifest
        legacy_manifest = self.runtime_dumps.get(dump_id)
        if legacy_manifest is not None and legacy_manifest.connector_id == connector_id:
            return legacy_manifest
        return None

    def _runtime_index(self, connector_id: str | None, dump_id: str) -> RuntimePackIndex:
        if connector_id:
            index = self.runtime_indexes_by_connector.get((connector_id, dump_id))
            if index is not None:
                return index
            legacy_manifest = self.runtime_dumps.get(dump_id)
            if legacy_manifest is None or legacy_manifest.connector_id != connector_id:
                return RuntimePackIndex.empty()
        return self.runtime_indexes.get(dump_id, RuntimePackIndex.empty())

    def _runtime_dump_upload_state(
        self,
        connector_id: str,
        dump_id: str,
        manifest: RuntimeDumpManifest,
    ) -> Dict[str, Any]:
        declared_sections = [section.name for section in manifest.sections]
        uploaded_sections = {
            section_name
            for stored_connector_id, stored_dump_id, section_name in self.runtime_dump_sections_by_connector
            if stored_connector_id == connector_id and stored_dump_id == dump_id
        }
        uploaded_declared_sections = [
            section_name for section_name in declared_sections if section_name in uploaded_sections
        ]
        missing_sections = [
            section_name for section_name in declared_sections if section_name not in uploaded_sections
        ]
        extra_sections = sorted(uploaded_sections - set(declared_sections))
        return {
            "declared_sections": declared_sections,
            "uploaded_sections": uploaded_declared_sections,
            "uploaded_section_count": len(uploaded_declared_sections),
            "missing_sections": missing_sections,
            "extra_sections": extra_sections,
            "upload_complete": not missing_sections and not extra_sections,
        }

    def _clear_runtime_dump_state(self, connector_id: str, dump_id: str) -> None:
        key = (connector_id, dump_id)
        self.runtime_dump_sections_by_connector = {
            section_key: section
            for section_key, section in self.runtime_dump_sections_by_connector.items()
            if section_key[0] != connector_id or section_key[1] != dump_id
        }
        self.runtime_dump_sections = {
            section_key: section
            for section_key, section in self.runtime_dump_sections.items()
            if section.connector_id != connector_id or section.dump_id != dump_id
        }
        self.runtime_mods_by_connector.pop(key, None)
        self.runtime_indexes_by_connector[key] = RuntimePackIndex.empty()
        if self.runtime_dumps.get(dump_id, None) is self.runtime_dumps_by_connector.get(key):
            self.runtime_mods.pop(dump_id, None)
            self.runtime_indexes[dump_id] = RuntimePackIndex.empty()

    def _static_summary_from_connector(self, connector_id: str) -> Mapping[str, Any]:
        hello = self.connectors.get(connector_id)
        if hello is None:
            raise ValueError(f"No static inspect or connector hello available for {connector_id}")
        connector = hello.connector
        return {
            "schema_version": "packwise.static_inspect.v1",
            "path": "",
            "pack": {
                "name": connector.pack_name,
                "version": connector.pack_version,
                "translation_language": None,
            },
            "loader": {
                "minecraft_version": connector.minecraft_version,
                "name": connector.loader,
                "version": connector.loader_version,
            },
            "adapter": {
                "pack_id": connector.pack_id,
                "loader": connector.loader,
                "minecraft_version": connector.minecraft_version,
                "quest_mod": None,
                "known_progression_sources": ["advancements"],
                "source_inventory": {},
                "optional_integrations": {},
            },
            "counts": {},
        }

    def _runtime_dump_present(self, connector_id: str | None, dump_id: str | None) -> bool:
        if not dump_id:
            return False
        if connector_id:
            return self._runtime_manifest(connector_id, dump_id) is not None
        return dump_id in self.runtime_dumps

    def _match_mod(self, question: str, index: RuntimePackIndex) -> RuntimeMod | None:
        explicit_namespaces = _registry_namespaces_in_text(question)
        if explicit_namespaces:
            for namespace in explicit_namespaces:
                for mod in index.mods:
                    if mod.mod_id == namespace:
                        return mod
        compact_question = _compact_search_text(question)
        if not compact_question:
            return None
        candidates = sorted(index.mods, key=lambda mod: max(len(mod.mod_id), len(mod.display_name)), reverse=True)
        if "热力" in question:
            for mod in candidates:
                if mod.mod_id == "thermal":
                    return mod
        for mod in candidates:
            compact_mod_id = _compact_search_text(mod.mod_id)
            compact_display = _compact_search_text(mod.display_name)
            if compact_mod_id and compact_mod_id in compact_question:
                return mod
            if compact_display and compact_display in compact_question:
                return mod
        return None

    def _match_item(self, question: str, context: Mapping[str, Any], index: RuntimePackIndex) -> Optional[str]:
        matches = self._match_items(question, context, index, self._match_mod(question, index))
        return matches[0] if matches else None

    def _match_items(
        self,
        question: str,
        context: Mapping[str, Any],
        index: RuntimePackIndex,
        matched_mod: RuntimeMod | None = None,
    ) -> list[str]:
        context_item = context.get("item_id")
        if isinstance(context_item, str) and context_item:
            return [context_item]

        family_requested = _question_requests_item_family(question)
        exact_matches = _exact_item_matches(question, index)
        if exact_matches and not family_requested:
            return exact_matches

        family_items = _question_family_items(question, index, matched_mod) if family_requested else []
        if family_items:
            return family_items
        if exact_matches:
            return exact_matches

        haystack = question.lower()
        normalized_question = _normalize_search_text(question)
        compact_question = _compact_search_text(question)
        question_tokens = set(normalized_question.split())
        matches: list[tuple[int, str]] = []
        for item_id in _candidate_item_ids(index):
            lowered = item_id.lower()
            if lowered in haystack:
                matches.append((1000 + len(lowered), item_id))
                continue
            path = lowered.split(":", 1)[-1]
            path_tokens = _significant_tokens(path)
            if not path_tokens:
                continue
            path_phrase = " ".join(path_tokens)
            if len(path_phrase) >= 4 and path_phrase in normalized_question:
                matches.append((500 + len(path_phrase), item_id))
                continue
            matched_alias = False
            for alias in _item_search_aliases(index, item_id):
                normalized_alias = _normalize_search_text(alias)
                compact_alias = _compact_search_text(alias)
                if _normalized_phrase_in_text(normalized_alias, normalized_question):
                    matches.append((700 + len(normalized_alias), item_id))
                    matched_alias = True
                    break
                if _contains_cjk(alias) and compact_alias and compact_alias in compact_question:
                    matches.append((700 + len(compact_alias), item_id))
                    matched_alias = True
                    break
            if matched_alias:
                continue
            if len(path_tokens) > 1 and all(token in question_tokens for token in path_tokens):
                matches.append((300 + len(path_tokens), item_id))
                continue
            if len(path_tokens) == 1 and path_tokens[0] in question_tokens and len(path_tokens[0]) >= 4:
                matches.append((100 + len(path_tokens[0]), item_id))

        if matches:
            return _unique_strings([item_id for _, item_id in sorted(matches, key=lambda item: (-item[0], item[1]))[:5]])

        if matched_mod is not None and _looks_like_mod_level_question(question):
            return _items_for_mod_namespace(index, matched_mod.mod_id, limit=12)
        return []

    def _related_items(
        self,
        question: str,
        index: RuntimePackIndex,
        matched_items: list[str],
        matched_mod: RuntimeMod | None = None,
    ) -> list[str]:
        related: list[str] = []
        mod_level_question = matched_mod is not None and _looks_like_mod_level_question(question)
        family_requested = _question_requests_item_family(question)
        if mod_level_question:
            related.extend(_items_for_mod_namespace(index, matched_mod.mod_id, limit=12))
        if not family_requested and not mod_level_question:
            return []

        candidate_ids = _candidate_item_ids(index)
        for item_id in matched_items:
            namespace, _, path = item_id.partition(":")
            if not namespace or not path:
                continue
            related.extend(
                other_id
                for other_id in candidate_ids
                if _is_sibling_item(item_id, other_id)
            )
            if namespace == "thermal" and path.startswith("upgrade_augment"):
                related.extend(
                    other_id
                    for other_id in candidate_ids
                    if other_id == "thermal_extra:upgrade_augment"
                    or other_id.startswith("thermal_extra:")
                    and "upgrade_augment" in other_id.split(":", 1)[1]
                )
        return [item_id for item_id in _unique_strings(related) if item_id not in set(matched_items)]

    def _recipes_for_item(self, item_id: str, index: RuntimePackIndex) -> list[RuntimeRecipe]:
        return self._recipes_for_items([item_id], index)

    def _recipes_for_items(self, item_ids: list[str], index: RuntimePackIndex) -> list[RuntimeRecipe]:
        item_set = set(item_ids)
        return [recipe for recipe in index.recipes if recipe.result_item in item_set]

    def _quest_matches_for_item(
        self,
        connector_id: str,
        item_id: Optional[str],
        index: RuntimePackIndex,
        dump_id: Optional[str],
    ) -> list[Dict[str, str]]:
        if not item_id:
            return []
        matches = _runtime_quest_matches_for_item(index, item_id, dump_id)
        quest_summary = self.quest_summaries.get(connector_id)
        if not quest_summary:
            return matches
        existing_paths = {match["path"] for match in matches}
        for chapter in quest_summary.get("chapters", []):
            if not isinstance(chapter, Mapping):
                continue
            source_file = chapter.get("source_file") if isinstance(chapter.get("source_file"), str) else "chapters"
            for quest in chapter.get("quests", []):
                if not isinstance(quest, Mapping):
                    continue
                if not _quest_mentions_item(quest, item_id):
                    continue
                quest_id = quest.get("id") if isinstance(quest.get("id"), str) else "quest"
                label = quest.get("title") if isinstance(quest.get("title"), str) and quest.get("title") else quest_id
                path = f"{source_file}#{quest_id}"
                if path in existing_paths:
                    continue
                matches.append(
                    {
                        "path": path,
                        "label": label,
                        "quest_id": quest_id,
                        "source": "static:ftbquests",
                    }
                )
        return matches

    def _quest_matches_for_items(
        self,
        connector_id: str,
        item_ids: list[str],
        index: RuntimePackIndex,
        dump_id: Optional[str],
    ) -> list[Dict[str, str]]:
        matches: list[Dict[str, str]] = []
        seen_paths: set[str] = set()
        for item_id in item_ids:
            for match in self._quest_matches_for_item(connector_id, item_id, index, dump_id):
                path = match["path"]
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                match = dict(match)
                match.setdefault("item_id", item_id)
                matches.append(match)
        return matches

    def _next_steps(
        self,
        question: str,
        index: RuntimePackIndex,
        matched_item: Optional[str],
        matched_recipes: list[RuntimeRecipe],
        quest_matches: list[Dict[str, str]] | None = None,
        progress_scope: ProgressScope | None = None,
        matched_items: list[str] | None = None,
        related_items: list[str] | None = None,
        matched_mod: RuntimeMod | None = None,
        usage_recipes: list[RuntimeRecipe] | None = None,
    ) -> list[str]:
        quest_matches = quest_matches or []
        usage_recipes = usage_recipes or []
        matched_items = matched_items or ([] if matched_item is None else [matched_item])
        related_items = related_items or []
        scoped_items = _unique_strings([*matched_items, *related_items])
        if matched_mod is not None and _looks_like_mod_level_question(question):
            item_text = _format_item_list(index, scoped_items, limit=6) if scoped_items else matched_mod.mod_id
            return [
                f"先按 runtime mods 确认 {_mod_label(matched_mod)}，入口从 namespace 样例开始：{item_text}。",
                f"游戏内 JEI 搜 @{matched_mod.mod_id}，再以 runtime recipes 和 ftb_quests 的 source_refs 校验实际制作入口、任务覆盖和进度状态。",
            ]
        if len(scoped_items) > 1 and (matched_recipes or quest_matches):
            labels = _format_item_list(index, scoped_items, limit=6)
            return [
                f"把同族物品一起核对：{labels}。",
                "先看这些物品的 runtime result recipes，再看对应 runtime quest refs；用途配方只作为附加线索。",
            ]
        next_runtime_quests = _next_runtime_quests(index, progress_scope)
        if matched_item and matched_recipes:
            ingredients = _ingredient_items(matched_recipes)
            if ingredients and ("材料" in question or "缺" in question):
                return [
                    f"先核对服务器 runtime 配方材料：{_format_item_list(index, ingredients, limit=8)}。",
                    "再检查这些材料对应的机器链、任务依赖和 stage/player progress；缺口需要用队伍进度确认。",
                ]
            if quest_matches and ("解锁" in question or "前置" in question or "缺" in question):
                return [
                    f"先按任务书定位 {_item_label(index, matched_item)} 相关任务：{quest_matches[0]['label']}。",
                    "再以服务器 runtime recipes/tags 校验实际制作路径，最后补齐缺失的材料、任务、stage 或机器条件。",
                ]
            return [
                f"以服务器 runtime recipe 为准，先查看 {_item_label(index, matched_item)} 的 {len(matched_recipes)} 条当前配方。",
                "再把配方输入材料与已完成任务、stage 和机器库存对齐，缺口需要后续 player/team progress dump 判断。",
            ]
        if matched_item and quest_matches:
            progress = _quest_completion_summary(quest_matches, index, progress_scope)
            if progress:
                return [
                    f"先查看 {_item_label(index, matched_item)} 相关 runtime 任务进度：{progress}。",
                    "再按未完成任务的 dependencies、stage 和 runtime recipes/tags 校验实际解锁条件。",
                ]
            return [
                f"先查看任务书中引用 {_item_label(index, matched_item)} 的任务：{quest_matches[0]['label']}。",
                "当前仍缺服务器 runtime recipes/player progress，无法高置信判断已完成的前置条件。",
            ]
        if ("下一步" in question or "干什么" in question) and next_runtime_quests:
            labels = ", ".join(_quest_label(quest) for quest in next_runtime_quests[:3])
            return [
                f"优先检查这些未完成且依赖已满足或最接近满足的 runtime 任务：{labels}。",
                "再用 recipes/tags 校验任务物品的实际服务器配方，避免按网页或离线 JEI 走错线。",
            ]
        if "jei" in question.lower() or "配方" in question:
            return [
                "优先使用服务器 runtime dump 的 recipes/tags 作为真值，不用网页或离线 JEI 截图覆盖服务器数据。",
                "如果仍有差异，补充 KubeJS、datapack 和脚本静态检查结果，定位是脚本改配方还是进度/stage 限制。",
            ]
        if index.advancements or index.recipes:
            return [
                "先用 runtime recipes、tags 和 advancements 建立当前目标的依赖链。",
                "要给出队伍级下一步，还需要上传 FTB Quests、FTB Teams 或 stage/player progress section。",
            ]
        return [
            "先同步 connector hello 和 runtime dump，确认 Packwise 拿到当前整合包事实。",
            "再基于任务进度、stage 和配方图生成更具体的路线建议。",
        ]

    def _llm_summary(self, question: str, context: Mapping[str, Any], evidence: Mapping[str, Any]) -> str:
        assert self.chat_client is not None
        evidence_json = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2)
        safe_context = _llm_safe_context(context)
        prompt = (
            "你是 Packwise 的早期轻量 harness。"
            "只能基于提供的 QA facts 和 source_refs 回答；runtime recipes/tags/quests/source_refs 是最高优先级事实。"
            "你只能润色和组织这些事实，不能覆盖、删除或虚构 source_refs。"
            "面向玩家的正文必须优先使用 item_labels 中的名称；registry ID 只放在括号中或 source_refs 中。"
            "涉及路线建议时，必须区分已验证的 recipe/effect facts、缺失的 availability/acquisition/ranking facts，"
            "以及只能表述为“材料表面较轻”的启发式线索。"
            "没有明确获取难度和排序证据时，不要把已验证路线改写成最容易、最早、最便宜、最好、首选或推荐第一。"
            "如果 runtime_dump_present=true 或 pack_index=ready，不允许说没有 dump、没有索引、未接收 runtime dump。"
            "如果信息不足，只能说明具体缺哪类事实，例如 runtime recipes、ftb_quests、player/team progress 或 stages。"
            "\n\n问题："
            + question
            + "\n\n上下文："
            + json.dumps(safe_context, ensure_ascii=False, sort_keys=True)
            + "\n\nQA facts：\n"
            + evidence_json
        )
        return self.chat_client.complete(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "你是 Minecraft 整合包服务器的只读进度助理。"
                        "服务器 runtime dump、pack index、source_refs 比模型常识可靠。"
                        "没有获取/进度/排名证据时，不要声称某条路线最佳、最易、最早、最便宜或推荐优先。"
                    ),
                ),
                ChatMessage(role="user", content=prompt),
            ]
        )


def _inconsistent_runtime_answer(
    source_refs: list[Dict[str, str]],
    dump_id: str | None,
    consistency_errors: list[str],
    model_name: str,
) -> Dict[str, Any]:
    first_error = consistency_errors[0] if consistency_errors else "unknown runtime consistency error"
    refs = list(source_refs)
    if dump_id:
        refs.append(
            {
                "kind": "runtime_dump_section",
                "path": f"{dump_id}/runtime_consistency_errors",
                "label": "Runtime consistency errors",
            }
        )
    refs.append(
        {
            "kind": "protocol",
            "path": "docs/protocol/CONNECTOR_AGENT_PROTOCOL.md",
            "label": "Packwise protocol draft",
        }
    )
    return {
        "summary": f"Runtime dump {dump_id or 'unknown'} 存在一致性错误，暂不基于该 dump 给出配方、任务或进度结论：{first_error}。",
        "next_steps": [
            "先重新运行 /packwise dump，并检查 agent connector status 中的 runtime_consistency_errors。",
            "再用 validate-dump --require-phase1 校验本地 dump；修正缺失或不一致的 section 后再提问。",
        ],
        "source_refs": refs,
        "confidence": "low",
        "model": model_name,
    }


def _question_requests_creative_flight(question: str) -> bool:
    lowered = question.lower()
    compact = _compact_search_text(question)
    return (
        "创造飞行" in question
        or "创造模式飞行" in question
        or "creative_flight" in lowered
        or "creativeflight" in compact
        or ("creative" in lowered and "flight" in lowered)
        or "飞行护符" in question
        or ("potion charm" in lowered and "flying" in lowered)
    )


def _creative_flight_answer(
    question: str,
    index: RuntimePackIndex,
    dump_id: str | None,
    base_source_refs: list[Dict[str, str]],
    model_name: str,
) -> Dict[str, Any] | None:
    route, missing_facts = _creative_flight_route(index)
    source_refs = list(base_source_refs)
    source_refs.extend(_creative_runtime_section_source_refs(dump_id, index))
    if route is not None:
        source_refs.extend(_creative_route_source_refs(dump_id, index, route))
        source_refs = _dedupe_source_refs(source_refs)
        summary = _creative_flight_summary(index, route)
        return {
            "summary": summary,
            "next_steps": _creative_flight_next_steps(index, route),
            "source_refs": source_refs,
            "confidence": "high",
            "model": model_name,
        }

    source_refs = _dedupe_source_refs(source_refs)
    if not source_refs:
        source_refs.append(
            {
                "kind": "protocol",
                "path": "docs/protocol/CONNECTOR_AGENT_PROTOCOL.md",
                "label": "Packwise protocol draft",
            }
        )
    missing = "、".join(missing_facts) if missing_facts else "可验证路线事实"
    return {
        "summary": (
            "当前 runtime/static evidence 还不能验证“飞行药水 -> 飞行护符 -> 创造飞行”路线；"
            f"缺少或未匹配到：{missing}。Packwise 不会把飞行护符当作已证实路线来编造。"
        ),
        "next_steps": [
            "重新生成包含 recipes、potions、mob_effects 的 runtime dump，并确认 recipes 带 ingredient_slots。",
            "再检查 mob_effects 中是否有修改 attributeslib:creative_flight 的效果，以及 potions 中是否有包含该效果的药水。",
        ],
        "source_refs": source_refs,
        "confidence": "low",
        "model": model_name,
    }


def _creative_flight_route(index: RuntimePackIndex) -> tuple[CreativeFlightRoute | None, list[str]]:
    missing: list[str] = []
    if not index.recipes:
        missing.append("runtime recipes")
    if not index.potions:
        missing.append("runtime potions")
    if not index.mob_effects:
        missing.append("runtime mob_effects")
    if missing:
        return None, missing

    creative_effects = [effect for effect in index.mob_effects if _effect_grants_creative_flight(effect)]
    if not creative_effects:
        return None, ["mob_effects 中修改 attributeslib:creative_flight 的效果"]
    effect_ids = {effect.id for effect in creative_effects}
    flying_potions = [
        potion
        for potion in index.potions
        if any(effect.effect_id in effect_ids for effect in potion.effects)
    ]
    if not flying_potions:
        return None, ["potions 中包含 creative-flight 效果的药水"]

    charm_recipes = [recipe for recipe in index.recipes if _is_potion_charm_recipe(recipe)]
    if not charm_recipes:
        return None, ["Apotheosis potion charm recipe"]

    complete_candidates: list[tuple[int, RuntimeRecipe, RuntimePotion, RuntimeMobEffect, int, int]] = []
    for recipe in charm_recipes:
        potion_count = _recipe_slot_item_count(recipe, "minecraft:potion")
        blaze_powder_count = _recipe_slot_item_count(recipe, "minecraft:blaze_powder")
        if potion_count is None or blaze_powder_count is None:
            continue
        if potion_count <= 0 or blaze_powder_count <= 0:
            continue
        for potion in flying_potions:
            effect = next(
                (
                    candidate_effect
                    for candidate_effect in creative_effects
                    if any(potion_effect.effect_id == candidate_effect.id for potion_effect in potion.effects)
                ),
                None,
            )
            if effect is None:
                continue
            rank = 0 if potion_count == 3 and blaze_powder_count == 6 else 10
            rank += max(0, potion_count - 3) + max(0, blaze_powder_count - 6)
            complete_candidates.append((rank, recipe, potion, effect, potion_count, blaze_powder_count))
    if not complete_candidates:
        return None, ["recipe ingredient_slots 中的药水/烈焰粉数量"]

    _, recipe, potion, effect, potion_count, blaze_powder_count = sorted(
        complete_candidates,
        key=lambda item: (item[0], item[1].id, item[2].id, item[3].id),
    )[0]
    attribute = _creative_flight_attribute(effect) or "attributeslib:creative_flight"
    charm_item_id = recipe.result_item or recipe.id
    return (
        CreativeFlightRoute(
            recipe=recipe,
            potion=potion,
            effect=effect,
            creative_flight_attribute=attribute,
            potion_count=potion_count,
            blaze_powder_count=blaze_powder_count,
            charm_item_id=charm_item_id,
            other_route_items=_other_creative_flight_route_items(index, charm_item_id),
        ),
        [],
    )


def _effect_grants_creative_flight(effect: RuntimeMobEffect) -> bool:
    return _creative_flight_attribute(effect) is not None


def _creative_flight_attribute(effect: RuntimeMobEffect) -> str | None:
    for modifier in effect.attribute_modifiers:
        attribute_id = modifier.attribute_id.lower()
        if attribute_id == "attributeslib:creative_flight" or attribute_id.endswith(":creative_flight"):
            return modifier.attribute_id
    return None


def _is_potion_charm_recipe(recipe: RuntimeRecipe) -> bool:
    result_item = (recipe.result_item or "").lower()
    text = " ".join([recipe.id, recipe.type, recipe.serializer, result_item]).lower()
    if result_item.endswith(":potion_charm") or result_item.endswith("/potion_charm"):
        return True
    if "potion_charm" in text:
        return True
    return "potion" in text and "charm" in text


def _recipe_slot_item_count(recipe: RuntimeRecipe, item_id: str) -> int | None:
    if not recipe.ingredient_slots:
        return None
    count = 0
    for slot in recipe.ingredient_slots:
        if _slot_has_item(slot, item_id):
            count += 1
    return count


def _slot_has_item(slot: Mapping[str, Any], item_id: str) -> bool:
    item_ids = slot.get("item_ids")
    if isinstance(item_ids, list) and item_id in {item for item in item_ids if isinstance(item, str)}:
        return True
    candidates = slot.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            if candidate.get("item_id") == item_id:
                return True
    return False


def _creative_runtime_section_source_refs(dump_id: str | None, index: RuntimePackIndex) -> list[Dict[str, str]]:
    if not dump_id:
        return []
    refs: list[Dict[str, str]] = []
    if index.recipes:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/recipes", "label": "Runtime recipes"})
    if index.potions:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/potions", "label": "Runtime potions"})
    if index.mob_effects:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/mob_effects", "label": "Runtime mob effects"})
    return refs


def _creative_route_source_refs(
    dump_id: str | None,
    index: RuntimePackIndex,
    route: CreativeFlightRoute,
) -> list[Dict[str, str]]:
    refs = [
        {"kind": "recipe", "path": route.recipe.id, "label": route.recipe.result_item or route.recipe.id},
    ]
    if dump_id:
        refs.extend(
            [
                {
                    "kind": "potion",
                    "path": f"{dump_id}/potions#{route.potion.id}",
                    "label": _potion_label(route.potion, route.effect),
                },
                {
                    "kind": "mob_effect",
                    "path": f"{dump_id}/mob_effects#{route.effect.id}",
                    "label": _effect_label(route.effect),
                },
                {
                    "kind": "effect_attribute",
                    "path": f"{dump_id}/mob_effects#{route.effect.id}/{route.creative_flight_attribute}",
                    "label": route.creative_flight_attribute,
                },
            ]
        )
    return refs


def _creative_flight_summary(index: RuntimePackIndex, route: CreativeFlightRoute) -> str:
    potion_name = _potion_label(route.potion, route.effect)
    charm_name = _charm_plain_label(route.effect)
    charm_with_id = _charm_label(route.effect, route.charm_item_id)
    blaze_powder = _item_display_name(index, "minecraft:blaze_powder") or "烈焰粉"
    parts = [
        (
            f"已验证的一条创造飞行路线是 {charm_name}："
            f"{route.potion_count} 瓶{potion_name} + {route.blaze_powder_count} 个{blaze_powder} "
            f"-> {charm_name} -> 创造飞行。"
        ),
        (
            f"runtime potions 显示 {route.potion.id} 包含 {_effect_label(route.effect)}；"
            f"runtime mob_effects 显示该效果修改 {route.creative_flight_attribute}。"
        ),
        (
            f"Packwise 目前只验证了这条配方/药水/效果链，还没有排名{potion_name}的获取难度，"
            "也没有比较酿造、掉落、战利品、机器链、任务/stage 或玩家进度成本。"
        ),
        f"对应物品是 {charm_with_id}。使用时右键启用，启用后把护符留在背包；Curios 槽位是否可用取决于服务器 Apotheosis/Curios 配置。",
    ]
    if route.other_route_items:
        other_routes = _format_item_list(index, route.other_route_items, limit=4)
        if _other_route_materials_indicate_later(index, route.other_route_items):
            parts.append(
                f"其他可见路线仍可查：{other_routes}；"
                "这些路线的 runtime 配方中出现了看起来更后期的材料，但 Packwise 还不能据此做路线难度或先后排名。"
            )
        else:
            parts.append(f"其他可见路线仍可查：{other_routes}。")
    return "".join(parts)


def _creative_flight_next_steps(index: RuntimePackIndex, route: CreativeFlightRoute) -> list[str]:
    potion_name = _potion_label(route.potion, route.effect)
    charm_name = _charm_label(route.effect, route.charm_item_id)
    return [
        f"先确认 {potion_name} 来源，再按 runtime recipe {route.recipe.id} 合成 {charm_name}。",
        "合成后右键切换启用；启用状态下把护符保留在背包，若服务器配置了 Curios 槽位则可放对应槽位。",
    ]


def _potion_label(potion: RuntimePotion, effect: RuntimeMobEffect) -> str:
    effect_name = _effect_short_name(effect)
    return f"{effect_name}药水"


def _charm_label(effect: RuntimeMobEffect, item_id: str) -> str:
    return f"{_charm_plain_label(effect)}（{item_id}）"


def _charm_plain_label(effect: RuntimeMobEffect) -> str:
    effect_name = _effect_short_name(effect)
    return f"{effect_name}护符"


def _effect_label(effect: RuntimeMobEffect) -> str:
    short_name = _effect_short_name(effect)
    return f"{short_name}（{effect.id}）"


def _effect_short_name(effect: RuntimeMobEffect) -> str:
    common = _COMMON_ZH_EFFECT_NAMES.get(effect.id)
    if common:
        return common
    for value in [effect.display_name, effect.description, _readable_item_id_fallback(effect.id)]:
        if value and not _looks_like_translation_key(value):
            return value
    return effect.id


def _other_creative_flight_route_items(index: RuntimePackIndex, charm_item_id: str) -> list[str]:
    keywords = [
        "angel_ring",
        "swiftwolf",
        "rending_gale",
        "creative_flight",
        "flight_module",
        "flightmodule",
        "draconic_flight",
    ]
    zh_keywords = ["天使戒指", "疾风戒指", "创造飞行模块", "飞行模块"]
    candidates: list[str] = []
    for item_id in _candidate_item_ids(index):
        if item_id == charm_item_id:
            continue
        item_text = item_id.lower()
        aliases = _item_search_aliases(index, item_id)
        if any(keyword in item_text for keyword in keywords):
            candidates.append(item_id)
            continue
        if any(keyword in alias for alias in aliases for keyword in zh_keywords):
            candidates.append(item_id)
    return _unique_strings(candidates)


def _other_route_materials_indicate_later(index: RuntimePackIndex, item_ids: list[str]) -> bool:
    late_markers = [
        "nether_star",
        "dragon",
        "draconic",
        "wyvern",
        "awakened",
        "infinity",
        "allthemodium",
        "vibranium",
        "unobtainium",
        "netherite",
        "dark_matter",
        "red_matter",
    ]
    item_set = set(item_ids)
    material_ids: list[str] = []
    for recipe in index.recipes:
        if recipe.result_item not in item_set:
            continue
        material_ids.extend(recipe.ingredient_items)
        for slot in recipe.ingredient_slots:
            item_ids_value = slot.get("item_ids")
            if isinstance(item_ids_value, list):
                material_ids.extend(item for item in item_ids_value if isinstance(item, str))
    return any(any(marker in material_id.lower() for marker in late_markers) for material_id in material_ids)


def _runtime_section_source_refs(
    dump_id: str | None,
    index: RuntimePackIndex,
    include_mods: bool = False,
    include_items: bool = False,
) -> list[Dict[str, str]]:
    if not dump_id:
        return []
    refs: list[Dict[str, str]] = []
    if include_mods and index.mods:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/mods", "label": "Runtime mods"})
    if include_items and index.items:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/items", "label": "Runtime items"})
    if index.recipes:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/recipes", "label": "Runtime recipes"})
    if index.potions:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/potions", "label": "Runtime potions"})
    if index.mob_effects:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/mob_effects", "label": "Runtime mob effects"})
    if index.tags:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/tags", "label": "Runtime tags"})
    if index.advancements:
        refs.append(
            {"kind": "runtime_dump_section", "path": f"{dump_id}/advancements", "label": "Runtime advancements"}
        )
    if index.ftb_quests:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/ftb_quests", "label": "Runtime FTB Quests"})
    if index.player_progress or index.team_progress:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/progress", "label": "Runtime player/team progress"})
    if index.stages:
        refs.append({"kind": "runtime_dump_section", "path": f"{dump_id}/stages", "label": "Runtime stages"})
    return refs


def _dedupe_source_refs(source_refs: list[Dict[str, str]]) -> list[Dict[str, str]]:
    deduped: list[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in source_refs:
        key = (ref.get("kind", ""), ref.get("path", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _answer_readiness(
    runtime_counts: Mapping[str, int],
    has_selected_dump_id: bool,
    runtime_dump_present: bool,
) -> Dict[str, str]:
    pack_index_ready = any(count > 0 for count in runtime_counts.values())
    return {
        "runtime_dump": "ready"
        if runtime_dump_present
        else ("selected_dump_id_without_manifest" if has_selected_dump_id else "missing_runtime_dump"),
        "pack_index": "ready" if pack_index_ready else "empty",
        "recipe_questions": "ready" if runtime_counts.get("recipes", 0) else "missing_runtime_recipes",
        "potion_questions": "ready" if runtime_counts.get("potions", 0) else "missing_runtime_potions",
        "effect_questions": "ready" if runtime_counts.get("mob_effects", 0) else "missing_runtime_mob_effects",
        "tag_questions": "ready" if runtime_counts.get("tags", 0) else "missing_runtime_tags",
        "quest_questions": "ready" if runtime_counts.get("ftb_quests", 0) else "missing_runtime_ftb_quests",
        "progress_questions": "ready"
        if runtime_counts.get("player_progress", 0) or runtime_counts.get("team_progress", 0)
        else "missing_runtime_player_or_team_progress",
        "stage_questions": "ready" if runtime_counts.get("stages", 0) else "missing_runtime_stages",
    }


def _ask_evidence(
    connector_id: str | None,
    dump_id: str | None,
    runtime_dump_present: bool,
    runtime_counts: Mapping[str, int],
    answer_readiness: Mapping[str, str],
    route_ranking_context: bool,
    route_ranking_question: bool,
    matched_mod: RuntimeMod | None,
    matched_items: list[str],
    related_items: list[str],
    matched_recipes: list[RuntimeRecipe],
    matched_usage_recipes: list[RuntimeRecipe],
    quest_matches: list[Dict[str, str]],
    source_refs: list[Dict[str, str]],
    item_labels: Mapping[str, str],
) -> Dict[str, Any]:
    missing_facts = [
        key
        for key, state in answer_readiness.items()
        if isinstance(state, str) and state.startswith("missing_")
    ]
    return {
        "selected_connector_id": connector_id,
        "selected_dump_id": dump_id,
        "runtime_dump_present": runtime_dump_present,
        "runtime_counts": dict(runtime_counts),
        "answer_readiness": dict(answer_readiness),
        "route_ranking_context": route_ranking_context,
        "route_ranking_question": route_ranking_question,
        "missing_facts": missing_facts,
        "matched_mod_candidates": [] if matched_mod is None else [matched_mod.to_dict()],
        "matched_item_candidates": list(matched_items),
        "matched_item_labels": [_item_label_from_map(item_labels, item_id) for item_id in matched_items],
        "related_items": list(related_items),
        "related_item_labels": [_item_label_from_map(item_labels, item_id) for item_id in related_items],
        "item_labels": dict(item_labels),
        "matched_recipes": [_recipe_fact(recipe, item_labels) for recipe in matched_recipes[:8]],
        "matched_usage_recipes": [_recipe_fact(recipe, item_labels) for recipe in matched_usage_recipes[:4]],
        "matched_quests": [dict(match) for match in quest_matches[:8]],
        "source_refs": list(source_refs),
        "source_policy": {
            "recipes": "runtime recipes/tags are authoritative when present",
            "recipe_usage": "usage recipes show where matched items are consumed; do not describe them as direct crafting recipes for the matched item",
            "quests": "runtime ftb_quests are authoritative when present",
            "item_names": "player-facing prose should use item_labels first, with registry IDs only as parenthetical anchors",
            "route_ranking": (
                "Do not describe a verified route as easiest, earliest, cheapest, best, or recommended first "
                "unless explicit acquisition and ranking evidence is present. Distinguish verified recipe/effect "
                "facts from missing availability facts and tentative material-light heuristics."
            ),
            "llm_role": "polish only; do not override source_refs",
        },
    }


def _recipe_fact(recipe: RuntimeRecipe, item_labels: Mapping[str, str]) -> Dict[str, Any]:
    return {
        "id": recipe.id,
        "type": recipe.type,
        "serializer": recipe.serializer,
        "result_item": recipe.result_item,
        "result_label": None if recipe.result_item is None else _item_label_from_map(item_labels, recipe.result_item),
        "result_count": recipe.result_count,
        "ingredient_items": recipe.ingredient_items[:12],
        "ingredient_labels": [_item_label_from_map(item_labels, item_id) for item_id in recipe.ingredient_items[:12]],
        "ingredient_count": len(recipe.ingredient_items),
        "ingredient_slots": recipe.ingredient_slots[:12],
        "slot_count": len(recipe.ingredient_slots),
        "width": recipe.width,
        "height": recipe.height,
        "source": recipe.source,
    }


def _llm_safe_context(context: Mapping[str, Any]) -> Dict[str, Any]:
    allowed_keys = {
        "connector_id",
        "dump_id",
        "item_id",
        "team_id",
        "player_id",
        "player_uuid",
        "player_name",
        "server_id",
        "locale",
    }
    return {
        key: value
        for key, value in context.items()
        if key in allowed_keys and isinstance(value, (str, int, float, bool, type(None)))
    }


def _evidence_item_ids(
    item_scope: list[str],
    matched_recipes: list[RuntimeRecipe],
    matched_usage_recipes: list[RuntimeRecipe],
    quest_matches: list[Dict[str, str]],
) -> list[str]:
    item_ids: list[str] = list(item_scope)
    for recipe in [*matched_recipes, *matched_usage_recipes]:
        if recipe.result_item:
            item_ids.append(recipe.result_item)
        item_ids.extend(recipe.ingredient_items)
    for quest in quest_matches:
        item_id = quest.get("item_id")
        if isinstance(item_id, str):
            item_ids.append(item_id)
    return _unique_strings(item_ids)


def _item_label_map(index: RuntimePackIndex, item_ids: list[str]) -> Dict[str, str]:
    return {item_id: _item_label(index, item_id) for item_id in item_ids}


def _item_label(index: RuntimePackIndex, item_id: str) -> str:
    display_name = _item_display_name(index, item_id)
    if display_name and display_name.lower() != item_id.lower():
        return f"{display_name}（{item_id}）"
    return item_id


def _item_display_name(index: RuntimePackIndex, item_id: str) -> str | None:
    entry = _runtime_entry_for_item(index, item_id)
    runtime_translated_name = None if entry is None else entry.translated_name
    runtime_display_name = None if entry is None else entry.display_name
    cjk_display_name = runtime_display_name if runtime_display_name and _contains_cjk(runtime_display_name) else None
    fallback_display_name = runtime_display_name if runtime_display_name != cjk_display_name else None
    for value in [
        runtime_translated_name,
        cjk_display_name,
        _COMMON_ZH_ITEM_NAMES.get(item_id),
        fallback_display_name,
        _readable_item_id_fallback(item_id),
    ]:
        if value and value != item_id and not _looks_like_translation_key(value):
            return value
    return None


def _item_search_aliases(index: RuntimePackIndex, item_id: str) -> list[str]:
    entry = _runtime_entry_for_item(index, item_id)
    aliases = [
        None if entry is None else entry.translated_name,
        None if entry is None else entry.display_name,
        _COMMON_ZH_ITEM_NAMES.get(item_id),
        _readable_item_id_fallback(item_id),
        *_generated_item_search_aliases(item_id),
    ]
    return [
        alias
        for alias in _unique_strings(aliases)
        if alias and alias != item_id and not _looks_like_translation_key(alias)
    ]


def _generated_item_search_aliases(item_id: str) -> list[str]:
    _, _, path = item_id.partition(":")
    if not path:
        return []
    path = path.rsplit("/", 1)[-1]
    aliases: list[str | None] = []
    if path.startswith("item_"):
        aliases.append(_readable_path_alias(path.removeprefix("item_")))
    if "flight" in path and "module" not in path:
        module_path = path.removeprefix("item_") if path.startswith("item_") else path
        aliases.append(_readable_path_alias(f"{module_path}_module"))
    return _unique_strings(aliases)


def _readable_path_alias(path: str) -> str | None:
    tokens = [token for token in re.split(r"[^0-9A-Za-z]+", path) if token]
    if not tokens:
        return None
    return " ".join(token.upper() if token.isupper() else token.capitalize() for token in tokens)


def _runtime_entry_for_item(index: RuntimePackIndex, item_id: str) -> RuntimeRegistryEntry | None:
    for entry in index.items:
        if entry.id == item_id:
            return entry
    return None


def _item_label_from_map(item_labels: Mapping[str, str], item_id: str) -> str:
    return item_labels.get(item_id, item_id)


def _format_item_list(index: RuntimePackIndex, item_ids: list[str], limit: int = 8) -> str:
    return ", ".join(_item_label(index, item_id) for item_id in item_ids[:limit])


def _format_item_chain(index: RuntimePackIndex, item_ids: list[str]) -> str:
    return " -> ".join(_item_label(index, item_id) for item_id in item_ids)


def _localize_summary_item_ids(summary: str, evidence: Mapping[str, Any]) -> str:
    item_labels = evidence.get("item_labels")
    if not isinstance(item_labels, Mapping):
        return summary
    localized = summary
    replacements = [
        (item_id, label)
        for item_id, label in item_labels.items()
        if isinstance(item_id, str)
        and isinstance(label, str)
        and item_id
        and label
        and label != item_id
    ]
    for item_id, label in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(rf"(?<![0-9A-Za-z_.:/-]){re.escape(item_id)}(?![0-9A-Za-z_.:/-])")

        def replace(match: re.Match[str]) -> str:
            before = localized[match.start() - 1] if match.start() > 0 else ""
            after = localized[match.end()] if match.end() < len(localized) else ""
            if before in {"（", "("} and after in {"）", ")"}:
                return item_id
            return label

        localized = pattern.sub(replace, localized)
    return localized


def _looks_like_translation_key(value: str) -> bool:
    return value.startswith(("item.", "block.", "fluid."))


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _readable_item_id_fallback(item_id: str) -> str | None:
    _, _, path = item_id.partition(":")
    if not path:
        path = item_id
    path = path.rsplit("/", 1)[-1]
    tokens = [token for token in re.split(r"[^0-9A-Za-z]+", path) if token]
    if not tokens:
        return None
    return " ".join(token.upper() if token.isupper() else token.capitalize() for token in tokens)


_COMMON_ZH_ITEM_NAMES: Dict[str, str] = {
    "everlastingabilities:ability_bottle": "能力瓶",
    "everlastingabilities:ability_totem": "能力图腾",
    "industrialforegoing:pink_slime": "粉色黏液",
    "minecraft:bucket": "桶",
    "minecraft:gold_nugget": "金粒",
    "minecraft:slime_ball": "黏液球",
    "minecraft:white_dye": "白色染料",
    "minecraft:potion": "药水",
    "minecraft:blaze_powder": "烈焰粉",
    "apotheosis:potion_charm": "药水护符",
    "angelring:angel_ring": "天使戒指",
    "projecte:swiftwolf_rending_gale": "疾风戒指",
    "draconicevolution:creative_flight_module": "创造飞行模块",
    "draconicevolution:item_wyvern_flight": "飞龙飞行模块",
    "draconicevolution:item_draconic_flight": "神龙飞行模块",
    "draconicevolution:item_chaotic_flight": "混沌飞行模块",
    "minecraft:glass": "玻璃",
    "minecraft:redstone": "红石",
    "minecraft:quartz": "下界石英",
    "xycraft_machines:resin_ball": "树脂球",
    "thermal:upgrade_augment_1": "硬化升级组件",
    "thermal:upgrade_augment_2": "强化升级组件",
    "thermal:upgrade_augment_3": "谐振升级组件",
    "thermal_extra:upgrade_augment": "龙钢升级组件",
    "thermal_extra:abyssal_upgrade_augment": "深渊升级组件",
    "alltheores:gold_gear": "金齿轮",
    "thermal:gold_gear": "金齿轮",
    "alltheores:invar_ingot": "殷钢锭",
    "thermal:invar_ingot": "殷钢锭",
    "alltheores:signalum_gear": "信素齿轮",
    "thermal:signalum_gear": "信素齿轮",
    "alltheores:electrum_ingot": "琥珀金锭",
    "thermal:electrum_ingot": "琥珀金锭",
    "alltheores:lumium_gear": "流明齿轮",
    "thermal:lumium_gear": "流明齿轮",
    "alltheores:enderium_ingot": "末影锭",
    "thermal:enderium_ingot": "末影锭",
    "thermal_extra:ancient_dust": "远古之尘",
    "thermal_extra:dragonsteel_gear": "龙钢齿轮",
}

_COMMON_ZH_EFFECT_NAMES: Dict[str, str] = {
    "attributeslib:flying": "飞行",
}


def _enforce_source_policy(summary: str, fallback_summary: str, evidence: Mapping[str, Any]) -> str:
    clean_summary = summary.strip()
    if not clean_summary:
        return fallback_summary
    if _summary_conflicts_with_evidence(clean_summary, evidence):
        return fallback_summary
    return _supplement_summary_from_evidence(clean_summary, evidence)


def _summary_conflicts_with_evidence(summary: str, evidence: Mapping[str, Any]) -> bool:
    text = summary.lower()
    answer_readiness = evidence.get("answer_readiness")
    if not isinstance(answer_readiness, Mapping):
        answer_readiness = {}
    if evidence.get("runtime_dump_present") is True and _contains_any(
        text,
        [
            "没有 dump",
            "没有dump",
            "没有 runtime dump",
            "没有runtime dump",
            "未接收 runtime dump",
            "未接收runtime dump",
            "缺 runtime dump",
            "缺少 runtime dump",
            "runtime dump 不存在",
            "no runtime dump",
        ],
    ):
        return True
    if answer_readiness.get("pack_index") == "ready" and _contains_any(
        text,
        [
            "没有索引",
            "没有 pack index",
            "没有pack index",
            "没有 runtime index",
            "没有runtime index",
            "缺索引",
            "no pack index",
            "no runtime index",
        ],
    ):
        return True
    matched_recipes = evidence.get("matched_recipes")
    if isinstance(matched_recipes, list) and matched_recipes and _contains_any(
        text,
        ["没有配方", "未找到配方", "缺少配方", "no recipe", "no recipes"],
    ):
        return True
    matched_quests = evidence.get("matched_quests")
    if isinstance(matched_quests, list) and matched_quests and _contains_any(
        text,
        ["没有任务", "未找到任务", "缺少任务", "no quest", "no quests"],
    ):
        return True
    if evidence.get("route_ranking_question") is True:
        return True
    if _claims_unverified_route_ranking(text, evidence):
        return True
    known_ids = _known_fact_ids(evidence)
    if known_ids:
        for item_id in re.findall(r"\b[a-z0-9_.-]+:[a-z0-9_./-]+\b", text):
            if item_id.startswith(("runtime:", "static:")):
                continue
            if item_id not in known_ids:
                return True
    return False


def _route_ranking_context(question: str, matched_items: list[str], related_items: list[str]) -> bool:
    text = question.lower()
    if _contains_any(text, _creative_flight_route_terms()):
        return True
    return any(
        _item_id_looks_like_creative_flight_route(item_id)
        for item_id in [*matched_items, *related_items]
    )


def _route_ranking_question(question: str, route_ranking_context: bool) -> bool:
    if not route_ranking_context:
        return False
    text = question.lower()
    ranking_question_markers = [
        "哪个",
        "哪条",
        "哪种",
        "哪一个",
        "更",
        "比",
        "比较",
        "还是",
        "或者",
        "或是",
        "推荐",
        "优先",
        "先",
        "最",
        "前期",
        "早",
        "容易",
        "便宜",
        "好",
        "which",
        "better",
        "earlier",
        "easier",
        "cheaper",
        "best",
        "recommend",
        "priority",
        "first",
        " vs ",
        " or ",
        " versus ",
        "/",
    ]
    return _contains_any(text, ranking_question_markers)


def _item_id_looks_like_creative_flight_route(item_id: str) -> bool:
    lowered = item_id.lower()
    route_item_markers = [
        "angel_ring",
        "swiftwolf",
        "rending_gale",
        "creative_flight",
        "flight_module",
        "flightmodule",
        "draconic_flight",
        "potion_charm",
    ]
    return any(marker in lowered for marker in route_item_markers)


def _creative_flight_route_terms() -> list[str]:
    return [
        "创造飞行",
        "creative flight",
        "creative_flight",
        "飞行护符",
        "飞行药水",
        "天使戒指",
        "angel ring",
        "swiftwolf",
        "rending gale",
        "疾风戒指",
        "draconic flight",
        "飞行模块",
    ]


def _claims_unverified_route_ranking(text: str, evidence: Mapping[str, Any]) -> bool:
    ranking_terms = [
        "推荐",
        "建议",
        "优先",
        "首推",
        "首选",
        "第一",
        "先",
        "更",
        "更早",
        "更好",
        "更便宜",
        "更容易",
        "更简单",
        "便宜",
        "容易",
        "简单",
        "前期",
        "早期",
        "低成本",
        "成本低",
        "选它",
        "选这个",
        "选择它",
        "选择这个",
        "挑这个",
        "最容易",
        "最简单",
        "最早",
        "最便宜",
        "最好",
        "最佳",
        "首选",
        "优先路线",
        "优先推荐",
        "推荐优先",
        "建议先",
        "先做",
        "先拿",
        "先获取",
        "先走",
        "先合成",
        "先制作",
        "先选择",
        "推荐先",
        "建议优先",
        "优先做",
        "优先获取",
        "优先考虑",
        "优先选择",
        "应排在",
        "推荐第一",
        "第一个推荐",
        "recommend",
        "recommended",
        "recommendation",
        "first",
        "priority",
        "choice",
        "start",
        "begin",
        "cheaper",
        "better",
        "earlier",
        "sooner",
        "easier",
        "simpler",
        "faster",
        "low cost",
        "lower cost",
        "less expensive",
        "early",
        "pick",
        "choose",
        "select",
        "go with",
        "prefer",
        "preferred",
        "optimal",
        "easiest",
        "earliest",
        "cheapest",
        "best",
        "recommended first",
        "first recommendation",
        "top recommendation",
        "priority route",
        "priority recommendation",
        "preferred route",
        "recommended route",
        "prioritize",
        "start with",
        "begin with",
        "do first",
        "make first",
        "craft first",
        "get first",
        "choose first",
        "pick first",
        "go for",
    ]
    route_context = evidence.get("route_ranking_context") is True or _contains_any(text, _creative_flight_route_terms())
    if not route_context:
        return False
    return _contains_any(text, ranking_terms)


def _known_fact_ids(evidence: Mapping[str, Any]) -> set[str]:
    known: set[str] = set()
    for key in ("matched_item_candidates", "related_items"):
        values = evidence.get(key)
        if isinstance(values, list):
            known.update(value.lower() for value in values if isinstance(value, str))
    recipes = evidence.get("matched_recipes")
    if isinstance(recipes, list):
        for recipe in recipes:
            if not isinstance(recipe, Mapping):
                continue
            for key in ("id", "result_item"):
                value = recipe.get(key)
                if isinstance(value, str) and value:
                    known.add(value.lower())
            ingredients = recipe.get("ingredient_items")
            if isinstance(ingredients, list):
                known.update(item.lower() for item in ingredients if isinstance(item, str))
    usage_recipes = evidence.get("matched_usage_recipes")
    if isinstance(usage_recipes, list):
        for recipe in usage_recipes:
            if not isinstance(recipe, Mapping):
                continue
            for key in ("id", "result_item"):
                value = recipe.get(key)
                if isinstance(value, str) and value:
                    known.add(value.lower())
            ingredients = recipe.get("ingredient_items")
            if isinstance(ingredients, list):
                known.update(item.lower() for item in ingredients if isinstance(item, str))
    source_refs = evidence.get("source_refs")
    if isinstance(source_refs, list):
        for ref in source_refs:
            if not isinstance(ref, Mapping):
                continue
            path = ref.get("path")
            if isinstance(path, str):
                known.add(path.lower())
                if "#" in path:
                    known.add(path.rsplit("#", 1)[-1].lower())
    return known


def _supplement_summary_from_evidence(summary: str, evidence: Mapping[str, Any]) -> str:
    supplements: list[str] = []
    item_ids = _critical_evidence_item_ids(evidence)
    missing_item_ids = [item_id for item_id in item_ids if item_id.lower() not in summary.lower()]
    if missing_item_ids:
        item_labels = evidence.get("item_labels")
        if not isinstance(item_labels, Mapping):
            item_labels = {}
        labels = [_item_label_from_map(item_labels, item_id) for item_id in missing_item_ids[:8]]
        supplements.append(f"Runtime 物品：{', '.join(labels)}。")

    quest_labels = _critical_evidence_quest_labels(evidence)
    missing_quest_labels = [label for label in quest_labels if label.lower() not in summary.lower()]
    if missing_quest_labels:
        supplements.append(f"Runtime 任务引用：{', '.join(missing_quest_labels[:6])}。")

    if not supplements:
        return summary
    return summary.rstrip() + "\n\n" + " ".join(supplements)


def _critical_evidence_item_ids(evidence: Mapping[str, Any]) -> list[str]:
    item_ids: list[str] = []
    for key in ("matched_item_candidates", "related_items"):
        values = evidence.get(key)
        if isinstance(values, list):
            item_ids.extend(value for value in values if isinstance(value, str) and ":" in value)
    return _unique_strings(item_ids)


def _critical_evidence_quest_labels(evidence: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    quests = evidence.get("matched_quests")
    if isinstance(quests, list):
        for quest in quests:
            if not isinstance(quest, Mapping):
                continue
            label = quest.get("label")
            if isinstance(label, str) and label:
                labels.append(label)
    return _unique_strings(labels)


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _mod_label(mod: RuntimeMod) -> str:
    return f"{mod.display_name} {mod.version}".strip()


def _unique_strings(values: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_search_text(text: str) -> str:
    lowered = text.lower()
    lowered = lowered.replace("/", " ")
    lowered = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff:.-]+", " ", lowered)
    lowered = lowered.replace("_", " ")
    lowered = lowered.replace("-", " ")
    lowered = lowered.replace(".", " ")
    return re.sub(r"\s+", " ", lowered).strip()


def _compact_search_text(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text.lower())


def _significant_tokens(path: str) -> list[str]:
    tokens = re.split(r"[^0-9a-zA-Z]+", path.lower())
    stopwords = {"a", "an", "the", "of", "to", "or", "and", "in", "on", "for", "from"}
    return [token for token in tokens if len(token) >= 3 and token not in stopwords]


def _candidate_item_ids(index: RuntimePackIndex) -> list[str]:
    candidates: list[str] = []
    candidates.extend(entry.id for entry in index.items)
    candidates.extend(recipe.result_item for recipe in index.recipes if recipe.result_item)
    candidates.extend(item_id for quest in index.ftb_quests for item_id in quest.task_item_ids)
    candidates.extend(item_id for quest in index.ftb_quests for item_id in quest.reward_item_ids)
    return sorted(_unique_strings(candidates))


def _registry_namespaces_in_text(text: str) -> list[str]:
    return _unique_strings([match.group(1) for match in re.finditer(r"\b([a-z0-9_.-]+):[a-z0-9_./-]+\b", text.lower())])


def _looks_like_mod_level_question(question: str) -> bool:
    lowered = question.lower()
    return any(
        marker in lowered
        for marker in [
            "模组",
            "mod",
            "干什么",
            "怎么开始",
            "开始用",
            "怎么用",
            "怎么玩",
            "任务书",
            "what does",
            "how do i start",
        ]
    )


def _items_for_mod_namespace(index: RuntimePackIndex, namespace: str, limit: int) -> list[str]:
    namespace_prefix = f"{namespace}:"
    items = [item_id for item_id in _candidate_item_ids(index) if item_id.startswith(namespace_prefix)]
    return sorted(items, key=lambda item_id: (_namespace_item_rank(item_id), item_id))[:limit]


def _namespace_item_rank(item_id: str) -> int:
    path = item_id.split(":", 1)[-1]
    priority_terms = ("ability_bottle", "ability_totem", "upgrade_augment")
    for rank, term in enumerate(priority_terms):
        if term in path:
            return rank
    return 100


def _normalized_phrase_in_text(phrase: str, text: str) -> bool:
    phrase_tokens = phrase.split()
    text_tokens = text.split()
    if not phrase_tokens or len(phrase_tokens) > len(text_tokens):
        return False
    for start in range(0, len(text_tokens) - len(phrase_tokens) + 1):
        if text_tokens[start : start + len(phrase_tokens)] != phrase_tokens:
            continue
        following_index = start + len(phrase_tokens)
        if following_index < len(text_tokens) and text_tokens[following_index].isdigit():
            continue
        return True
    return False


def _exact_item_matches(question: str, index: RuntimePackIndex) -> list[str]:
    haystack = question.lower()
    normalized_question = _normalize_search_text(question)
    question_tokens = set(normalized_question.split())
    compact_question = _compact_search_text(question)
    matches: list[tuple[int, str]] = []
    for item_id in _candidate_item_ids(index):
        lowered = item_id.lower()
        if lowered in haystack:
            matches.append((1000 + len(lowered), item_id))
            continue
        path = lowered.split(":", 1)[-1]
        path_phrase = _normalize_search_text(path)
        path_tokens = path_phrase.split()
        if len(path_tokens) > 1 and _normalized_phrase_in_text(path_phrase, normalized_question):
            matches.append((650 + len(path_phrase), item_id))
            continue
        if len(path_tokens) == 1 and path_tokens[0] in question_tokens:
            matches.append((600 + len(path_tokens[0]), item_id))
            continue
        for alias in _item_search_aliases(index, item_id):
            normalized_alias = _normalize_search_text(alias)
            compact_alias = _compact_search_text(alias)
            if _normalized_phrase_in_text(normalized_alias, normalized_question):
                matches.append((800 + len(normalized_alias), item_id))
                break
            if _contains_cjk(alias) and compact_alias and compact_alias in compact_question:
                matches.append((800 + len(compact_alias), item_id))
                break
    return _unique_strings([item_id for _, item_id in sorted(matches, key=lambda item: (-item[0], item[1]))[:5]])


def _question_requests_item_family(question: str) -> bool:
    normalized = _normalize_search_text(question)
    compact = _compact_search_text(question)
    explicit_markers = [
        "分别",
        "顺序",
        "升级顺序",
        "配方链",
        "升级链",
        "同族",
        "那堆",
        "这堆",
        "这一组",
        "这些",
        "它们",
        "各自",
        "upgrade chain",
        "upgrade order",
        "upgrade sequence",
        "progression",
        "family",
        "upgrades",
    ]
    if any(marker in question or marker in normalized or marker in compact for marker in explicit_markers):
        return True
    tier_markers = [
        "hardened",
        "reinforced",
        "resonant",
        "硬化",
        "强化",
        "谐振",
    ]
    return sum(1 for marker in tier_markers if marker in normalized or marker in compact or marker in question) >= 2


def _question_family_items(
    question: str,
    index: RuntimePackIndex,
    matched_mod: RuntimeMod | None,
) -> list[str]:
    normalized = _normalize_search_text(question)
    compact = _compact_search_text(question)
    thermal_hint = (
        "thermal" in normalized
        or "热力" in question
        or (matched_mod is not None and matched_mod.mod_id == "thermal")
    )
    upgrade_hint = any(
        marker in normalized or marker in compact
        for marker in [
            "upgrade",
            "augment",
            "hardened",
            "reinforced",
            "resonant",
            "升级",
            "升级件",
            "硬化",
            "强化",
            "谐振",
        ]
    )
    if thermal_hint and upgrade_hint:
        thermal_family = [
            item_id
            for item_id in [
                "thermal:upgrade_augment_1",
                "thermal:upgrade_augment_2",
                "thermal:upgrade_augment_3",
            ]
            if _item_exists(index, item_id)
        ]
        if thermal_family:
            return thermal_family

    if "upgrade augment" in normalized or "upgrade_augment" in question.lower():
        return [
            item_id
            for item_id in _candidate_item_ids(index)
            if item_id.split(":", 1)[-1].startswith("upgrade_augment")
        ][:8]
    return []


def _item_exists(index: RuntimePackIndex, item_id: str) -> bool:
    return item_id in set(_candidate_item_ids(index))


def _is_sibling_item(item_id: str, other_id: str) -> bool:
    if item_id == other_id:
        return True
    namespace, _, path = item_id.partition(":")
    other_namespace, _, other_path = other_id.partition(":")
    if namespace != other_namespace or not path or not other_path:
        return False
    return _family_key(path) == _family_key(other_path)


def _family_key(path: str) -> str:
    stripped = re.sub(r"_(?:[0-9]+|basic|hardened|reinforced|resonant)$", "", path.lower())
    return stripped or path.lower()


def _recipe_is_directly_about_items(recipe: RuntimeRecipe, item_ids: set[str]) -> bool:
    item_namespaces = {item_id.split(":", 1)[0] for item_id in item_ids if ":" in item_id}
    recipe_id = recipe.id.lower()
    if any(namespace and namespace in recipe_id for namespace in item_namespaces):
        return True
    return any(item_id.split(":", 1)[-1].lower() in recipe_id for item_id in item_ids)


def _usage_recipes_for_items(item_ids: list[str], index: RuntimePackIndex) -> list[RuntimeRecipe]:
    item_set = set(item_ids)
    if not item_set:
        return []
    return [
        recipe
        for recipe in index.recipes
        if recipe.result_item not in item_set
        and any(item_id in item_set for item_id in recipe.ingredient_items)
        and _recipe_is_directly_about_items(recipe, item_set)
    ]


def _mod_level_summary(
    index: RuntimePackIndex,
    matched_mod: RuntimeMod,
    scoped_items: list[str],
    matched_recipes: list[RuntimeRecipe],
    quest_matches: list[Dict[str, str]],
    usage_recipes: list[RuntimeRecipe] | None = None,
) -> str:
    usage_recipes = usage_recipes or []
    parts = [f"runtime mods 显示 {_mod_label(matched_mod)} ({matched_mod.mod_id}) 存在。"]
    if scoped_items:
        parts.append(f"namespace 下可见物品包括：{_format_item_list(index, scoped_items, limit=8)}。")
    else:
        parts.append("当前缺 runtime items，无法列出该 mod 的物品入口。")

    entry_recipes = [recipe for recipe in matched_recipes if recipe.ingredient_items]
    if entry_recipes:
        recipe = entry_recipes[0]
        result_label = _item_label(index, recipe.result_item) if recipe.result_item else recipe.id
        ingredients = _format_item_list(index, recipe.ingredient_items, limit=8)
        parts.append(f"可作为入口的 runtime 配方样例是 {result_label}，材料包括：{ingredients}。")
    elif matched_recipes:
        parts.append("runtime recipes 只给出了无材料或特殊 serializer 的配方，缺普通制作入口材料。")
    else:
        parts.append("当前缺该 namespace 下物品的 runtime recipe 样例。")

    if quest_matches:
        quest_labels = _unique_strings([match["label"] for match in quest_matches if match.get("label")])
        parts.append(f"任务书覆盖到：{', '.join(quest_labels[:4])}；不是完全无覆盖，但覆盖较少/不完整。")
    else:
        parts.append("当前未在 runtime ftb_quests 中找到这些入口物品的任务引用。")

    special_results = _unique_strings(
        [
            recipe.result_item
            for recipe in matched_recipes
            if recipe.result_item and not recipe.ingredient_items and "special" in recipe.serializer
        ]
    )
    if special_results:
        parts.append(f"{_format_item_list(index, special_results, limit=4)} 只看到特殊/回收类 runtime recipe，不能说成普通合成入口。")
    if usage_recipes:
        use_labels = [_item_label(index, recipe.result_item) for recipe in usage_recipes[:3] if recipe.result_item]
        if use_labels:
            parts.append(f"这些物品还出现在 runtime 用途/回收配方，产出包括：{', '.join(use_labels)}。")
        else:
            parts.append("这些物品还出现在 runtime 用途/回收配方；具体配方 ID 见 source_refs。")
    parts.append(f"可执行入口：JEI 搜 @{matched_mod.mod_id}，优先看 {_format_item_list(index, scoped_items, limit=4)}。")
    return "".join(parts)


def _item_family_summary(
    index: RuntimePackIndex,
    scoped_items: list[str],
    matched_recipes: list[RuntimeRecipe],
    quest_matches: list[Dict[str, str]],
    usage_recipes: list[RuntimeRecipe] | None = None,
) -> str:
    usage_recipes = usage_recipes or []
    parts = [f"已按同族/相关物品匹配：{_format_item_list(index, scoped_items, limit=8)}。"]
    scoped_set = set(scoped_items)
    recipe_results = _unique_strings(
        [recipe.result_item for recipe in matched_recipes if recipe.result_item in scoped_set]
    )
    if recipe_results:
        parts.append(f"runtime recipes 找到这些结果物品的配方：{_format_item_list(index, recipe_results, limit=8)}。")
    else:
        parts.append("当前缺这些同族物品的 runtime recipe。")
    if all(item_id in scoped_set for item_id in ["thermal:upgrade_augment_1", "thermal:upgrade_augment_2", "thermal:upgrade_augment_3"]):
        parts.append(
            "升级顺序按 runtime 配方链核对为 "
            + _format_item_chain(
                index,
                [
                    "thermal:upgrade_augment_1",
                    "thermal:upgrade_augment_2",
                    "thermal:upgrade_augment_3",
                ],
            )
            + "。"
        )
    if quest_matches:
        quest_labels = _unique_strings([match["label"] for match in quest_matches if match.get("label")])
        parts.append(f"runtime quests 也引用了这些物品：{', '.join(quest_labels[:6])}。")
    else:
        parts.append("当前未找到这些物品的 runtime quest 引用。")
    if usage_recipes:
        use_labels = [_item_label(index, recipe.result_item) for recipe in usage_recipes[:4] if recipe.result_item]
        if use_labels:
            parts.append(f"相关用途配方另列为用途证据，不当作直接制作配方；产出包括：{', '.join(use_labels)}。")
        else:
            parts.append("相关用途配方另列为用途证据，不当作直接制作配方；具体配方 ID 见 source_refs。")
    return "".join(parts)


def _fallback_summary(
    question: str,
    index: RuntimePackIndex | None = None,
    matched_item: Optional[str] = None,
    matched_recipes: list[RuntimeRecipe] | None = None,
    quest_matches: list[Dict[str, str]] | None = None,
    progress_scope: ProgressScope | None = None,
    matched_items: list[str] | None = None,
    related_items: list[str] | None = None,
    matched_mod: RuntimeMod | None = None,
    usage_recipes: list[RuntimeRecipe] | None = None,
) -> str:
    index = index or RuntimePackIndex.empty()
    matched_recipes = matched_recipes or []
    quest_matches = quest_matches or []
    usage_recipes = usage_recipes or []
    matched_items = matched_items or ([] if matched_item is None else [matched_item])
    related_items = related_items or []
    scoped_items = _unique_strings([*matched_items, *related_items])
    if matched_mod is not None and _looks_like_mod_level_question(question):
        return _mod_level_summary(index, matched_mod, scoped_items, matched_recipes, quest_matches, usage_recipes)
    if len(scoped_items) > 1 and (matched_recipes or quest_matches):
        return _item_family_summary(index, scoped_items, matched_recipes, quest_matches, usage_recipes)
    if matched_item and matched_recipes:
        ingredients = _ingredient_items(matched_recipes)
        item_label = _item_label(index, matched_item)
        if ingredients and ("材料" in question or "缺" in question):
            return f"服务器 runtime 配方显示 {item_label} 需要这些候选材料：{_format_item_list(index, ingredients, limit=8)}。"
        if quest_matches and ("解锁" in question or "前置" in question or "缺" in question):
            progress = _quest_completion_summary(quest_matches, index, progress_scope)
            suffix = f"；当前进度：{progress}" if progress else ""
            return f"{item_label} 同时出现在服务器 runtime 配方和任务书中；相关任务包括：{quest_matches[0]['label']}{suffix}。"
        recipe_types = sorted({recipe.type for recipe in matched_recipes})
        return f"服务器 runtime dump 中找到 {item_label} 的 {len(matched_recipes)} 条配方，类型包括：{', '.join(recipe_types[:5])}。"
    if matched_item and quest_matches:
        progress = _quest_completion_summary(quest_matches, index, progress_scope)
        item_label = _item_label(index, matched_item)
        if progress:
            return f"runtime 任务/进度中找到 {item_label} 的相关任务：{quest_matches[0]['label']}；当前进度：{progress}。"
        return f"任务书中找到 {item_label} 的相关任务：{quest_matches[0]['label']}；还需要 runtime dump 和玩家/队伍进度确认是否已解锁。"
    if "jei" in question.lower() or "配方" in question:
        if index.recipes:
            tag_note = f"，tags={len(index.tags)}" if index.tags else ""
            return f"Packwise 已接收服务器 runtime recipes（{len(index.recipes)} 条{tag_note}）。回答配方差异时应以服务器 dump 为准，再回看 KubeJS/datapack/static sources。"
        return "配方差异需要服务器 runtime recipes 才能判断；JEI 或网页只能作为线索，不能替代服务器真值。"
    if "下一步" in question or "干什么" in question:
        next_runtime_quests = _next_runtime_quests(index, progress_scope)
        if next_runtime_quests:
            labels = ", ".join(_quest_label(quest) for quest in next_runtime_quests[:3])
            return f"根据 runtime quests/progress，下一步优先检查这些未完成任务：{labels}。"
        if index.advancements or index.recipes:
            return f"已接收 runtime 索引：recipes={len(index.recipes)}，advancements={len(index.advancements)}；下一步仍需要任务和队伍进度来排序。"
        return "当前轻量 harness 还没有完整进度图；建议先完成 runtime dump，再用任务书和 stage 状态计算下一步。"
    return "当前轻量 harness 已接收问题，但需要检索索引和 runtime dump 后才能给出高置信答案。"


def _confidence(
    matched_recipes: list[RuntimeRecipe],
    quest_matches: list[Dict[str, str]],
    index: RuntimePackIndex,
    has_dump: bool,
    progress_scope: ProgressScope | None = None,
) -> str:
    if matched_recipes and quest_matches and _has_progress_state(index, progress_scope):
        return "high"
    if matched_recipes or quest_matches or _next_runtime_quests(index, progress_scope):
        return "medium"
    return "low" if has_dump else "low"


def _runtime_quest_matches_for_item(
    index: RuntimePackIndex,
    item_id: str,
    dump_id: Optional[str],
) -> list[Dict[str, str]]:
    matches: list[Dict[str, str]] = []
    for quest in index.ftb_quests:
        roles = []
        if item_id in quest.task_item_ids:
            roles.append("task")
        if item_id in quest.reward_item_ids:
            roles.append("reward")
        if not roles:
            continue
        path_prefix = f"{dump_id}/ftb_quests" if dump_id else "ftb_quests"
        matches.append(
            {
                "path": f"{path_prefix}#{quest.quest_id}",
                "label": _quest_label(quest),
                "quest_id": quest.quest_id,
                "source": "runtime:ftb_quests",
                "role": ",".join(roles),
            }
        )
    return matches


def _next_runtime_quests(index: RuntimePackIndex, progress_scope: ProgressScope | None = None) -> list[RuntimeQuest]:
    if not index.ftb_quests:
        return []
    completed = _completed_quest_ids(index, progress_scope)
    open_quests = [quest for quest in index.ftb_quests if quest.quest_id not in completed]
    if not open_quests:
        return []
    ready = [
        quest
        for quest in open_quests
        if _quest_dependencies_completed(quest, completed)
    ]
    candidates = ready or open_quests
    return sorted(candidates, key=lambda quest: (quest.chapter_id or "", quest.quest_id))[:5]


def _quest_dependencies_completed(quest: RuntimeQuest, completed: set[str]) -> bool:
    dependencies = quest.quest_dependencies()
    return not dependencies or all(dependency in completed for dependency in dependencies)


def _quest_completion_summary(
    quest_matches: list[Dict[str, str]],
    index: RuntimePackIndex,
    progress_scope: ProgressScope | None = None,
) -> str:
    completed = _completed_quest_ids(index, progress_scope)
    if not completed and not _has_progress_state(index, progress_scope):
        return ""
    labels = []
    for match in quest_matches[:3]:
        quest_id = match.get("quest_id")
        label = match.get("label") or quest_id or "quest"
        state = "已完成" if quest_id in completed else "未完成"
        labels.append(f"{label}={state}")
    return ", ".join(labels)


def _completed_quest_ids(index: RuntimePackIndex, progress_scope: ProgressScope | None = None) -> set[str]:
    completed: set[str] = set()
    player_progress, team_progress, _ = _progress_for_scope(index, progress_scope)
    for progress in [*team_progress, *player_progress]:
        completed.update(progress.completed_quests)
    return completed


def _has_progress_state(index: RuntimePackIndex, progress_scope: ProgressScope | None = None) -> bool:
    player_progress, team_progress, stages = _progress_for_scope(index, progress_scope)
    return bool(team_progress or player_progress or stages)


def _progress_scope(context: Mapping[str, Any]) -> ProgressScope:
    return ProgressScope(
        team_id=_context_str(context, "team_id"),
        player_id=_context_str(context, "player_id") or _context_str(context, "player_uuid"),
        player_name=_context_str(context, "player_name"),
    )


def _progress_for_scope(
    index: RuntimePackIndex,
    progress_scope: ProgressScope | None,
) -> tuple[list[Any], list[Any], list[Any]]:
    if progress_scope is None or not progress_scope.is_scoped():
        return (list(index.player_progress), list(index.team_progress), list(index.stages))

    player_progress = _player_progress_for_scope(index, progress_scope)
    team_ids = {progress_scope.team_id} if progress_scope.team_id else set()
    team_ids.update(progress.team_id for progress in player_progress if progress.team_id)
    team_progress = [
        progress
        for progress in index.team_progress
        if progress.subject_id in team_ids
        or (progress_scope.player_id is not None and progress_scope.player_id in progress.members)
        or (progress_scope.player_name is not None and progress_scope.player_name in progress.members)
    ]
    stages = [
        stage
        for stage in index.stages
        if (progress_scope.player_id is not None and stage.subject_id == progress_scope.player_id)
        or (progress_scope.player_name is not None and stage.player_name == progress_scope.player_name)
        or (
            progress_scope.team_id is not None
            and stage.subject_type == "team"
            and stage.subject_id == progress_scope.team_id
        )
    ]
    return (player_progress, team_progress, stages)


def _player_progress_for_scope(index: RuntimePackIndex, progress_scope: ProgressScope) -> list[Any]:
    return [
        progress
        for progress in index.player_progress
        if (progress_scope.player_id is not None and progress.subject_id == progress_scope.player_id)
        or (progress_scope.player_name is not None and progress.player_name == progress_scope.player_name)
        or (progress_scope.team_id is not None and progress.team_id == progress_scope.team_id)
    ]


def _context_str(context: Mapping[str, Any], key: str) -> str | None:
    value = context.get(key)
    return value if isinstance(value, str) and value else None


def _quest_label(quest: RuntimeQuest) -> str:
    return quest.title or quest.quest_id


def _ingredient_items(recipes: list[RuntimeRecipe]) -> list[str]:
    ingredients = sorted({item for recipe in recipes for item in recipe.ingredient_items})
    return ingredients


def _quest_mentions_item(quest: Mapping[str, Any], item_id: str) -> bool:
    for section_name in ("tasks", "rewards"):
        section = quest.get(section_name)
        if not isinstance(section, list):
            continue
        for entry in section:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("item_id") == item_id:
                return True
    return False


def _new_message_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _duplicate_section_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    return sorted(duplicates)


def _invalid_runtime_content_types(manifest: RuntimeDumpManifest) -> list[str]:
    return [
        f"{section.name}={section.content_type}"
        for section in manifest.sections
        if section.name in RUNTIME_SECTIONS and section.content_type != RUNTIME_DUMP_NDJSON_CONTENT_TYPE
    ]
