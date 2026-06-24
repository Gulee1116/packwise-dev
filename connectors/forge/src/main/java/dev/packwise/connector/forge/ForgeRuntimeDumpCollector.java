package dev.packwise.connector.forge;

import com.mojang.datafixers.util.Pair;
import com.mojang.logging.LogUtils;
import dev.packwise.connector.protocol.JsonText;
import dev.packwise.connector.protocol.ModsSectionDumper;
import dev.packwise.connector.protocol.NdjsonSectionDumper;
import dev.packwise.connector.protocol.RuntimeDumpContent;
import dev.packwise.connector.protocol.RuntimeSectionNames;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderSet;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.Recipe;
import org.slf4j.Logger;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
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
        contents.add(dumpAdvancements(server));
        contents.addAll(ForgeOptionalRuntimeDumpCollector.collect(server));
        return List.copyOf(contents);
    }

    private static <T> RuntimeDumpContent dumpRegistry(String sectionName, String registryName, Registry<T> registry) {
        List<String> lines = registry.keySet().stream()
                .sorted(Comparator.comparing(ResourceLocation::toString))
                .map(id -> "{"
                        + field("id", id.toString()) + ","
                        + field("registry", registryName) + ","
                        + field("namespace", id.getNamespace()) + ","
                        + field("path", id.getPath()) + ","
                        + field("source", "runtime:built_in_registry")
                        + "}")
                .toList();
        return NdjsonSectionDumper.dump(sectionName, lines);
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
        for (Object recipeEntry : server.getRecipeManager().getRecipes()) {
            String recipeId = "unknown";
            try {
                recipeId = firstString(invokeOptional(recipeEntry, "id"), "unknown");
                String line = recipeLine(server, recipeEntry);
                if (line != null) {
                    lines.add(line);
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

    private static String recipeLine(MinecraftServer server, Object recipeEntry) {
        Object holderRecipe = invokeOptional(recipeEntry, "value");
        Object recipeObject = holderRecipe == null ? recipeEntry : holderRecipe;
        if (!(recipeObject instanceof Recipe<?> recipe)) {
            return null;
        }
        String recipeId = firstString(invokeOptional(recipeEntry, "id"), invokeOptional(recipe, "getId"));
        ResourceLocation recipeType = BuiltInRegistries.RECIPE_TYPE.getKey(recipe.getType());
        ResourceLocation serializer = BuiltInRegistries.RECIPE_SERIALIZER.getKey(recipe.getSerializer());
        ItemStack result = recipe.getResultItem(server.registryAccess());
        ResourceLocation resultItem = result.isEmpty() ? null : BuiltInRegistries.ITEM.getKey(result.getItem());
        return "{"
                + field("id", recipeId) + ","
                + field("type", stringValue(recipeType)) + ","
                + field("serializer", stringValue(serializer)) + ","
                + field("result_item", stringValue(resultItem)) + ","
                + "\"result_count\":" + (result.isEmpty() ? 0 : result.getCount()) + ","
                + stringArrayField("ingredient_items", ingredientItemIds(recipe)) + ","
                + field("source", "runtime:recipe_manager")
                + "}";
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

    private static RuntimeDumpContent dumpAdvancements(MinecraftServer server) {
        List<String> lines = new ArrayList<>();
        for (Object advancement : server.getAdvancements().getAllAdvancements()) {
            lines.add("{"
                    + field("id", advancementId(advancement)) + ","
                    + field("source", "runtime:server_advancements")
                    + "}");
        }
        lines.sort(String::compareTo);
        return NdjsonSectionDumper.dump(RuntimeSectionNames.ADVANCEMENTS, lines);
    }

    private static String advancementId(Object advancement) {
        Object id = invokeOptional(advancement, "id");
        if (id == null) {
            id = invokeOptional(advancement, "getId");
        }
        return String.valueOf(id);
    }

    private static Object invokeOptional(Object target, String methodName) {
        try {
            Method method = target.getClass().getMethod(methodName);
            return method.invoke(target);
        } catch (NoSuchMethodException error) {
            return null;
        } catch (IllegalAccessException | InvocationTargetException error) {
            throw new IllegalStateException("Failed to invoke " + methodName + " on " + target.getClass().getName(), error);
        }
    }

    private static String firstString(Object... values) {
        for (Object value : values) {
            if (value != null) {
                String text = String.valueOf(value);
                if (!text.isBlank()) {
                    return text;
                }
            }
        }
        return "unknown";
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
