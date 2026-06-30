package dev.packwise.connector.forge;

import com.mojang.logging.LogUtils;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import dev.packwise.connector.protocol.AgentHttpClient;
import dev.packwise.connector.protocol.AgentAnswer;
import dev.packwise.connector.protocol.CommandResponse;
import dev.packwise.connector.protocol.ConnectorInfo;
import dev.packwise.connector.protocol.QueryAsk;
import dev.packwise.connector.protocol.RuntimeDumpContent;
import dev.packwise.connector.protocol.RuntimeDumpFileWriter;
import dev.packwise.connector.protocol.RuntimeDumpUploader;
import dev.packwise.connector.protocol.RuntimeSectionNames;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.RegisterCommandsEvent;
import org.slf4j.Logger;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Path;
import java.time.Instant;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

public final class PackwiseForgeCommands {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static volatile String lastUploadedDumpId = "";

    private PackwiseForgeCommands() {
    }

    public static void register(RegisterCommandsEvent event) {
        CommandDispatcher<CommandSourceStack> dispatcher = event.getDispatcher();
        dispatcher.register(Commands.literal("packwise")
                .then(Commands.literal("status")
                        .executes(context -> status(context.getSource())))
                .then(Commands.literal("dump")
                        .requires(source -> source.hasPermission(2))
                        .executes(context -> dump(context.getSource())))
                .then(Commands.literal("ask")
                        .then(Commands.argument("question", StringArgumentType.greedyString())
                                .executes(context -> ask(
                                        context.getSource(),
                                        StringArgumentType.getString(context, "question"))))));
    }

    private static int status(CommandSourceStack source) {
        ConnectorInfo connector = ForgeRuntimeIdentity.connectorInfo();
        Optional<URI> agentUri = ForgeRuntimeIdentity.agentBaseUri();
        List<String> lines = List.of(
                "Packwise connector: forge " + connector.loaderVersion() + " / Minecraft " + connector.minecraftVersion(),
                "Connector Mod: " + PackwiseForgeMod.MOD_ID + " " + ForgeRuntimeIdentity.connectorVersion(),
                "Connector ID: " + connector.id(),
                "Pack: " + connector.packName() + " (" + connector.packId() + " " + connector.packVersion() + ")",
                "Capabilities: " + String.join(", ", connector.capabilities()),
                "Optional integrations: " + String.join(", ", ForgeRuntimeIdentity.optionalIntegrationStatus()),
                "Agent URL: " + agentUri.map(URI::toString).orElse("not configured"));
        sendAndLog(source, lines);
        return 1;
    }

    private static int dump(CommandSourceStack source) {
        MinecraftServer server = source.getServer();
        ConnectorInfo connector = ForgeRuntimeIdentity.connectorInfo();
        List<RuntimeDumpContent> contents;
        try {
            contents = ForgeRuntimeDumpCollector.collect(server);
        } catch (RuntimeException error) {
            sendFailureAndLog(source, "Packwise dump failed while collecting runtime data: " + error.getMessage(), error);
            return 0;
        }

        String now = Instant.now().toString();
        String messageId = "msg_" + UUID.randomUUID().toString().replace("-", "");
        String dumpId = "dump_" + UUID.randomUUID().toString().replace("-", "");
        Path localDumpDirectory;
        try {
            localDumpDirectory = new RuntimeDumpFileWriter().write(
                    ForgeRuntimeIdentity.dumpRootDirectory(),
                    messageId,
                    now,
                    connector,
                    dumpId,
                    contents);
        } catch (IOException error) {
            sendFailureAndLog(source, "Packwise local dump write failed: " + error.getMessage(), error);
            return 0;
        }

        List<String> details = new java.util.ArrayList<>(contents.stream()
                .map(content -> content.sectionName() + "=" + content.count())
                .toList());
        details.add("connector_id=" + connector.id());
        details.add("dump_id=" + dumpId);
        details.add("optional_integrations=" + String.join("|", ForgeRuntimeIdentity.optionalIntegrationStatus()));
        details.add("optional_sections=" + optionalSectionsSummary(contents));
        details.add("path=" + localDumpDirectory);
        Optional<URI> agentUri = ForgeRuntimeIdentity.agentBaseUri();
        if (agentUri.isEmpty()) {
            CommandResponse response = new CommandResponse(
                    false,
                    "runtime dump written locally; upload skipped because PACKWISE_BACKEND_BASE_URL/PACKWISE_AGENT_BASE_URL/PACKWISE_AGENT_URL is not configured",
                    details);
            sendAndLog(source, responseLines(response));
            return 1;
        }

        try {
            RuntimeDumpUploader uploader = new RuntimeDumpUploader(new AgentHttpClient(agentUri.get()));
            uploader.upload(
                    messageId,
                    now,
                    connector,
                    dumpId,
                    contents);
            lastUploadedDumpId = dumpId;
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            details.add("upload_error=" + error.getClass().getSimpleName() + ":" + String.valueOf(error.getMessage()));
            CommandResponse response = new CommandResponse(
                    false,
                    "runtime dump written locally; upload failed: " + error.getMessage(),
                    details);
            sendAndLog(source, responseLines(response));
            return 1;
        }

        CommandResponse response = new CommandResponse(true, "runtime dump written and uploaded: " + dumpId, details);
        sendAndLog(source, responseLines(response));
        return 1;
    }

