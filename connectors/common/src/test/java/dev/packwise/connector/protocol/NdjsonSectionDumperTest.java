package dev.packwise.connector.protocol;

import java.util.List;

public final class NdjsonSectionDumperTest {
    public static void main(String[] args) {
        createsGenericNdjsonPayload();
        System.out.println("NdjsonSectionDumperTest passed");
    }

    private static void createsGenericNdjsonPayload() {
        RuntimeDumpContent content = NdjsonSectionDumper.dump(
                RuntimeSectionNames.ITEMS,
                List.of(
                        "{\"id\":\"minecraft:stone\"}",
                        "{\"id\":\"minecraft:dirt\"}"));

        assertEquals("items", content.sectionName(), "section name");
        assertEquals("application/x-ndjson", content.contentType(), "content type");
        assertEquals(2, content.count(), "count");
        assertEquals("{\"id\":\"minecraft:stone\"}\n{\"id\":\"minecraft:dirt\"}\n", content.body(), "body");
        assertEquals(64, content.sha256().length(), "sha256 hex length");
    }

    private static void assertEquals(Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + " but got " + actual);
        }
    }
}
