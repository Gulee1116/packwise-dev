package dev.packwise.connector.protocol;

import java.util.Objects;

public record RuntimeDumpSection(
        String name,
        String contentType,
        int count,
        String sha256) {

    public RuntimeDumpSection {
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(contentType, "contentType");
        Objects.requireNonNull(sha256, "sha256");
        if (count < 0) {
            throw new IllegalArgumentException("count must be non-negative");
        }
    }
}
