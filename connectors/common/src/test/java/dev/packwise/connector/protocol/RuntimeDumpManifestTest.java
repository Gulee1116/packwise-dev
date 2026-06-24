package dev.packwise.connector.protocol;

import java.util.List;

public final class RuntimeDumpManifestTest {
    public static void main(String[] args) {
        roundTripsRuntimeDumpManifest();
        roundTripsRuntimeDumpManifestControlCharacters();
        rejectsStandardSectionWithNonNdjsonContentType();
        rejectsDecodedStandardSectionWithNonNdjsonContentType();
        allowsCustomSectionWithNonNdjsonContentType();
        rejectsDuplicateSectionNames();
        rejectsConnectorPathMismatch();
        System.out.println("RuntimeDumpManifestTest passed");
    }

    private static void roundTripsRuntimeDumpManifest() {
        RuntimeDumpManifest manifest = RuntimeDumpManifest.create(
                "msg_0200",
                "2026-06-14T08:10:00Z",
                "stoneblock4-dev-server",
                "dump_20260614_081000",
                "1.21.1",
                "neoforge",
                "21.1.233",
                "packwise_connector",
                "0.1.0",
                List.of(
                        new RuntimeDumpSection("mods", "application/x-ndjson", 404, "sha-mods"),
                        new RuntimeDumpSection("recipes", "application/x-ndjson", 8000, "sha-recipes")));

        String json = manifest.toJson();
        assertContains(json, "\"message_type\":\"runtime_dump.manifest\"");
        assertContains(json, "\"connector_id\":\"stoneblock4-dev-server\"");
        assertContains(json, "\"connector_mod_id\":\"packwise_connector\"");
        assertContains(json, "\"connector_version\":\"0.1.0\"");
        assertContains(json, "\"name\":\"recipes\"");

        RuntimeDumpManifest decoded = RuntimeDumpManifest.fromJson(json);
        assertEquals("msg_0200", decoded.messageId(), "message_id");
        assertEquals("stoneblock4-dev-server", decoded.connectorId(), "connector_id");
        assertEquals("dump_20260614_081000", decoded.dumpId(), "dump_id");
        assertEquals("21.1.233", decoded.loaderVersion(), "loader_version");
        assertEquals("packwise_connector", decoded.connectorModId(), "connector_mod_id");
        assertEquals("0.1.0", decoded.connectorVersion(), "connector_version");
        assertEquals(2, decoded.sections().size(), "sections size");
        assertEquals("mods", decoded.sections().get(0).name(), "first section name");
        assertEquals(8000, decoded.sections().get(1).count(), "second section count");
    }

    private static void roundTripsRuntimeDumpManifestControlCharacters() {
        RuntimeDumpManifest manifest = RuntimeDumpManifest.create(
                "msg_0200\b",
                "2026-06-14T08:10:00Z",
                "forge-test-server",
                "dump_test",
                "1.20.1",
                "forge",
                "47.4.20\f\u0001",
                List.of(new RuntimeDumpSection("recipes\u0001", "application/x-ndjson", 1, "sha-recipes")));

        String json = manifest.toJson();
        assertContains(json, "msg_0200\\b");
        assertContains(json, "47.4.20\\f\\u0001");
        assertContains(json, "recipes\\u0001");

        RuntimeDumpManifest decoded = RuntimeDumpManifest.fromJson(json);
        assertEquals("msg_0200\b", decoded.messageId(), "control message_id");
        assertEquals("47.4.20\f\u0001", decoded.loaderVersion(), "control loader_version");
        assertEquals("recipes\u0001", decoded.sections().get(0).name(), "control section name");
    }

    private static void rejectsStandardSectionWithNonNdjsonContentType() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new RuntimeDumpSection("recipes", "text/plain", 1, "sha-recipes"),
                "standard section content type");
    }

    private static void rejectsDecodedStandardSectionWithNonNdjsonContentType() {
        String json = "{"
                + "\"protocol\":\"packwise.connector.v1\","
                + "\"message_type\":\"runtime_dump.manifest\","
                + "\"message_id\":\"msg_0200\","
                + "\"sent_at\":\"2026-06-14T08:10:00Z\","
                + "\"connector_id\":\"forge-test-server\","
                + "\"dump_id\":\"dump_test\","
                + "\"minecraft_version\":\"1.20.1\","
                + "\"loader\":\"forge\","
                + "\"loader_version\":\"47.4.20\","
                + "\"sections\":[{\"name\":\"recipes\",\"content_type\":\"text/plain\",\"count\":1,\"sha256\":\"sha-recipes\"}]"
                + "}";

        assertThrows(
                IllegalArgumentException.class,
                () -> RuntimeDumpManifest.fromJson(json),
                "decoded standard section content type");
    }

    private static void allowsCustomSectionWithNonNdjsonContentType() {
        RuntimeDumpManifest manifest = RuntimeDumpManifest.create(
                "msg_0200",
                "2026-06-14T08:10:00Z",
                "forge-test-server",
                "dump_test",
                "1.20.1",
                "forge",
                "47.4.20",
                List.of(new RuntimeDumpSection("diagnostic/notes", "text/plain", 1, "sha-notes")));

        assertEquals("diagnostic/notes", manifest.sections().get(0).name(), "custom section name");
        assertEquals("text/plain", manifest.sections().get(0).contentType(), "custom section content type");
    }

    private static void rejectsDuplicateSectionNames() {
        assertThrows(
                IllegalArgumentException.class,
                () -> RuntimeDumpManifest.create(
                        "msg_0200",
                        "2026-06-14T08:10:00Z",
                        "forge-test-server",
                        "dump_test",
                        "1.20.1",
                        "forge",
                        "47.4.20",
                        List.of(
                                new RuntimeDumpSection("recipes", "application/x-ndjson", 1, "sha-recipes-a"),
                                new RuntimeDumpSection("recipes", "application/x-ndjson", 1, "sha-recipes-b"))),
                "duplicate sections");
    }

    private static void rejectsConnectorPathMismatch() {
        RuntimeDumpManifest manifest = RuntimeDumpManifest.create(
                "msg_0200",
                "2026-06-14T08:10:00Z",
                "stoneblock4-dev-server",
                "dump_20260614_081000",
                "1.21.1",
                "neoforge",
                "21.1.233",
                List.of());
        assertThrows(IllegalArgumentException.class, () -> manifest.requireConnectorId("other-server"), "connector_id mismatch");
    }

    private static void assertContains(String actual, String expected) {
        if (!actual.contains(expected)) {
            throw new AssertionError("Expected JSON to contain " + expected + " but was " + actual);
        }
    }

    private static void assertEquals(Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + " but got " + actual);
        }
    }

    private static void assertThrows(Class<? extends Throwable> type, Runnable action, String label) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return;
            }
            throw new AssertionError(label + ": expected " + type.getName() + " but got " + error.getClass().getName(), error);
        }
        throw new AssertionError(label + ": expected exception " + type.getName());
    }
}
