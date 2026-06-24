package dev.packwise.connector.protocol;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class RuntimeDumpFileWriter {
    public Path write(
            Path rootDirectory,
            String messageId,
            String sentAt,
            ConnectorInfo connector,
            String dumpId,
            List<RuntimeDumpContent> contents) throws IOException {
        return write(
                rootDirectory,
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
    }

    public Path write(
            Path rootDirectory,
            String messageId,
            String sentAt,
            String connectorId,
            String dumpId,
            String minecraftVersion,
            String loader,
            String loaderVersion,
            List<RuntimeDumpContent> contents) throws IOException {
        return write(
                rootDirectory,
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

    public Path write(
            Path rootDirectory,
            String messageId,
            String sentAt,
            String connectorId,
            String dumpId,
            String minecraftVersion,
            String loader,
            String loaderVersion,
            String connectorModId,
            String connectorVersion,
            List<RuntimeDumpContent> contents) throws IOException {
        Objects.requireNonNull(rootDirectory, "rootDirectory");
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
        Map<String, String> targetFiles = sectionTargetFiles(contents);
        Path dumpDirectory = rootDirectory.resolve(safePathSegment(dumpId));
        Files.createDirectories(dumpDirectory);
        Files.writeString(dumpDirectory.resolve("manifest.json"), manifest.toJson() + "\n", StandardCharsets.UTF_8);
        for (RuntimeDumpContent content : contents) {
            Files.writeString(
                    dumpDirectory.resolve(targetFiles.get(content.sectionName())),
                    content.body(),
                    StandardCharsets.UTF_8);
        }
        return dumpDirectory;
    }

    private static Map<String, String> sectionTargetFiles(List<RuntimeDumpContent> contents) {
        Map<String, String> filesBySection = new LinkedHashMap<>();
        Map<String, String> sectionByFile = new LinkedHashMap<>();
        for (RuntimeDumpContent content : contents) {
            String file = sectionFilename(content.sectionName(), content.contentType());
            String previousSection = sectionByFile.putIfAbsent(file, content.sectionName());
            if (previousSection != null && !previousSection.equals(content.sectionName())) {
                throw new IllegalArgumentException(
                        "Runtime dump sections resolve to the same file "
                                + file
                                + ": "
                                + previousSection
                                + ", "
                                + content.sectionName());
            }
            filesBySection.put(content.sectionName(), file);
        }
        return Map.copyOf(filesBySection);
    }

    private static String sectionFilename(String sectionName, String contentType) {
        return safePathSegment(sectionName) + extension(contentType);
    }

    private static String extension(String contentType) {
        if (NdjsonSectionDumper.CONTENT_TYPE.equals(contentType)) {
            return ".ndjson";
        }
        return ".txt";
    }

    private static String safePathSegment(String value) {
        Objects.requireNonNull(value, "path segment");
        StringBuilder safe = new StringBuilder(value.length());
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (Character.isLetterOrDigit(c) || c == '_' || c == '-' || c == '.') {
                safe.append(c);
            } else {
                safe.append('_');
            }
        }
        if (safe.isEmpty()) {
            throw new IllegalArgumentException("path segment must not be empty");
        }
        if (safe.toString().equals(".") || safe.toString().equals("..")) {
            throw new IllegalArgumentException("path segment must not resolve to current or parent directory");
        }
        return safe.toString();
    }
}
