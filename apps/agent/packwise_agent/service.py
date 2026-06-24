from __future__ import annotations

import hashlib
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
    RuntimeMod,
    RuntimePackIndex,
    RuntimeQuest,
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
        source_refs = []
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
        matched_item = self._match_item(question, context, index)
        matched_recipes = self._recipes_for_item(matched_item, index) if matched_item else []
        quest_matches = self._quest_matches_for_item(connector_id, matched_item, index, dump_id) if connector_id and matched_item else []
        if dump_id and index.recipes:
            source_refs.append(
                {
                    "kind": "runtime_dump_section",
                    "path": f"{dump_id}/recipes",
                    "label": "Runtime recipes",
                }
            )
        if dump_id and index.tags:
            source_refs.append(
                {
                    "kind": "runtime_dump_section",
                    "path": f"{dump_id}/tags",
                    "label": "Runtime tags",
                }
            )
        if dump_id and index.advancements:
            source_refs.append(
                {
                    "kind": "runtime_dump_section",
                    "path": f"{dump_id}/advancements",
                    "label": "Runtime advancements",
                }
            )
        if dump_id and index.ftb_quests:
            source_refs.append(
                {
                    "kind": "runtime_dump_section",
                    "path": f"{dump_id}/ftb_quests",
                    "label": "Runtime FTB Quests",
                }
            )
        if dump_id and (index.player_progress or index.team_progress):
            source_refs.append(
                {
                    "kind": "runtime_dump_section",
                    "path": f"{dump_id}/progress",
                    "label": "Runtime player/team progress",
                }
            )
        if dump_id and index.stages:
            source_refs.append(
                {
                    "kind": "runtime_dump_section",
                    "path": f"{dump_id}/stages",
                    "label": "Runtime stages",
                }
            )
        for quest in quest_matches[:3]:
            source_refs.append(
                {
                    "kind": "quest",
                    "path": quest["path"],
                    "label": quest["label"],
                }
            )
        for recipe in matched_recipes[:3]:
            source_refs.append(
                {
                    "kind": "recipe",
                    "path": recipe.id,
                    "label": recipe.result_item or recipe.id,
                }
            )

        if not source_refs:
            source_refs.append(
                {
                    "kind": "protocol",
                    "path": "docs/protocol/CONNECTOR_AGENT_PROTOCOL.md",
                    "label": "Packwise protocol draft",
                }
            )

        summary = self._llm_summary(question, context) if self.chat_client else _fallback_summary(question, index, matched_item, matched_recipes, quest_matches, progress_scope)
        next_steps = self._next_steps(question, index, matched_item, matched_recipes, quest_matches, progress_scope)
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

    def _match_item(self, question: str, context: Mapping[str, Any], index: RuntimePackIndex) -> Optional[str]:
        context_item = context.get("item_id")
        if isinstance(context_item, str) and context_item:
            return context_item
        haystack = question.lower()
        candidates = {entry.id for entry in index.items}
        candidates.update(recipe.result_item for recipe in index.recipes if recipe.result_item)
        candidates.update(item_id for quest in index.ftb_quests for item_id in quest.task_item_ids)
        candidates.update(item_id for quest in index.ftb_quests for item_id in quest.reward_item_ids)
        for item_id in sorted(candidates, key=len, reverse=True):
            lowered = item_id.lower()
            path = lowered.split(":", 1)[-1].replace("_", " ")
            if lowered in haystack or path in haystack:
                return item_id
        return None

    def _recipes_for_item(self, item_id: str, index: RuntimePackIndex) -> list[RuntimeRecipe]:
        return [recipe for recipe in index.recipes if recipe.result_item == item_id]

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

    def _next_steps(
        self,
        question: str,
        index: RuntimePackIndex,
        matched_item: Optional[str],
        matched_recipes: list[RuntimeRecipe],
        quest_matches: list[Dict[str, str]] | None = None,
        progress_scope: ProgressScope | None = None,
    ) -> list[str]:
        quest_matches = quest_matches or []
        next_runtime_quests = _next_runtime_quests(index, progress_scope)
        if matched_item and matched_recipes:
            ingredients = _ingredient_items(matched_recipes)
            if ingredients and ("材料" in question or "缺" in question):
                return [
                    f"先核对服务器 runtime 配方材料：{', '.join(ingredients[:8])}。",
                    "再检查这些材料对应的机器链、任务依赖和 stage/player progress；缺口需要用队伍进度确认。",
                ]
            if quest_matches and ("解锁" in question or "前置" in question or "缺" in question):
                return [
                    f"先按任务书定位 {matched_item} 相关任务：{quest_matches[0]['label']}。",
                    "再以服务器 runtime recipes/tags 校验实际制作路径，最后补齐缺失的材料、任务、stage 或机器条件。",
                ]
            return [
                f"以服务器 runtime recipe 为准，先查看 {matched_item} 的 {len(matched_recipes)} 条当前配方。",
                "再把配方输入材料与已完成任务、stage 和机器库存对齐，缺口需要后续 player/team progress dump 判断。",
            ]
        if matched_item and quest_matches:
            progress = _quest_completion_summary(quest_matches, index, progress_scope)
            if progress:
                return [
                    f"先查看 {matched_item} 相关 runtime 任务进度：{progress}。",
                    "再按未完成任务的 dependencies、stage 和 runtime recipes/tags 校验实际解锁条件。",
                ]
            return [
                f"先查看任务书中引用 {matched_item} 的任务：{quest_matches[0]['label']}。",
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

    def _llm_summary(self, question: str, context: Mapping[str, Any]) -> str:
        assert self.chat_client is not None
        prompt = (
            "你是 Packwise 的早期轻量 harness。"
            "只能基于提供的上下文回答；如果缺 runtime dump 或索引，要明确说明低置信。"
            "\n\n问题："
            + question
            + "\n\n上下文："
            + repr(dict(context))
        )
        return self.chat_client.complete(
            [
                ChatMessage(role="system", content="你是 Minecraft 整合包服务器的只读进度助理。"),
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


def _fallback_summary(
    question: str,
    index: RuntimePackIndex | None = None,
    matched_item: Optional[str] = None,
    matched_recipes: list[RuntimeRecipe] | None = None,
    quest_matches: list[Dict[str, str]] | None = None,
    progress_scope: ProgressScope | None = None,
) -> str:
    index = index or RuntimePackIndex.empty()
    matched_recipes = matched_recipes or []
    quest_matches = quest_matches or []
    if matched_item and matched_recipes:
        ingredients = _ingredient_items(matched_recipes)
        if ingredients and ("材料" in question or "缺" in question):
            return f"服务器 runtime 配方显示 {matched_item} 需要这些候选材料：{', '.join(ingredients[:8])}。"
        if quest_matches and ("解锁" in question or "前置" in question or "缺" in question):
            progress = _quest_completion_summary(quest_matches, index, progress_scope)
            suffix = f"；当前进度：{progress}" if progress else ""
            return f"{matched_item} 同时出现在服务器 runtime 配方和任务书中；相关任务包括：{quest_matches[0]['label']}{suffix}。"
        recipe_types = sorted({recipe.type for recipe in matched_recipes})
        return f"服务器 runtime dump 中找到 {matched_item} 的 {len(matched_recipes)} 条配方，类型包括：{', '.join(recipe_types[:5])}。"
    if matched_item and quest_matches:
        progress = _quest_completion_summary(quest_matches, index, progress_scope)
        if progress:
            return f"runtime 任务/进度中找到 {matched_item} 的相关任务：{quest_matches[0]['label']}；当前进度：{progress}。"
        return f"任务书中找到 {matched_item} 的相关任务：{quest_matches[0]['label']}；还需要 runtime dump 和玩家/队伍进度确认是否已解锁。"
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
        if not quest.dependencies or all(dependency in completed for dependency in quest.dependencies)
    ]
    candidates = ready or open_quests
    return sorted(candidates, key=lambda quest: (quest.chapter_id or "", quest.quest_id))[:5]


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
