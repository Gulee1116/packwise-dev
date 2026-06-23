package dev.packwise.connector.protocol;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

public final class ModsSectionDumper {
    private ModsSectionDumper() {
    }

    public static RuntimeDumpContent dump(List<ModSnapshot> mods) {
        StringBuilder body = new StringBuilder();
        for (ModSnapshot mod : mods) {
            body.append(mod.toJsonLine()).append('\n');
        }
        String text = body.toString();
        return new RuntimeDumpContent(
                "mods",
                "application/x-ndjson",
                text,
                mods.size(),
                sha256(text));
    }

    private static String sha256(String text) {
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
