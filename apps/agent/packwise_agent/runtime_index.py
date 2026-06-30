from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class RuntimeMod:
    mod_id: str
    display_name: str
    version: str
    source: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeMod":
        return cls(
            mod_id=_require_str(payload, "mod_id"),
            display_name=_require_str(payload, "display_name"),
            version=_require_str(payload, "version"),
            source=_require_str(payload, "source"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "mod_id": self.mod_id,
            "display_name": self.display_name,
            "version": self.version,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeRegistryEntry:
    id: str
    registry: str
    namespace: str
    path: str
    source: str
    translation_key: Optional[str]
    display_name: Optional[str]
    translated_name: Optional[str]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeRegistryEntry":
        item_id = _require_str(payload, "id")
        namespace, _, path = item_id.partition(":")
        return cls(
            id=item_id,
            registry=_optional_str(payload, "registry") or "unknown",
            namespace=_optional_str(payload, "namespace") or namespace,
            path=_optional_str(payload, "path") or path or item_id,
            source=_optional_str(payload, "source") or "runtime",
            translation_key=_optional_str(payload, "translation_key"),
            display_name=_optional_str(payload, "display_name"),
            translated_name=_optional_str(payload, "translated_name"),
        )

    def to_dict(self) -> Dict[str, str]:
        payload = {
            "id": self.id,
            "registry": self.registry,
            "namespace": self.namespace,
            "path": self.path,
            "source": self.source,
        }
        if self.translation_key:
            payload["translation_key"] = self.translation_key
        if self.display_name:
            payload["display_name"] = self.display_name
        if self.translated_name:
            payload["translated_name"] = self.translated_name
        return payload


@dataclass(frozen=True)
class RuntimeTag:
    registry: str
    tag: str
    entry_count: int
    entries: List[str]
    source: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeTag":
        entry_count = payload.get("entry_count")
        entries = payload.get("entries")
        if entries is None:
            entries = []
        if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
            raise ValueError("entries must be a string list")
        if entry_count is None:
            entry_count = len(entries)
        if not isinstance(entry_count, int) or entry_count < 0:
            raise ValueError("entry_count must be a non-negative integer")
        return cls(
            registry=_require_str(payload, "registry"),
            tag=_require_str(payload, "tag"),
            entry_count=entry_count,
            entries=list(entries),
            source=_optional_str(payload, "source") or "runtime",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registry": self.registry,
            "tag": self.tag,
            "entry_count": self.entry_count,
            "entries": list(self.entries),
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeRecipe:
    id: str
    type: str
    serializer: str
    result_item: Optional[str]
    result_count: int
    ingredient_items: List[str]
    ingredient_slots: List[Dict[str, Any]]
    source: str
    width: Optional[int]
    height: Optional[int]
    pattern: List[str]
    raw_recipe: Optional[Dict[str, Any]]
    result_nbt: Optional[str]
    result_display_name: Optional[str]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeRecipe":
        result_count = payload.get("result_count", 0)
        if not isinstance(result_count, int) or result_count < 0:
            raise ValueError("result_count must be a non-negative integer")
        result_item = _optional_str(payload, "result_item")
        return cls(
            id=_require_str(payload, "id"),
            type=_optional_str(payload, "type") or "unknown",
            serializer=_optional_str(payload, "serializer") or "unknown",
            result_item=result_item or None,
            result_count=result_count,
            ingredient_items=_optional_str_list(payload, "ingredient_items"),
            ingredient_slots=_optional_object_list(payload, "ingredient_slots"),
            source=_optional_str(payload, "source") or "runtime",
            width=_optional_non_negative_int(payload, "width"),
            height=_optional_non_negative_int(payload, "height"),
            pattern=_optional_str_list(payload, "pattern"),
            raw_recipe=_optional_mapping(payload, "raw_recipe"),
            result_nbt=_optional_str(payload, "result_nbt"),
            result_display_name=_optional_str(payload, "result_display_name"),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "serializer": self.serializer,
            "result_item": self.result_item,
            "result_count": self.result_count,
            "ingredient_items": list(self.ingredient_items),
            "source": self.source,
        }
        if self.ingredient_slots:
            payload["ingredient_slots"] = [dict(slot) for slot in self.ingredient_slots]
        if self.width is not None:
            payload["width"] = self.width
        if self.height is not None:
            payload["height"] = self.height
        if self.pattern:
            payload["pattern"] = list(self.pattern)
        if self.raw_recipe is not None:
            payload["raw_recipe"] = dict(self.raw_recipe)
        if self.result_nbt:
            payload["result_nbt"] = self.result_nbt
        if self.result_display_name:
            payload["result_display_name"] = self.result_display_name
        return payload


@dataclass(frozen=True)
class RuntimePotionEffect:
    effect_id: str
    duration: int
    amplifier: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimePotionEffect":
        duration = payload.get("duration", 0)
        amplifier = payload.get("amplifier", 0)
        if not isinstance(duration, int):
            raise ValueError("duration must be an integer")
        if not isinstance(amplifier, int) or amplifier < 0:
            raise ValueError("amplifier must be a non-negative integer")
        return cls(
            effect_id=_optional_str(payload, "effect_id") or _require_str(payload, "id"),
            duration=duration,
            amplifier=amplifier,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "duration": self.duration,
            "amplifier": self.amplifier,
        }


@dataclass(frozen=True)
class RuntimePotion:
    id: str
    display_name: Optional[str]
    translation_key: Optional[str]
    effects: List[RuntimePotionEffect]
    source: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimePotion":
        return cls(
            id=_require_str(payload, "id"),
            display_name=_optional_str(payload, "display_name"),
            translation_key=_optional_str(payload, "translation_key"),
            effects=[
                RuntimePotionEffect.from_dict(effect)
                for effect in _optional_object_list(payload, "effects")
            ],
            source=_optional_str(payload, "source") or "runtime",
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "effects": [effect.to_dict() for effect in self.effects],
            "source": self.source,
        }
        if self.display_name:
            payload["display_name"] = self.display_name
        if self.translation_key:
            payload["translation_key"] = self.translation_key
        return payload


@dataclass(frozen=True)
class RuntimeEffectAttributeModifier:
    attribute_id: str
    amount: float
    operation: str
    name: Optional[str]
    uuid: Optional[str]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeEffectAttributeModifier":
        amount = payload.get("amount", 0.0)
        if not isinstance(amount, (int, float)):
            raise ValueError("amount must be a number")
        return cls(
            attribute_id=_optional_str(payload, "attribute_id") or _require_str(payload, "attribute"),
            amount=float(amount),
            operation=_optional_str(payload, "operation") or "unknown",
            name=_optional_str(payload, "name"),
            uuid=_optional_str(payload, "uuid"),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "attribute_id": self.attribute_id,
            "amount": self.amount,
            "operation": self.operation,
        }
        if self.name:
            payload["name"] = self.name
        if self.uuid:
            payload["uuid"] = self.uuid
        return payload


@dataclass(frozen=True)
class RuntimeMobEffect:
    id: str
    display_name: Optional[str]
    translation_key: Optional[str]
    description: Optional[str]
    attribute_modifiers: List[RuntimeEffectAttributeModifier]
    source: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeMobEffect":
        return cls(
            id=_require_str(payload, "id"),
            display_name=_optional_str(payload, "display_name"),
            translation_key=_optional_str(payload, "translation_key"),
            description=_optional_str(payload, "description"),
            attribute_modifiers=[
                RuntimeEffectAttributeModifier.from_dict(modifier)
                for modifier in _optional_object_list(payload, "attribute_modifiers")
            ],
            source=_optional_str(payload, "source") or "runtime",
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "attribute_modifiers": [modifier.to_dict() for modifier in self.attribute_modifiers],
            "source": self.source,
        }
        if self.display_name:
            payload["display_name"] = self.display_name
        if self.translation_key:
            payload["translation_key"] = self.translation_key
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class RuntimeAdvancement:
    id: str
    source: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeAdvancement":
        return cls(
            id=_require_str(payload, "id"),
            source=_optional_str(payload, "source") or "runtime",
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeQuest:
    quest_id: str
    chapter_id: Optional[str]
    title: Optional[str]
    dependencies: List[str]
    dependency_types: Dict[str, str]
    task_item_ids: List[str]
    reward_item_ids: List[str]
    source: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeQuest":
        return cls(
            quest_id=_require_str(payload, "quest_id"),
            chapter_id=_optional_str(payload, "chapter_id"),
            title=_optional_str(payload, "title"),
            dependencies=_optional_str_list(payload, "dependencies"),
            dependency_types=_optional_str_dict(payload, "dependency_types"),
            task_item_ids=_optional_str_list(payload, "task_item_ids"),
            reward_item_ids=_optional_str_list(payload, "reward_item_ids"),
            source=_optional_str(payload, "source") or "runtime",
        )

    def quest_dependencies(self) -> List[str]:
        if not self.dependency_types:
            return list(self.dependencies)
        return [
            dependency
            for dependency in self.dependencies
            if self.dependency_types.get(dependency) == "quest"
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "chapter_id": self.chapter_id,
            "title": self.title,
            "dependencies": list(self.dependencies),
            "dependency_types": dict(self.dependency_types),
            "task_item_ids": list(self.task_item_ids),
            "reward_item_ids": list(self.reward_item_ids),
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeProgress:
    subject_type: str
    subject_id: str
    completed_quests: List[str]
    completed_advancements: List[str]
    stages: List[str]
    source: str
    player_name: Optional[str]
    team_id: Optional[str]
    team_name: Optional[str]
    members: List[str]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeProgress":
        return cls(
            subject_type=_require_str(payload, "subject_type"),
            subject_id=_require_str(payload, "subject_id"),
            completed_quests=_optional_str_list(payload, "completed_quests"),
            completed_advancements=_optional_str_list(payload, "completed_advancements"),
            stages=_optional_str_list(payload, "stages"),
            source=_optional_str(payload, "source") or "runtime",
            player_name=_optional_str(payload, "player_name"),
            team_id=_optional_str(payload, "team_id"),
            team_name=_optional_str(payload, "team_name"),
            members=_optional_str_list(payload, "members"),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "completed_quests": list(self.completed_quests),
            "completed_advancements": list(self.completed_advancements),
            "stages": list(self.stages),
            "source": self.source,
        }
        if self.player_name is not None:
            payload["player_name"] = self.player_name
        if self.team_id is not None:
            payload["team_id"] = self.team_id
        if self.team_name is not None:
            payload["team_name"] = self.team_name
        if self.members:
            payload["members"] = list(self.members)
        return payload


@dataclass(frozen=True)
class RuntimeStage:
    subject_type: str
    subject_id: str
    stage: str
    active: bool
    source: str
    player_name: Optional[str]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeStage":
        active = payload.get("active", True)
        if not isinstance(active, bool):
            raise ValueError("active must be a boolean")
        return cls(
            subject_type=_require_str(payload, "subject_type"),
            subject_id=_require_str(payload, "subject_id"),
            stage=_require_str(payload, "stage"),
            active=active,
            source=_optional_str(payload, "source") or "runtime",
            player_name=_optional_str(payload, "player_name"),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "stage": self.stage,
            "active": self.active,
            "source": self.source,
        }
        if self.player_name is not None:
            payload["player_name"] = self.player_name
        return payload


@dataclass(frozen=True)
class RuntimePackIndex:
    mods: List[RuntimeMod]
    items: List[RuntimeRegistryEntry]
    blocks: List[RuntimeRegistryEntry]
    fluids: List[RuntimeRegistryEntry]
    tags: List[RuntimeTag]
    recipes: List[RuntimeRecipe]
    potions: List[RuntimePotion]
    mob_effects: List[RuntimeMobEffect]
    advancements: List[RuntimeAdvancement]
    ftb_quests: List[RuntimeQuest]
    player_progress: List[RuntimeProgress]
    team_progress: List[RuntimeProgress]
    stages: List[RuntimeStage]

    @classmethod
    def empty(cls) -> "RuntimePackIndex":
        return cls(
            mods=[],
            items=[],
            blocks=[],
            fluids=[],
            tags=[],
            recipes=[],
            potions=[],
            mob_effects=[],
            advancements=[],
            ftb_quests=[],
            player_progress=[],
            team_progress=[],
            stages=[],
        )

    def with_section(self, section_name: str, body: str) -> "RuntimePackIndex":
        if section_name == "mods":
            return replace(self, mods=parse_mods_ndjson(body))
        if section_name == "items":
            return replace(self, items=parse_registry_entries_ndjson(body))
        if section_name == "blocks":
            return replace(self, blocks=parse_registry_entries_ndjson(body))
        if section_name == "fluids":
            return replace(self, fluids=parse_registry_entries_ndjson(body))
        if section_name == "tags":
            return replace(self, tags=parse_tags_ndjson(body))
        if section_name == "recipes":
            return replace(self, recipes=parse_recipes_ndjson(body))
        if section_name == "potions":
            return replace(self, potions=parse_potions_ndjson(body))
        if section_name == "mob_effects":
            return replace(self, mob_effects=parse_mob_effects_ndjson(body))
        if section_name == "advancements":
            return replace(self, advancements=parse_advancements_ndjson(body))
        if section_name == "ftb_quests":
            return replace(self, ftb_quests=parse_ftb_quests_ndjson(body))
        if section_name == "player_progress":
            return replace(self, player_progress=parse_progress_ndjson(body, "player_progress"))
        if section_name == "team_progress":
            return replace(self, team_progress=parse_progress_ndjson(body, "team_progress"))
        if section_name == "stages":
            return replace(self, stages=parse_stages_ndjson(body))
        return self

    def summary(self) -> Dict[str, int]:
        return {
            "mods": len(self.mods),
            "items": len(self.items),
            "blocks": len(self.blocks),
            "fluids": len(self.fluids),
            "tags": len(self.tags),
            "recipes": len(self.recipes),
            "potions": len(self.potions),
            "mob_effects": len(self.mob_effects),
            "advancements": len(self.advancements),
            "ftb_quests": len(self.ftb_quests),
            "player_progress": len(self.player_progress),
            "team_progress": len(self.team_progress),
            "stages": len(self.stages),
        }


def parse_mods_ndjson(body: str) -> List[RuntimeMod]:
    mods = [RuntimeMod.from_dict(payload) for payload in _parse_ndjson_objects(body, "mods")]
    return sorted(mods, key=lambda mod: mod.mod_id)


def parse_registry_entries_ndjson(body: str) -> List[RuntimeRegistryEntry]:
    entries = [RuntimeRegistryEntry.from_dict(payload) for payload in _parse_ndjson_objects(body, "registry")]
    return sorted(entries, key=lambda entry: entry.id)


def parse_tags_ndjson(body: str) -> List[RuntimeTag]:
    tags = [RuntimeTag.from_dict(payload) for payload in _parse_ndjson_objects(body, "tags")]
    return sorted(tags, key=lambda tag: (tag.registry, tag.tag))


def parse_recipes_ndjson(body: str) -> List[RuntimeRecipe]:
    recipes = [RuntimeRecipe.from_dict(payload) for payload in _parse_ndjson_objects(body, "recipes")]
    return sorted(recipes, key=lambda recipe: recipe.id)


def parse_potions_ndjson(body: str) -> List[RuntimePotion]:
    potions = [RuntimePotion.from_dict(payload) for payload in _parse_ndjson_objects(body, "potions")]
    return sorted(potions, key=lambda potion: potion.id)


def parse_mob_effects_ndjson(body: str) -> List[RuntimeMobEffect]:
    effects = [RuntimeMobEffect.from_dict(payload) for payload in _parse_ndjson_objects(body, "mob_effects")]
    return sorted(effects, key=lambda effect: effect.id)


def parse_advancements_ndjson(body: str) -> List[RuntimeAdvancement]:
    advancements = [RuntimeAdvancement.from_dict(payload) for payload in _parse_ndjson_objects(body, "advancements")]
    return sorted(advancements, key=lambda advancement: advancement.id)


def parse_ftb_quests_ndjson(body: str) -> List[RuntimeQuest]:
    quests = [RuntimeQuest.from_dict(payload) for payload in _parse_ndjson_objects(body, "ftb_quests")]
    return sorted(quests, key=lambda quest: quest.quest_id)


def parse_progress_ndjson(body: str, section_name: str) -> List[RuntimeProgress]:
    progress = [RuntimeProgress.from_dict(payload) for payload in _parse_ndjson_objects(body, section_name)]
    return sorted(progress, key=lambda item: (item.subject_type, item.subject_id))


def parse_stages_ndjson(body: str) -> List[RuntimeStage]:
    stages = [RuntimeStage.from_dict(payload) for payload in _parse_ndjson_objects(body, "stages")]
    return sorted(stages, key=lambda item: (item.subject_type, item.subject_id, item.stage))


def runtime_consistency_errors(runtime_index: RuntimePackIndex) -> List[str]:
    errors: List[str] = []
    item_ids = {entry.id for entry in runtime_index.items}
    block_ids = {entry.id for entry in runtime_index.blocks}
    fluid_ids = {entry.id for entry in runtime_index.fluids}
    errors.extend(_duplicate_value_errors("items", [entry.id for entry in runtime_index.items]))
    errors.extend(_duplicate_value_errors("blocks", [entry.id for entry in runtime_index.blocks]))
    errors.extend(_duplicate_value_errors("fluids", [entry.id for entry in runtime_index.fluids]))
    errors.extend(_duplicate_value_errors("recipes", [recipe.id for recipe in runtime_index.recipes]))
    errors.extend(_duplicate_value_errors("potions", [potion.id for potion in runtime_index.potions]))
    errors.extend(_duplicate_value_errors("mob_effects", [effect.id for effect in runtime_index.mob_effects]))
    errors.extend(_duplicate_value_errors("advancements", [advancement.id for advancement in runtime_index.advancements]))
    errors.extend(_duplicate_value_errors("tags", [f"{tag.registry}:{tag.tag}" for tag in runtime_index.tags]))
    errors.extend(_duplicate_value_errors("ftb_quests", [quest.quest_id for quest in runtime_index.ftb_quests]))
    errors.extend(_duplicate_value_errors("player_progress", [f"{progress.subject_type}:{progress.subject_id}" for progress in runtime_index.player_progress]))
    errors.extend(_duplicate_value_errors("team_progress", [f"{progress.subject_type}:{progress.subject_id}" for progress in runtime_index.team_progress]))
    errors.extend(_duplicate_value_errors("stages", [f"{stage.subject_type}:{stage.subject_id}:{stage.stage}" for stage in runtime_index.stages]))
    if item_ids:
        missing_results = sorted(
            {
                recipe.result_item
                for recipe in runtime_index.recipes
                if recipe.result_item and recipe.result_item not in item_ids
            }
        )
        if missing_results:
            errors.append("Recipe result items missing from items registry: " + ", ".join(missing_results[:20]))
        missing_ingredients = sorted(
            {
                item_id
                for recipe in runtime_index.recipes
                for item_id in recipe.ingredient_items
                if item_id not in item_ids
            }
        )
        if missing_ingredients:
            errors.append("Recipe ingredient items missing from items registry: " + ", ".join(missing_ingredients[:20]))
        missing_quest_task_items = sorted(
            {
                item_id
                for quest in runtime_index.ftb_quests
                for item_id in quest.task_item_ids
                if item_id not in item_ids
            }
        )
        if missing_quest_task_items:
            errors.append("FTB quest task items missing from items registry: " + ", ".join(missing_quest_task_items[:20]))
        missing_quest_reward_items = sorted(
            {
                item_id
                for quest in runtime_index.ftb_quests
                for item_id in quest.reward_item_ids
                if item_id not in item_ids
            }
        )
        if missing_quest_reward_items:
            errors.append("FTB quest reward items missing from items registry: " + ", ".join(missing_quest_reward_items[:20]))
    effect_ids = {effect.id for effect in runtime_index.mob_effects}
    if effect_ids:
        missing_potion_effects = sorted(
            {
                potion_effect.effect_id
                for potion in runtime_index.potions
                for potion_effect in potion.effects
                if potion_effect.effect_id not in effect_ids
            }
        )
        if missing_potion_effects:
            errors.append("Potion effects missing from mob_effects: " + ", ".join(missing_potion_effects[:20]))
    quest_ids = {quest.quest_id for quest in runtime_index.ftb_quests}
    if quest_ids:
        missing_dependencies = sorted(
            {
                dependency
                for quest in runtime_index.ftb_quests
                for dependency in quest.quest_dependencies()
                if dependency not in quest_ids
            }
        )
        if missing_dependencies:
            errors.append("FTB quest dependencies missing from ftb_quests: " + ", ".join(missing_dependencies[:20]))
        missing_player_completed_quests = sorted(
            {
                quest_id
                for progress in runtime_index.player_progress
                for quest_id in progress.completed_quests
                if quest_id not in quest_ids
            }
        )
        if missing_player_completed_quests:
            errors.append(
                "Player progress completed quests missing from ftb_quests: "
                + ", ".join(missing_player_completed_quests[:20])
            )
        missing_team_completed_quests = sorted(
            {
                quest_id
                for progress in runtime_index.team_progress
                for quest_id in progress.completed_quests
                if quest_id not in quest_ids
            }
        )
        if missing_team_completed_quests:
            errors.append(
                "Team progress completed quests missing from ftb_quests: "
                + ", ".join(missing_team_completed_quests[:20])
            )
    stage_keys = {(stage.subject_type, stage.subject_id, stage.stage) for stage in runtime_index.stages}
    if stage_keys:
        missing_player_progress_stages = sorted(
            {
                f"{progress.subject_id}:{stage}"
                for progress in runtime_index.player_progress
                for stage in progress.stages
                if ("player", progress.subject_id, stage) not in stage_keys
            }
        )
        if missing_player_progress_stages:
            errors.append(
                "Player progress stages missing from stages section: "
                + ", ".join(missing_player_progress_stages[:20])
            )
    tag_registries = {
        "item": item_ids,
        "block": block_ids,
        "fluid": fluid_ids,
    }
    for tag in runtime_index.tags:
        if tag.entry_count != len(tag.entries):
            errors.append(
                f"Tag {tag.registry}:{tag.tag} entry_count mismatch: "
                f"expected {tag.entry_count}, got {len(tag.entries)} entries"
            )
        registry_ids = tag_registries.get(tag.registry)
        if not registry_ids:
            continue
        missing_entries = sorted({entry for entry in tag.entries if entry not in registry_ids})
        if missing_entries:
            errors.append(
                f"Tag {tag.registry}:{tag.tag} entries missing from {tag.registry} registry: "
                + ", ".join(missing_entries[:20])
            )
    return errors


def _parse_ndjson_objects(body: str, section_name: str) -> List[Mapping[str, Any]]:
    objects: List[Mapping[str, Any]] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{section_name} line {line_number} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{section_name} line {line_number} must be a JSON object")
        objects.append(payload)
    return objects


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_str_list(payload: Mapping[str, Any], key: str) -> List[str]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a string list")
    return list(value)


def _optional_str_dict(payload: Mapping[str, Any], key: str) -> Dict[str, str]:
    value = payload.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(item_key, str) and isinstance(item_value, str)
        for item_key, item_value in value.items()
    ):
        raise ValueError(f"{key} must be a string dictionary")
    return dict(value)


def _optional_mapping(payload: Mapping[str, Any], key: str) -> Dict[str, Any] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return dict(value)


def _optional_object_list(payload: Mapping[str, Any], key: str) -> List[Dict[str, Any]]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be an object list")
    return [dict(item) for item in value]


def _optional_non_negative_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _duplicate_value_errors(section_name: str, values: List[str]) -> List[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if not duplicates:
        return []
    return [f"Duplicate runtime {section_name}: " + ", ".join(sorted(duplicates)[:20])]
