package dev.packwise.connector.forge;

import com.mojang.logging.LogUtils;
import dev.packwise.connector.protocol.JsonText;
import dev.packwise.connector.protocol.NdjsonSectionDumper;
import dev.packwise.connector.protocol.RuntimeDumpContent;
import dev.packwise.connector.protocol.RuntimeSectionNames;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import org.slf4j.Logger;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.function.Supplier;
import java.util.stream.Stream;

final class ForgeOptionalRuntimeDumpCollector {
    private static final Logger LOGGER = LogUtils.getLogger();

    private ForgeOptionalRuntimeDumpCollector() {
    }

    static List<RuntimeDumpContent> collect(MinecraftServer server) {
        List<RuntimeDumpContent> contents = new ArrayList<>();
        addIfPresent(contents, RuntimeSectionNames.FTB_QUESTS, () -> dumpFtbQuests());
        addIfPresent(contents, RuntimeSectionNames.PLAYER_PROGRESS, () -> dumpPlayerProgress(server));
        addIfPresent(contents, RuntimeSectionNames.TEAM_PROGRESS, () -> dumpTeamProgress());
        addIfPresent(contents, RuntimeSectionNames.STAGES, () -> dumpStages(server));
        return List.copyOf(contents);
    }

    private static Optional<RuntimeDumpContent> dumpFtbQuests() {
        if (!ForgeModSnapshots.isLoaded("ftbquests")) {
            return Optional.empty();
        }
        Object questFile = ftbQuestFile();
        if (questFile == null) {
            return Optional.empty();
        }

        List<String> lines = new ArrayList<>();
        for (Object quest : ftbQuests(questFile)) {
            Object chapter = invokeOptional(quest, "getQuestChapter");
            DependencySnapshot dependencies = dependencySnapshot(quest);
            lines.add("{"
                    + field("quest_id", codeString(quest)) + ","
                    + nullableField("chapter_id", chapter == null ? null : codeString(chapter)) + ","
                    + nullableField("title", rawTitle(quest)) + ","
                    + stringArrayField("dependencies", dependencies.ids()) + ","
                    + stringMapField("dependency_types", dependencies.types()) + ","
                    + stringArrayField("task_item_ids", taskItemIds(quest)) + ","
                    + stringArrayField("reward_item_ids", rewardItemIds(quest)) + ","
                    + field("source", "runtime:ftb_quests")
                    + "}");
        }
        lines.sort(String::compareTo);
        return Optional.of(NdjsonSectionDumper.dump(RuntimeSectionNames.FTB_QUESTS, lines));
    }

    private static Optional<RuntimeDumpContent> dumpPlayerProgress(MinecraftServer server) {
        Object questFile = ftbQuestFile();
        boolean hasFtbQuests = questFile != null;
        boolean hasGameStages = ForgeModSnapshots.isLoaded("gamestages");
        if (!hasFtbQuests && !hasGameStages) {
            return Optional.empty();
        }

        List<Object> quests = hasFtbQuests ? ftbQuests(questFile) : List.of();
        List<String> lines = new ArrayList<>();
        for (ServerPlayer player : server.getPlayerList().getPlayers()) {
            List<String> completed = List.of();
            String teamId = null;
            if (hasFtbQuests) {
                Object teamData = invokeOptional(questFile, "getOrCreateTeamData", new Class<?>[]{Entity.class}, player);
                completed = teamData == null ? List.of() : completedQuestIds(teamData, quests);
                teamId = teamData == null ? null : stringValue(invokeOptional(teamData, "getTeamId"));
            }
            List<String> stages = hasGameStages ? gameStages(player) : List.of();
            lines.add("{"
                    + field("subject_type", "player") + ","
                    + field("subject_id", player.getUUID().toString()) + ","
                    + stringArrayField("completed_quests", completed) + ","
                    + stringArrayField("completed_advancements", List.of()) + ","
                    + stringArrayField("stages", stages) + ","
                    + field("source", hasFtbQuests ? "runtime:ftb_quests" : "runtime:gamestages") + ","
                    + field("player_name", player.getGameProfile().getName()) + ","
                    + nullableField("team_id", teamId)
                    + "}");
        }
        lines.sort(String::compareTo);
        return Optional.of(NdjsonSectionDumper.dump(RuntimeSectionNames.PLAYER_PROGRESS, lines));
    }

    private static Optional<RuntimeDumpContent> dumpTeamProgress() {
        if (!ForgeModSnapshots.isLoaded("ftbquests")) {
            return Optional.empty();
        }
        Object questFile = ftbQuestFile();
        if (questFile == null) {
            return Optional.empty();
        }

        List<Object> quests = ftbQuests(questFile);
        Collection<?> teamDataItems = collectionValue(invokeOptional(questFile, "getAllTeamData"));
        List<String> lines = new ArrayList<>();
        for (Object teamData : teamDataItems) {
            String teamId = stringValue(invokeOptional(teamData, "getTeamId"));
            FtbTeamInfo teamInfo = ftbTeamInfo(teamId);
            lines.add("{"
                    + field("subject_type", "team") + ","
                    + field("subject_id", teamId) + ","
                    + stringArrayField("completed_quests", completedQuestIds(teamData, quests)) + ","
                    + stringArrayField("completed_advancements", List.of()) + ","
                    + stringArrayField("stages", List.of()) + ","
                    + field("source", "runtime:ftb_quests") + ","
                    + nullableField("team_name", teamInfo.name()) + ","
                    + stringArrayField("members", teamInfo.members())
                    + "}");
        }
        lines.sort(String::compareTo);
        return Optional.of(NdjsonSectionDumper.dump(RuntimeSectionNames.TEAM_PROGRESS, lines));
    }

