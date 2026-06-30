package dev.packwise.connector.forge;

import com.mojang.datafixers.util.Pair;
import com.mojang.logging.LogUtils;
import dev.packwise.connector.protocol.JsonText;
import dev.packwise.connector.protocol.ModsSectionDumper;
import dev.packwise.connector.protocol.NdjsonSectionDumper;
import dev.packwise.connector.protocol.RuntimeDumpContent;
import dev.packwise.connector.protocol.RuntimeSectionNames;
import net.minecraft.advancements.Advancement;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.tags.TagKey;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.ai.attributes.Attribute;
import net.minecraft.world.entity.ai.attributes.AttributeModifier;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.alchemy.Potion;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.ShapedRecipe;
import org.slf4j.Logger;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

public final class ForgeRuntimeDumpCollector {
    private static final Logger LOGGER = LogUtils.getLogger();

    private ForgeRuntimeDumpCollector() {
    }

    public static List<RuntimeDumpContent> collect(MinecraftServer server) {
        List<RuntimeDumpContent> contents = new ArrayList<>();
        contents.add(ModsSectionDumper.dump(ForgeModSnapshots.collectLoadedMods()));
        contents.add(dumpRegistry(RuntimeSectionNames.ITEMS, "item", BuiltInRegistries.ITEM));
        contents.add(dumpRegistry(RuntimeSectionNames.BLOCKS, "block", BuiltInRegistries.BLOCK));
        contents.add(dumpRegistry(RuntimeSectionNames.FLUIDS, "fluid", BuiltInRegistries.FLUID));
        contents.add(dumpTags());
        contents.add(dumpRecipes(server));
        contents.add(dumpPotions());
        contents.add(dumpMobEffects());
        contents.add(dumpAdvancements(server));
        contents.addAll(ForgeOptionalRuntimeDumpCollector.collect(server));
        return List.copyOf(contents);
    }

    private static <T> RuntimeDumpContent dumpRegistry(String sectionName, String registryName, Registry<T> registry) {
        List<String> lines = registry.keySet().stream()
                .sorted(Comparator.comparing(ResourceLocation::toString))
                .map(id -> registryLine(registryName, registry, id))
                .toList();
        return NdjsonSectionDumper.dump(sectionName, lines);
    }

    private static <T> String registryLine(String registryName, Registry<T> registry, ResourceLocation id) {
        T value = registry.get(id);
        StringBuilder json = new StringBuilder();
        json.append("{")
                .append(field("id", id.toString())).append(",")
                .append(field("registry", registryName)).append(",")
                .append(field("namespace", id.getNamespace())).append(",")
                .append(field("path", id.getPath())).append(",")
                .append(field("source", "runtime:built_in_registry"));
        if ("item".equals(registryName) && value instanceof Item item) {
            appendItemNameFields(json, item);
        }
        json.append("}");
        return json.toString();
    }

    private static void appendItemNameFields(StringBuilder json, Item item) {
        String translationKey = item.getDescriptionId();
        if (!translationKey.isBlank()) {
            json.append(",").append(field("translation_key", translationKey));
        }
        String displayName = itemDisplayName(item, translationKey);
        if (!displayName.isBlank()) {
            json.append(",").append(field("display_name", displayName));
        }
    }

    private static String itemDisplayName(Item item, String translationKey) {
        try {
            String displayName = new ItemStack(item).getHoverName().getString();
            if (displayName.isBlank() || displayName.equals(translationKey)) {
                return "";
            }
            return displayName;
        } catch (RuntimeException error) {
            LOGGER.debug("Packwise skipped item display name for {}: {}", translationKey, error.toString());
            return "";
        }
    }

