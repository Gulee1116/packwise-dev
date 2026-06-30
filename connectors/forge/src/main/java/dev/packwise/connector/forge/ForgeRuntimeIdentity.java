package dev.packwise.connector.forge;

import dev.packwise.connector.protocol.ConnectorInfo;
import dev.packwise.connector.protocol.ConnectorSide;
import net.minecraft.SharedConstants;
import net.minecraftforge.fml.ModList;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URI;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public final class ForgeRuntimeIdentity {
    private static final ForgePackMetadata DETECTED_PACK_METADATA = ForgePackMetadata.detect(Path.of("."));

    private ForgeRuntimeIdentity() {
    }

    public static ConnectorInfo connectorInfo() {
        String minecraftVersion = SharedConstants.getCurrentVersion().getName();
        String forgeVersion = forgeVersion();
        return new ConnectorInfo(
                value("packwise.connectorId", "PACKWISE_CONNECTOR_ID", "forge-" + minecraftVersion + "-" + forgeVersion),
                ConnectorSide.SERVER,
                "forge",
                forgeVersion,
                minecraftVersion,
                value("packwise.packId", "PACKWISE_PACK_ID", DETECTED_PACK_METADATA.packId()),
                value("packwise.packName", "PACKWISE_PACK_NAME", DETECTED_PACK_METADATA.packName()),
                value("packwise.packVersion", "PACKWISE_PACK_VERSION", DETECTED_PACK_METADATA.packVersion()),
                PackwiseForgeMod.MOD_ID,
                connectorVersion(),
                capabilities());
    }

    public static Optional<URI> agentBaseUri() {
        String configured = value(
                "packwise.agentUrl",
                List.of("PACKWISE_BACKEND_BASE_URL", "PACKWISE_AGENT_BASE_URL", "PACKWISE_AGENT_URL"),
                "");
        if (configured.isBlank()) {
            return Optional.empty();
        }
        return Optional.of(URI.create(configured));
    }

    public static Path dumpRootDirectory() {
        return Path.of(value("packwise.dumpDir", "PACKWISE_DUMP_DIR", "packwise-dumps"));
    }

    public static String connectorVersion() {
        return ModList.get().getModContainerById(PackwiseForgeMod.MOD_ID)
                .map(container -> container.getModInfo().getVersion().toString())
                .orElse("unknown");
    }

    public static List<String> capabilities() {
        List<String> capabilities = new ArrayList<>();
        capabilities.add("runtime_dump");
        capabilities.add("commands");
        capabilities.add("server_progress");
        if (ForgeModSnapshots.isLoaded("ftbquests")) {
            capabilities.add("quest_progress");
        }
        if (ForgeModSnapshots.isLoaded("ftbteams")) {
            capabilities.add("team_progress");
        }
        if (ForgeModSnapshots.isLoaded("gamestages")) {
            capabilities.add("stage_state");
        }
        if (ForgeModSnapshots.isLoaded("kubejs")) {
            capabilities.add("kubejs_static_sources");
        }
        return List.copyOf(capabilities);
    }

    public static List<String> optionalIntegrationStatus() {
        Map<String, Boolean> integrations = new LinkedHashMap<>();
        integrations.put("ftbquests", ForgeModSnapshots.isLoaded("ftbquests"));
        integrations.put("ftbteams", ForgeModSnapshots.isLoaded("ftbteams"));
        integrations.put("gamestages", ForgeModSnapshots.isLoaded("gamestages"));
        integrations.put("kubejs", ForgeModSnapshots.isLoaded("kubejs"));
        return integrations.entrySet().stream()
                .map(entry -> entry.getKey() + "=" + (entry.getValue() ? "loaded" : "not_loaded"))
                .toList();
    }

    private static String value(String property, String env, String fallback) {
        return value(property, List.of(env), fallback);
    }

    private static String value(String property, List<String> envNames, String fallback) {
        String fromProperty = System.getProperty(property);
        if (fromProperty != null && !fromProperty.isBlank()) {
            return fromProperty;
        }
        for (String envName : envNames) {
            String fromEnv = System.getenv(envName);
            if (fromEnv != null && !fromEnv.isBlank()) {
                return fromEnv;
            }
        }
        return fallback;
    }

    private static String forgeVersion() {
        Object version = invokeStatic("net.minecraftforge.versions.forge.ForgeVersion", "getVersion");
        if (version == null) {
            version = invokeStatic("net.minecraftforge.common.ForgeVersion", "getVersion");
        }
        return version == null ? "unknown" : String.valueOf(version);
    }

    private static Object invokeStatic(String className, String methodName) {
        try {
            Class<?> type = Class.forName(className);
            Method method = type.getMethod(methodName);
            return method.invoke(null);
        } catch (ClassNotFoundException | NoSuchMethodException error) {
            return null;
        } catch (IllegalAccessException | InvocationTargetException error) {
            throw new IllegalStateException("Failed to invoke " + className + "#" + methodName, error);
        }
    }
}
