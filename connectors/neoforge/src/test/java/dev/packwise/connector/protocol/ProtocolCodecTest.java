package dev.packwise.connector.protocol;

import java.util.List;

public final class ProtocolCodecTest {
    public static void main(String[] args) {
        roundTripsConnectorHello();
        rejectsUnsupportedProtocol();
        System.out.println("ProtocolCodecTest passed");
    }

    private static void roundTripsConnectorHello() {
        ConnectorHello hello = ConnectorHello.create(
                "msg_0001",
                "2026-06-14T08:00:00Z",
                new ConnectorInfo(
                        "stoneblock4-dev-server",
                        ConnectorSide.SERVER,
                        "neoforge",
                        "21.1.233",
                        "1.21.1",
                        "ftb-stoneblock-4",
                        "FTB StoneBlock 4",
                        "1.14.2",
                        List.of("runtime_dump", "commands", "server_progress", "quest_progress", "stage_state")));

        String json = hello.toJson();
        assertContains(json, "\"protocol\":\"packwise.connector.v1\"");
        assertContains(json, "\"message_type\":\"connector.hello\"");
        assertContains(json, "\"side\":\"server\"");
        assertContains(json, "\"loader_version\":\"21.1.233\"");

        ConnectorHello decoded = ConnectorHello.fromJson(json);
        assertEquals("msg_0001", decoded.messageId(), "message_id");
        assertEquals("2026-06-14T08:00:00Z", decoded.sentAt(), "sent_at");
        assertEquals("stoneblock4-dev-server", decoded.connector().id(), "connector.id");
        assertEquals(ConnectorSide.SERVER, decoded.connector().side(), "connector.side");
        assertEquals("neoforge", decoded.connector().loader(), "connector.loader");
        assertEquals("21.1.233", decoded.connector().loaderVersion(), "connector.loader_version");
        assertEquals("1.21.1", decoded.connector().minecraftVersion(), "connector.minecraft_version");
        assertEquals("FTB StoneBlock 4", decoded.connector().packName(), "connector.pack_name");
        assertTrue(decoded.connector().capabilities().contains("runtime_dump"), "capabilities include runtime_dump");
    }

    private static void rejectsUnsupportedProtocol() {
        String wrong = "{\"protocol\":\"packwise.connector.v0\",\"message_type\":\"connector.hello\",\"message_id\":\"bad\",\"sent_at\":\"2026-06-14T08:00:00Z\",\"connector\":{\"id\":\"c\",\"side\":\"server\",\"loader\":\"neoforge\",\"loader_version\":\"21.1.233\",\"minecraft_version\":\"1.21.1\",\"pack_id\":\"p\",\"pack_name\":\"p\",\"pack_version\":\"1\",\"capabilities\":[]}}";
        assertThrows(IllegalArgumentException.class, () -> ConnectorHello.fromJson(wrong), "unsupported protocol");
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

    private static void assertTrue(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
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