    private static RuntimeDumpContent dumpTags() {
        List<String> lines = new ArrayList<>();
        appendTags(lines, "item", BuiltInRegistries.ITEM);
        appendTags(lines, "block", BuiltInRegistries.BLOCK);
        appendTags(lines, "fluid", BuiltInRegistries.FLUID);
        lines.sort(String::compareTo);
        return NdjsonSectionDumper.dump(RuntimeSectionNames.TAGS, lines);
    }

    private static <T> void appendTags(List<String> lines, String registryName, Registry<T> registry) {
        registry.getTags().forEach(pair -> lines.add(tagLine(registryName, registry, pair)));
    }

    private static <T> String tagLine(String registryName, Registry<T> registry, Pair<TagKey<T>, HolderSet.Named<T>> pair) {
        TagKey<T> tag = pair.getFirst();
        List<String> entries = pair.getSecond().stream()
                .map(Holder::value)
                .map(registry::getKey)
                .filter(id -> id != null)
                .map(ResourceLocation::toString)
                .sorted()
                .toList();
        return "{"
                + field("registry", registryName) + ","
                + field("tag", tag.location().toString()) + ","
                + "\"entry_count\":" + entries.size() + ","
                + stringArrayField("entries", entries) + ","
                + field("source", "runtime:registry_tags")
                + "}";
    }

    private static RuntimeDumpContent dumpRecipes(MinecraftServer server) {
        List<String> lines = new ArrayList<>();
        int skipped = 0;
        List<ResourceLocation> recipeIds = server.getRecipeManager().getRecipeIds()
                .sorted(Comparator.comparing(ResourceLocation::toString))
                .toList();
        for (ResourceLocation recipeId : recipeIds) {
            try {
                Optional<? extends Recipe<?>> recipe = server.getRecipeManager().byKey(recipeId);
                if (recipe.isPresent()) {
                    lines.add(recipeLine(server, recipeId, recipe.get()));
                }
            } catch (RuntimeException error) {
                skipped++;
                LOGGER.warn("Packwise skipped recipe {} while dumping runtime recipes: {}", recipeId, error.toString());
            }
        }
        if (skipped > 0) {
            LOGGER.warn("Packwise skipped {} recipe(s) while dumping runtime recipes; remaining recipes will still be written", skipped);
        }
        lines.sort(String::compareTo);
        return NdjsonSectionDumper.dump(RuntimeSectionNames.RECIPES, lines);
    }

    private static String recipeLine(MinecraftServer server, ResourceLocation recipeId, Recipe<?> recipe) {
        ResourceLocation recipeType = BuiltInRegistries.RECIPE_TYPE.getKey(recipe.getType());
        ResourceLocation serializer = BuiltInRegistries.RECIPE_SERIALIZER.getKey(recipe.getSerializer());
        ItemStack result = recipe.getResultItem(server.registryAccess());
        ResourceLocation resultItem = result.isEmpty() ? null : BuiltInRegistries.ITEM.getKey(result.getItem());
        StringBuilder json = new StringBuilder();
        json.append("{")
                .append(field("id", recipeId.toString())).append(",")
                .append(field("type", stringValue(recipeType))).append(",")
                .append(field("serializer", stringValue(serializer))).append(",")
                .append(field("result_item", stringValue(resultItem))).append(",")
                .append("\"result_count\":").append(result.isEmpty() ? 0 : result.getCount()).append(",")
                .append(stringArrayField("ingredient_items", ingredientItemIds(recipe))).append(",")
                .append(ingredientSlotsField(recipe)).append(",");
        if (recipe instanceof ShapedRecipe shapedRecipe) {
            json.append("\"width\":").append(shapedRecipe.getWidth()).append(",");
            json.append("\"height\":").append(shapedRecipe.getHeight()).append(",");
        }
        if (!result.isEmpty() && result.hasTag()) {
            json.append(field("result_nbt", result.getTag().toString())).append(",");
        }
        if (!result.isEmpty()) {
            String resultDisplayName = result.getHoverName().getString();
            if (!resultDisplayName.isBlank()) {
                json.append(field("result_display_name", resultDisplayName)).append(",");
            }
        }
        json.append(field("source", "runtime:recipe_manager")).append("}");
        return json.toString();
    }

