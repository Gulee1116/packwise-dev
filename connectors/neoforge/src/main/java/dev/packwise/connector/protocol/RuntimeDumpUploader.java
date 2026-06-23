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
            String connectorId,
            String dumpId,
            String minecraftVersion,
            String loader,
            String loaderVersion,
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
