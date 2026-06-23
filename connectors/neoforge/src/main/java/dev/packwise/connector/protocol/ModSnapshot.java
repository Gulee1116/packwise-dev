package dev.packwise.connector.protocol;

import java.util.Objects;

public record ModSnapshot(
        String modId,
        String displayName,
        String version,
        String source) {

    public ModSnapshot {
        Objects.requireNonNull(modId, "modId");
        Objects.requireNonNull(displayName, "displayName");
        Objects.requireNonNull(version, "version");
        Objects.requireNonNull(source, "source");
    }

    public String toJsonLine() {
        return "{"
                + field("mod_id", modId) + ","
                + field("display_name", displayName) + ","
                + field("version", version) + ","
                + field("source", source)
                + "}";
    }

    private static String field(String key, String value) {
        return "\"" + key + "\":\"" + JsonText.escape(value) + "\"";
    }
}
