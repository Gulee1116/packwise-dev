package dev.packwise.connector.protocol;

import java.util.List;

public final class RuntimeDumpManifestTest {
    public static void main(String[] args) {
        roundTripsRuntimeDumpManifest();
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
                List.of(
                        new RuntimeDumpSection("mods", "application/x-ndjson", 404, "sha-mods"),
                        new RuntimeDumpSection("recipes", "application/x-ndjson", 8000, "sha-recipes")));

        String json = manifest.toJson();
        assertContains(json, "\"message_type\":\"runtime_dump.manifest\"");
        assertContains(json, "\"connector_id\":\"stoneblock4-dev-server\"");
        assertContains(json, "\"name\":\"recipes\"");

        RuntimeDumpManifest decoded = RuntimeDumpManifest.fromJson(json);
        assertEquals("msg_0200", decoded.messageId(), "message_id");
        assertEquals("stoneblock4-dev-server", decoded.connectorId(), "connector_id");
        assertEquals("dump_20260614_081000", decoded.dumpId(), "dump_id");
        assertEquals("21.1.233", decoded.loaderVersion(), "loader_version");
        assertEquals(2, decoded.sections().size(), "sections size");
        assertEquals("mods", decoded.sections().get(0).name(), "first section name");
        assertEquals(8000, decoded.sections().get(1).count(), "second section count");
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