    private static Optional<RuntimeDumpContent> dumpStages(MinecraftServer server) {
        if (!ForgeModSnapshots.isLoaded("gamestages")) {
            return Optional.empty();
        }

        List<String> lines = new ArrayList<>();
        for (ServerPlayer player : server.getPlayerList().getPlayers()) {
            for (String stage : gameStages(player)) {
                lines.add("{"
                        + field("subject_type", "player") + ","
                        + field("subject_id", player.getUUID().toString()) + ","
                        + field("stage", stage) + ","
                        + "\"active\":true,"
                        + field("source", "runtime:gamestages") + ","
                        + field("player_name", player.getGameProfile().getName())
                        + "}");
            }
        }
        lines.sort(String::compareTo);
        return Optional.of(NdjsonSectionDumper.dump(RuntimeSectionNames.STAGES, lines));
    }

    private static void addIfPresent(
            List<RuntimeDumpContent> contents,
            String sectionName,
            Supplier<Optional<RuntimeDumpContent>> supplier
    ) {
        try {
            supplier.get().ifPresent(contents::add);
        } catch (RuntimeException error) {
            LOGGER.warn("Packwise optional runtime section {} skipped: {}", sectionName, error.toString());
        }
    }

    private static Object ftbQuestFile() {
        return staticField("dev.ftb.mods.ftbquests.quest.ServerQuestFile", "INSTANCE");
    }

    private static List<Object> ftbQuests(Object questFile) {
        List<Object> quests = new ArrayList<>();
        invokeOptional(questFile, "forAllQuests", new Class<?>[]{Consumer.class}, (Consumer<Object>) quests::add);
        quests.sort(Comparator.comparing(ForgeOptionalRuntimeDumpCollector::codeString));
        return List.copyOf(quests);
    }

    private static DependencySnapshot dependencySnapshot(Object quest) {
        Object stream = invokeOptional(quest, "streamDependencies");
        if (!(stream instanceof Stream<?> dependencies)) {
            return new DependencySnapshot(List.of(), Map.of());
        }
        Map<String, String> dependencyTypes = new TreeMap<>();
        dependencies.forEach(dependency -> {
            String id = codeString(dependency);
            if (!id.isBlank() && !"unknown".equals(id)) {
                dependencyTypes.put(id, objectTypeId(dependency));
            }
        });
        return new DependencySnapshot(List.copyOf(dependencyTypes.keySet()), Map.copyOf(dependencyTypes));
    }

    private static List<String> taskItemIds(Object quest) {
        Set<String> ids = new TreeSet<>();
        for (Object task : collectionValue(invokeOptional(quest, "getTasks"))) {
            addItemStackId(ids, invokeOptional(task, "getItemStack"));
        }
        return List.copyOf(ids);
    }

    private static List<String> rewardItemIds(Object quest) {
        Set<String> ids = new TreeSet<>();
        for (Object reward : collectionValue(invokeOptional(quest, "getRewards"))) {
            addItemStackId(ids, invokeOptional(reward, "getItem"));
        }
        return List.copyOf(ids);
    }

    private static List<String> completedQuestIds(Object teamData, List<Object> quests) {
        List<String> completed = new ArrayList<>();
        Class<?> questObjectClass = classForName("dev.ftb.mods.ftbquests.quest.QuestObject");
        if (questObjectClass == null) {
            return List.of();
        }
        for (Object quest : quests) {
            Object value = invokeOptional(teamData, "isCompleted", new Class<?>[]{questObjectClass}, quest);
            if (Boolean.TRUE.equals(value)) {
                completed.add(codeString(quest));
            }
        }
        completed.sort(String::compareTo);
        return List.copyOf(completed);
    }

    private static List<String> gameStages(Player player) {
        Object data = invokeStaticOptional(
                "net.darkhax.gamestages.GameStageHelper",
                "getPlayerData",
                new Class<?>[]{Player.class},
                player);
        Collection<?> stages = collectionValue(data == null ? null : invokeOptional(data, "getStages"));
        return stages.stream()
                .map(String::valueOf)
                .filter(value -> !value.isBlank())
                .sorted()
                .toList();
    }

