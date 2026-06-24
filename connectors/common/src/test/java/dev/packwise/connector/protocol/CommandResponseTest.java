package dev.packwise.connector.protocol;

import java.util.List;

public final class CommandResponseTest {
    public static void main(String[] args) {
        encodesCommandResponse();
        System.out.println("CommandResponseTest passed");
    }

    private static void encodesCommandResponse() {
        CommandResponse response = new CommandResponse(true, "runtime dump uploaded", List.of("mods=2", "recipes=8"));

        String json = response.toJson();

        assertContains(json, "\"accepted\":true");
        assertContains(json, "\"summary\":\"runtime dump uploaded\"");
        assertContains(json, "\"mods=2\"");
    }

    private static void assertContains(String actual, String expected) {
        if (!actual.contains(expected)) {
            throw new AssertionError("Expected JSON to contain " + expected + " but was " + actual);
        }
    }
}
