package dev.packwise.connector.protocol;

import java.util.Objects;

public record RuntimeDumpContent(
        String sectionName,
        String contentType,
        String body,
        int count,
        String sha256) {

    public RuntimeDumpContent {
        Objects.requireNonNull(sectionName, "sectionName");
        Objects.requireNonNull(contentType, "contentType");
        Objects.requireNonNull(body, "body");
        Objects.requireNonNull(sha256, "sha256");
        if (count < 0) {
            throw new IllegalArgumentException("count must be non-negative");
        }
    }

    public RuntimeDumpSection toManifestSection() {
        return new RuntimeDumpSection(sectionName, contentType, count, sha256);
    }
}