    private static FtbTeamInfo ftbTeamInfo(String teamId) {
        if (!ForgeModSnapshots.isLoaded("ftbteams") || teamId == null || teamId.isBlank()) {
            return FtbTeamInfo.empty();
        }
        UUID teamUuid = parseUuid(teamId);
        if (teamUuid == null) {
            return FtbTeamInfo.empty();
        }
        Object api = invokeStaticOptional("dev.ftb.mods.ftbteams.api.FTBTeamsAPI", "api", new Class<?>[0]);
        if (api == null || !Boolean.TRUE.equals(invokeOptional(api, "isManagerLoaded"))) {
            return FtbTeamInfo.empty();
        }
        Object manager = invokeOptional(api, "getManager");
        Object optionalTeam = invokeOptional(manager, "getTeamByID", new Class<?>[]{UUID.class}, teamUuid);
        Object team = optionalValue(optionalTeam);
        if (team == null) {
            return FtbTeamInfo.empty();
        }
        String name = stringValue(invokeOptional(team, "getShortName"));
        List<String> members = collectionValue(invokeOptional(team, "getMembers")).stream()
                .map(String::valueOf)
                .sorted()
                .toList();
        return new FtbTeamInfo(name, members);
    }

    private static UUID parseUuid(String value) {
        try {
            return UUID.fromString(value);
        } catch (IllegalArgumentException error) {
            return null;
        }
    }

    private static void addItemStackId(Set<String> ids, Object value) {
        if (!(value instanceof ItemStack stack) || stack.isEmpty()) {
            return;
        }
        ResourceLocation id = BuiltInRegistries.ITEM.getKey(stack.getItem());
        if (id != null) {
            ids.add(id.toString());
        }
    }

    private static Object optionalValue(Object value) {
        if (value instanceof Optional<?> optional) {
            return optional.orElse(null);
        }
        return value;
    }

    private static Collection<?> collectionValue(Object value) {
        if (value instanceof Collection<?> collection) {
            return collection;
        }
        return List.of();
    }

    private static String codeString(Object value) {
        Object code = invokeOptional(value, "getCodeString");
        if (code instanceof String text && !text.isBlank()) {
            return text;
        }
        Object id = invokeOptional(value, "getId");
        return id == null ? "unknown" : String.valueOf(id);
    }

    private static String objectTypeId(Object value) {
        Object type = invokeOptional(value, "getObjectType");
        Object id = type == null ? null : invokeOptional(type, "getId");
        if (id instanceof String text && !text.isBlank()) {
            return text;
        }
        return "unknown";
    }

    private static String rawTitle(Object value) {
        Object title = invokeOptional(value, "getRawTitle");
        if (title instanceof String text && !text.isBlank()) {
            return text;
        }
        return null;
    }

    private static Object staticField(String className, String fieldName) {
        Class<?> type = classForName(className);
        if (type == null) {
            return null;
        }
        try {
            Field field = type.getField(fieldName);
            return field.get(null);
        } catch (NoSuchFieldException error) {
            return null;
        } catch (IllegalAccessException error) {
            throw new IllegalStateException("Failed to read " + className + "#" + fieldName, error);
        }
    }

    private static Object invokeStaticOptional(String className, String methodName, Class<?>[] parameterTypes, Object... args) {
        Class<?> type = classForName(className);
        if (type == null) {
            return null;
        }
        try {
            Method method = type.getMethod(methodName, parameterTypes);
            return method.invoke(null, args);
        } catch (NoSuchMethodException error) {
            return null;
        } catch (IllegalAccessException | InvocationTargetException error) {
            throw new IllegalStateException("Failed to invoke " + className + "#" + methodName, error);
        }
    }

    private static Object invokeOptional(Object target, String methodName) {
        return invokeOptional(target, methodName, new Class<?>[0]);
    }

    private static Object invokeOptional(Object target, String methodName, Class<?>[] parameterTypes, Object... args) {
        if (target == null) {
            return null;
        }
        try {
            Method method = target.getClass().getMethod(methodName, parameterTypes);
            return method.invoke(target, args);
        } catch (NoSuchMethodException error) {
            return null;
        } catch (IllegalAccessException | InvocationTargetException error) {
            throw new IllegalStateException("Failed to invoke " + methodName + " on " + target.getClass().getName(), error);
        }
    }

    private static Class<?> classForName(String className) {
        try {
            return Class.forName(className);
        } catch (ClassNotFoundException error) {
            return null;
        }
    }

    private static String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static String field(String key, String value) {
        return "\"" + key + "\":\"" + JsonText.escape(value) + "\"";
    }

    private static String nullableField(String key, String value) {
        if (value == null || value.isBlank()) {
            return "\"" + key + "\":null";
        }
        return field(key, value);
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

    private static String stringMapField(String key, Map<String, String> values) {
        StringBuilder json = new StringBuilder();
        json.append('"').append(key).append("\":{");
        int index = 0;
        for (Map.Entry<String, String> entry : new TreeMap<>(values).entrySet()) {
            if (index > 0) {
                json.append(',');
            }
            json.append('"').append(JsonText.escape(entry.getKey())).append("\":\"")
                    .append(JsonText.escape(entry.getValue())).append('"');
            index++;
        }
        json.append('}');
        return json.toString();
    }

    private record DependencySnapshot(List<String> ids, Map<String, String> types) {
    }

    private record FtbTeamInfo(String name, List<String> members) {
        static FtbTeamInfo empty() {
            return new FtbTeamInfo(null, List.of());
        }
    }
}
