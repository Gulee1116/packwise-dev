package dev.packwise.connector.protocol;

import java.util.List;

public final class ModsSectionDumperTest {
    public static void main(String[] args) {
        createsNdjsonPayloadAndManifestSection();
        System.out.println("ModsSectionDumperTest passed");
    }

    private static void createsNdjsonPayloadAndManifestSection() {
        RuntimeDumpContent content = ModsSectionDumper.dump(List.of(
                new ModSnapshot("minecraft", "Minecraft", "1.21.1", "builtin"),
                new ModSnapshot("neoforge", "NeoForge", "21.1.233", "modlist")));

        assertEquals("mods", content.sectionName(), "section name");
        assertEquals("application/x-ndjson", content.contentType(), "content type");
        assertEquals(2, content.count(), "count");
        assertContains(content.body(), "\"mod_id\":\"minecraft\"");
        assertContains(content.body(), "\"display_name\":\"NeoForge\"");
        assertTrue(content.body().endsWith("\n"), "body ends with newline");
        assertEquals(64, content.sha256().length(), "sha256 hex length");

        RuntimeDumpSection section = content.toManifestSection();
        assertEquals("mods", section.name(), "manifest section name");
        assertEquals(2, section.count(), "manifest section count");
        assertEquals(content.sha256(), section.sha256(), "manifest section sha");
    }

    private static void assertContains(String actual, String expected) {
        if (!actual.contains(expected)) {
            throw new AssertionError("Expected text to contain " + expected + " but was " + actual);
        }
    }

    private static void assertEquals(Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + " but got " + actual);
        }
    }

    private static void assertTrue(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }
}
