package dev.packwise.connector.protocol;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collection;
import java.util.Objects;

public final class NdjsonSectionDumper {
    public static final String CONTENT_TYPE = "application/x-ndjson";

    private NdjsonSectionDumper() {
    }

    public static RuntimeDumpContent dump(String sectionName, Collection<String> jsonLines) {
        Objects.requireNonNull(sectionName, "sectionName");
        Objects.requireNonNull(jsonLines, "jsonLines");
        StringBuilder body = new StringBuilder();
        int count = 0;
        for (String line : jsonLines) {
            Objects.requireNonNull(line, "json line");
            body.append(line).append('\n');
            count++;
        }
        String text = body.toString();
        return new RuntimeDumpContent(
                sectionName,
                CONTENT_TYPE,
                text,
                count,
                sha256(text));
    }

    public static String sha256(String text) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                out.append(String.format("%02x", b));
            }
            return out.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is not available", error);
        }
    }
}