    private static List<String> ingredientItemIds(Recipe<?> recipe) {
        Set<String> ids = new TreeSet<>();
        for (Ingredient ingredient : recipe.getIngredients()) {
            for (ItemStack stack : ingredient.getItems()) {
                if (stack.isEmpty()) {
                    continue;
                }
                ResourceLocation id = BuiltInRegistries.ITEM.getKey(stack.getItem());
                if (id != null) {
                    ids.add(id.toString());
                }
            }
        }
        return List.copyOf(ids);
    }

    private static String ingredientSlotsField(Recipe<?> recipe) {
        StringBuilder json = new StringBuilder();
        json.append("\"ingredient_slots\":[");
        List<Ingredient> ingredients = recipe.getIngredients();
        for (int slot = 0; slot < ingredients.size(); slot++) {
            if (slot > 0) {
                json.append(',');
            }
            Ingredient ingredient = ingredients.get(slot);
            List<String> itemIds = ingredientItemIds(ingredient);
            json.append("{\"slot\":").append(slot).append(",");
            json.append("\"empty\":").append(ingredient.isEmpty()).append(",");
            json.append(stringArrayField("item_ids", itemIds)).append(",");
            json.append(ingredientCandidatesField(ingredient));
            json.append("}");
        }
        json.append(']');
        return json.toString();
    }

    private static List<String> ingredientItemIds(Ingredient ingredient) {
        Set<String> ids = new TreeSet<>();
        for (ItemStack stack : ingredient.getItems()) {
            if (stack.isEmpty()) {
                continue;
            }
            ResourceLocation id = BuiltInRegistries.ITEM.getKey(stack.getItem());
            if (id != null) {
                ids.add(id.toString());
            }
        }
        return List.copyOf(ids);
    }

    private static String ingredientCandidatesField(Ingredient ingredient) {
        StringBuilder json = new StringBuilder();
        json.append("\"candidates\":[");
        ItemStack[] stacks = ingredient.getItems();
        for (int index = 0; index < stacks.length; index++) {
            if (index > 0) {
                json.append(',');
            }
            json.append(itemStackCandidate(stacks[index]));
        }
        json.append(']');
        return json.toString();
    }

    private static String itemStackCandidate(ItemStack stack) {
        ResourceLocation itemId = stack.isEmpty() ? null : BuiltInRegistries.ITEM.getKey(stack.getItem());
        StringBuilder json = new StringBuilder();
        json.append("{")
                .append(field("item_id", stringValue(itemId))).append(",")
                .append("\"count\":").append(stack.isEmpty() ? 0 : stack.getCount());
        if (!stack.isEmpty() && stack.hasTag()) {
            json.append(",").append(field("nbt", stack.getTag().toString()));
        }
        if (!stack.isEmpty()) {
            String displayName = stack.getHoverName().getString();
            if (!displayName.isBlank()) {
                json.append(",").append(field("display_name", displayName));
            }
        }
        json.append("}");
        return json.toString();
    }

    private static RuntimeDumpContent dumpPotions() {
        List<String> lines = BuiltInRegistries.POTION.keySet().stream()
                .sorted(Comparator.comparing(ResourceLocation::toString))
                .map(id -> potionLine(id, BuiltInRegistries.POTION.get(id)))
                .toList();
        return NdjsonSectionDumper.dump(RuntimeSectionNames.POTIONS, lines);
    }

