package dev.packwise.connector.protocol;

public final class JsonTextTest {
    public static void main(String[] args) {
        escapesAllJsonControlCharacters();
        roundTripsEscapedControlCharacters();
        readsStringArraysWithBracketsInsideStrings();
        readsObjectArraysWithStringFields();
        System.out.println("JsonTextTest passed");
    }

    private static void escapesAllJsonControlCharacters() {
        String escaped = JsonText.escape("quote\" slash\\ backspace\b formfeed\f newline\n return\r tab\t unit\u0001");

        assertContains(escaped, "quote\\\"");
        assertContains(escaped, "slash\\\\");
        assertContains(escaped, "backspace\\b");
        assertContains(escaped, "formfeed\\f");
        assertContains(escaped, "newline\\n");
        assertContains(escaped, "return\\r");
        assertContains(escaped, "tab\\t");
        assertContains(escaped, "unit\\u0001");
        for (int i = 0; i < escaped.length(); i++) {
            char c = escaped.charAt(i);
            if (c < 0x20) {
                throw new AssertionError("Escaped JSON text still contains raw control char U+" + Integer.toHexString(c));
            }
        }
    }

    private static void roundTripsEscapedControlCharacters() {
        String original = "a\b\f\n\r\t\u0001";
        String roundTrip = JsonText.unescape(JsonText.escape(original));

        assertEquals(original, roundTrip, "round trip");
    }

    private static void readsStringArraysWithBracketsInsideStrings() {
        String json = "{\"next_steps\":[\"检查 tag [forge:stone]\", \"路径 C:\\\\server\\\\packwise\", \"控制\\u0001字符\"]}";

        java.util.List<String> values = JsonText.readStringArrayField(json, "next_steps");

        assertEquals(3, values.size(), "array size");
        assertEquals("检查 tag [forge:stone]", values.get(0), "bracket value");
        assertEquals("路径 C:\\server\\packwise", values.get(1), "slash value");
        assertEquals("控制\u0001字符", values.get(2), "unicode value");
    }

    private static void readsObjectArraysWithStringFields() {
        String json = "{\"source_refs\":[{\"kind\":\"recipe\",\"path\":\"minecraft:stonecutting/stone\",\"label\":\"Stone [runtime]\"},{\"kind\":\"runtime_dump_section\",\"path\":\"dump_1/recipes\",\"label\":\"路径 C:\\\\server\\\\recipes\"}]}";

        java.util.List<java.util.Map<String, String>> values = JsonText.readObjectArrayStringFields(json, "source_refs");

        assertEquals(2, values.size(), "object array size");
        assertEquals("recipe", values.get(0).get("kind"), "first kind");
        assertEquals("Stone [runtime]", values.get(0).get("label"), "first label");
        assertEquals("路径 C:\\server\\recipes", values.get(1).get("label"), "second slash label");
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
}
