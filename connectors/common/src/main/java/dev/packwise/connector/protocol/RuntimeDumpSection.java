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
        if (name.isEmpty()) {
            throw new IllegalArgumentException("name must not be empty");
        }
        if (contentType.isEmpty()) {
            throw new IllegalArgumentException("content_type must not be empty");
        }
        if (sha256.isEmpty()) {
            throw new IllegalArgumentException("sha256 must not be empty");
        }
        if (count < 0) {
            throw new IllegalArgumentException("count must be non-negative");
        }
        if (RuntimeSectionNames.isStandard(name) && !NdjsonSectionDumper.CONTENT_TYPE.equals(contentType)) {
            throw new IllegalArgumentException(
                    "Runtime dump section " + name + " must use content_type " + NdjsonSectionDumper.CONTENT_TYPE);
        }
    }
}
