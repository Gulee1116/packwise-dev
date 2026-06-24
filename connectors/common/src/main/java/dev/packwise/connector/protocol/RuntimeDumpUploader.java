package dev.packwise.connector.protocol;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class RuntimeDumpUploader {
    private final AgentHttpClient client;

    public RuntimeDumpUploader(AgentHttpClient client) {
        this.client = Objects.requireNonNull(client, "client");
    }

    public RuntimeDumpUploadResult upload(
            String messageId,
            String sentAt,
            ConnectorInfo connector,
            String dumpId,
            List<RuntimeDumpContent> contents) throws IOException, InterruptedException {
        String helloResponse = client.sendHello(ConnectorHello.create(messageId + "_hello", sentAt, connector));
        RuntimeDumpUploadResult dumpResult = upload(
                messageId,
                sentAt,
                connector.id(),
                dumpId,
                connector.minecraftVersion(),
                connector.loader(),
                connector.loaderVersion(),
                connector.connectorModId(),
                connector.connectorVersion(),
                contents);
        return new RuntimeDumpUploadResult(
                helloResponse,
                dumpResult.manifestResponse(),
                dumpResult.sectionResponses());
    }

    public RuntimeDumpUploadResult upload(
            String messageId,
            String sentAt,
            String connectorId,
            String dumpId,
            String minecraftVersion,
            String loader,
            String loaderVersion,
            List<RuntimeDumpContent> contents) throws IOException, InterruptedException {
        return upload(
                messageId,
                sentAt,
                connectorId,
                dumpId,
                minecraftVersion,
                loader,
                loaderVersion,
                "unknown",
                "unknown",
                contents);
    }

    public RuntimeDumpUploadResult upload(
            String messageId,
            String sentAt,
            String connectorId,
            String dumpId,
            String minecraftVersion,
            String loader,
            String loaderVersion,
            String connectorModId,
            String connectorVersion,
            List<RuntimeDumpContent> contents) throws IOException, InterruptedException {
        List<RuntimeDumpSection> sections = contents.stream()
                .map(RuntimeDumpContent::toManifestSection)
                .toList();
        RuntimeDumpManifest manifest = RuntimeDumpManifest.create(
                messageId,
                sentAt,
                connectorId,
                dumpId,
                minecraftVersion,
                loader,
                loaderVersion,
                connectorModId,
                connectorVersion,
                sections);
        String manifestResponse = client.sendRuntimeDumpManifest(manifest);
        List<String> sectionResponses = new ArrayList<>();
        for (RuntimeDumpContent content : contents) {
            sectionResponses.add(client.sendRuntimeDumpSection(
                    connectorId,
                    dumpId,
                    content.sectionName(),
                    content.contentType(),
                    content.body()));
        }
        return new RuntimeDumpUploadResult(manifestResponse, sectionResponses);
    }
}