    private static List<String> responseLines(CommandResponse response) {
        return List.of("Packwise: " + response.summary(), String.join(", ", response.details()));
    }

    private static void sendAndLog(CommandSourceStack source, List<String> lines) {
        for (String line : lines) {
            source.sendSuccess(() -> Component.literal(line), false);
            LOGGER.info(line);
        }
    }

    private static void sendFailureAndLog(CommandSourceStack source, String message, Throwable error) {
        source.sendFailure(Component.literal(message));
        if (error == null) {
            LOGGER.warn(message);
        } else {
            LOGGER.warn(message, error);
        }
    }

    private static String optionalSectionsSummary(List<RuntimeDumpContent> contents) {
        Set<String> optionalSections = new HashSet<>(List.of(
                RuntimeSectionNames.FTB_QUESTS,
                RuntimeSectionNames.PLAYER_PROGRESS,
                RuntimeSectionNames.TEAM_PROGRESS,
                RuntimeSectionNames.STAGES));
        List<String> emitted = contents.stream()
                .map(RuntimeDumpContent::sectionName)
                .filter(optionalSections::contains)
                .sorted()
                .toList();
        return emitted.isEmpty() ? "none" : String.join("|", emitted);
    }

    private static int ask(CommandSourceStack source, String question) {
        Optional<URI> agentUri = ForgeRuntimeIdentity.agentBaseUri();
        if (agentUri.isEmpty()) {
            sendFailureAndLog(
                    source,
                    "Packwise ask requires PACKWISE_BACKEND_BASE_URL, PACKWISE_AGENT_BASE_URL, PACKWISE_AGENT_URL, or -Dpackwise.agentUrl.",
                    null);
            return 0;
        }
        ConnectorInfo connector = ForgeRuntimeIdentity.connectorInfo();
        Map<String, String> context = new LinkedHashMap<>();
        context.put("connector_id", connector.id());
        context.put("loader", connector.loader());
        context.put("minecraft_version", connector.minecraftVersion());
        context.put("pack_id", connector.packId());
        if (source.getEntity() instanceof ServerPlayer player) {
            context.put("player_id", player.getUUID().toString());
            context.put("player_name", player.getGameProfile().getName());
        }
        if (!lastUploadedDumpId.isBlank()) {
            context.put("dump_id", lastUploadedDumpId);
        }

        QueryAsk ask = QueryAsk.create(
                "msg_" + UUID.randomUUID().toString().replace("-", ""),
                Instant.now().toString(),
                question,
                "zh_cn",
                context);
        String responseJson;
        try {
            responseJson = new AgentHttpClient(agentUri.get()).sendAsk(ask);
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            sendFailureAndLog(source, "Packwise ask failed: " + error.getMessage(), error);
            return 0;
        }

        AgentAnswer answer = AgentAnswer.fromAnswerPacketJson(responseJson);
        sendAndLog(source, answerLines(answer));
        return 1;
    }

    private static List<String> answerLines(AgentAnswer answer) {
        List<String> lines = new java.util.ArrayList<>();
        lines.add("Packwise: " + answer.summary());
        for (String nextStep : answer.nextSteps().stream().limit(3).toList()) {
            lines.add("- " + nextStep);
        }
        if (!answer.sourceRefs().isEmpty()) {
            lines.add("Sources: " + sourceRefsSummary(answer.sourceRefs()));
        }
        lines.add("Confidence: " + answer.confidence());
        return List.copyOf(lines);
    }

    private static String sourceRefsSummary(List<AgentAnswer.SourceRef> sourceRefs) {
        return String.join(", ", sourceRefs.stream()
                .limit(3)
                .map(AgentAnswer.SourceRef::compact)
                .toList());
    }
}
