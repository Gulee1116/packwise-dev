package dev.packwise.connector.protocol;

import java.util.Map;

public final class QueryAskTest {
    public static void main(String[] args) {
        encodesAskRequest();
        rejectsBlankQuestion();
        System.out.println("QueryAskTest passed");
    }

    private static void encodesAskRequest() {
        QueryAsk ask = QueryAsk.create(
                "msg_ask_1",
                "2026-06-14T08:20:00Z",
                "minecraft:stone 怎么做？",
                "zh_cn",
                Map.of("connector_id", "atm9sky-dev-server", "dump_id", "dump_1"));

        String json = ask.toJson();

        assertContains(json, "\"message_type\":\"query.ask\"");
        assertContains(json, "\"question\":\"minecraft:stone 怎么做？\"");
        assertContains(json, "\"connector_id\":\"atm9sky-dev-server\"");
        assertContains(json, "\"dump_id\":\"dump_1\"");
    }

    private static void rejectsBlankQuestion() {
        assertThrows(IllegalArgumentException.class, () -> QueryAsk.create(
                "msg_ask_1",
                "2026-06-14T08:20:00Z",
                " ",
                "zh_cn",
                Map.of()), "blank question");
    }

    private static void assertContains(String actual, String expected) {
        if (!actual.contains(expected)) {
            throw new AssertionError("Expected JSON to contain " + expected + " but was " + actual);
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