    private static String potionLine(ResourceLocation id, Potion potion) {
        String translationKey = potion.getName("item.minecraft.potion.effect.");
        String displayName = net.minecraft.network.chat.Component.translatable(translationKey).getString();
        StringBuilder json = new StringBuilder();
        json.append("{")
                .append(field("id", id.toString())).append(",")
                .append(field("translation_key", translationKey)).append(",");
        if (!displayName.isBlank() && !displayName.equals(translationKey)) {
            json.append(field("display_name", displayName)).append(",");
        }
        json.append("\"effects\":[");
        List<MobEffectInstance> effects = potion.getEffects();
        for (int index = 0; index < effects.size(); index++) {
            if (index > 0) {
                json.append(',');
            }
            MobEffectInstance effectInstance = effects.get(index);
            ResourceLocation effectId = BuiltInRegistries.MOB_EFFECT.getKey(effectInstance.getEffect());
            json.append("{")
                    .append(field("effect_id", stringValue(effectId))).append(",")
                    .append("\"duration\":").append(effectInstance.getDuration()).append(",")
                    .append("\"amplifier\":").append(effectInstance.getAmplifier())
                    .append("}");
        }
        json.append("],").append(field("source", "runtime:potion_registry")).append("}");
        return json.toString();
    }

    private static RuntimeDumpContent dumpMobEffects() {
        List<String> lines = BuiltInRegistries.MOB_EFFECT.keySet().stream()
                .sorted(Comparator.comparing(ResourceLocation::toString))
                .map(id -> mobEffectLine(id, BuiltInRegistries.MOB_EFFECT.get(id)))
                .toList();
        return NdjsonSectionDumper.dump(RuntimeSectionNames.MOB_EFFECTS, lines);
    }

    private static String mobEffectLine(ResourceLocation id, MobEffect effect) {
        String translationKey = effect.getDescriptionId();
        String displayName = effect.getDisplayName().getString();
        StringBuilder json = new StringBuilder();
        json.append("{")
                .append(field("id", id.toString())).append(",")
                .append(field("translation_key", translationKey)).append(",")
                .append(field("description", translationKey)).append(",");
        if (!displayName.isBlank() && !displayName.equals(translationKey)) {
            json.append(field("display_name", displayName)).append(",");
        }
        json.append("\"attribute_modifiers\":[");
        int index = 0;
        for (Map.Entry<Attribute, AttributeModifier> entry : effect.getAttributeModifiers().entrySet()) {
            if (index > 0) {
                json.append(',');
            }
            index++;
            ResourceLocation attributeId = BuiltInRegistries.ATTRIBUTE.getKey(entry.getKey());
            AttributeModifier modifier = entry.getValue();
            json.append("{")
                    .append(field("attribute_id", stringValue(attributeId))).append(",")
                    .append(field("name", modifier.getName())).append(",")
                    .append(field("uuid", modifier.getId().toString())).append(",")
                    .append(field("operation", modifier.getOperation().toString())).append(",")
                    .append("\"amount\":").append(modifier.getAmount())
                    .append("}");
        }
        json.append("],").append(field("source", "runtime:mob_effect_registry")).append("}");
        return json.toString();
    }

    private static RuntimeDumpContent dumpAdvancements(MinecraftServer server) {
        List<String> lines = new ArrayList<>();
        for (Advancement advancement : server.getAdvancements().getAllAdvancements()) {
            lines.add("{"
                    + field("id", advancement.getId().toString()) + ","
                    + field("source", "runtime:server_advancements")
                    + "}");
        }
        lines.sort(String::compareTo);
        return NdjsonSectionDumper.dump(RuntimeSectionNames.ADVANCEMENTS, lines);
    }

    private static String field(String key, String value) {
        return "\"" + key + "\":\"" + JsonText.escape(value) + "\"";
    }

    private static String stringValue(ResourceLocation id) {
        return id == null ? "" : id.toString();
    }

    private static String stringArrayField(String key, List<String> values) {
        StringBuilder json = new StringBuilder();
        json.append('"').append(key).append("\":[");
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) {
                json.append(',');
            }
            json.append('"').append(JsonText.escape(values.get(i))).append('"');
        }
        json.append(']');
        return json.toString();
    }
}
