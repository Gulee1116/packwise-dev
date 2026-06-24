package dev.packwise.connector.protocol;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class JsonText {
    private static final Pattern STRING_FIELD_PATTERN = Pattern.compile("\"((?:\\\\.|[^\"])*)\"\\s*:\\s*\"((?:\\\\.|[^\"])*)\"");

    private JsonText() {
    }

    public static String escape(String value) {
        StringBuilder out = new StringBuilder(value.length());
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\' -> out.append("\\\\");
                case '"' -> out.append("\\\"");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        appendUnicodeEscape(out, c);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.toString();
    }

    public static Optional<String> readStringField(String json, String key) {
        Pattern pattern = Pattern.compile("\"" + Pattern.quote(key) + "\"\\s*:\\s*\"((?:\\\\.|[^\"])*)\"");
        Matcher matcher = pattern.matcher(json);
        if (!matcher.find()) {
            return Optional.empty();
        }
        return Optional.of(unescape(matcher.group(1)));
    }

    public static List<String> readStringArrayField(String json, String key) {
        String body = readArrayBody(json, key);
        if (body == null || body.trim().isEmpty()) {
            return List.of();
        }

        List<String> values = new ArrayList<>();
        for (int i = 0; i < body.length(); i++) {
            if (body.charAt(i) != '"') {
                continue;
            }
            StringBuilder value = new StringBuilder();
            boolean escaped = false;
            for (i = i + 1; i < body.length(); i++) {
                char c = body.charAt(i);
                if (escaped) {
                    value.append('\\').append(c);
                    escaped = false;
                    continue;
                }
                if (c == '\\') {
                    escaped = true;
                    continue;
                }
                if (c == '"') {
                    values.add(unescape(value.toString()));
                    break;
                }
                value.append(c);
            }
        }
        return values;
    }

    public static List<Map<String, String>> readObjectArrayStringFields(String json, String key) {
        String body = readArrayBody(json, key);
        if (body == null || body.trim().isEmpty()) {
            return List.of();
        }

        List<Map<String, String>> values = new ArrayList<>();
        for (String objectBody : objectBodies(body)) {
            Map<String, String> fields = new LinkedHashMap<>();
            Matcher matcher = STRING_FIELD_PATTERN.matcher(objectBody);
            while (matcher.find()) {
                fields.put(unescape(matcher.group(1)), unescape(matcher.group(2)));
            }
            if (!fields.isEmpty()) {
                values.add(Map.copyOf(fields));
            }
        }
        return List.copyOf(values);
    }

    public static String unescape(String value) {
        StringBuilder out = new StringBuilder(value.length());
        boolean escaped = false;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (!escaped) {
                if (c == '\\') {
                    escaped = true;
                } else {
                    out.append(c);
                }
                continue;
            }
            switch (c) {
                case '\\' -> out.append('\\');
                case '"' -> out.append('"');
                case 'b' -> out.append('\b');
                case 'f' -> out.append('\f');
                case 'n' -> out.append('\n');
                case 'r' -> out.append('\r');
                case 't' -> out.append('\t');
                case 'u' -> {
                    if (i + 4 <= value.length() - 1 && isHex(value, i + 1, i + 5)) {
                        out.append((char) Integer.parseInt(value.substring(i + 1, i + 5), 16));
                        i += 4;
                    } else {
                        out.append('u');
                    }
                }
                default -> out.append(c);
            }
            escaped = false;
        }
        if (escaped) {
            out.append('\\');
        }
        return out.toString();
    }

    private static void appendUnicodeEscape(StringBuilder out, char c) {
        out.append("\\u");
        String hex = Integer.toHexString(c);
        for (int i = hex.length(); i < 4; i++) {
            out.append('0');
        }
        out.append(hex);
    }

    private static String readArrayBody(String json, String key) {
        int keyIndex = json.indexOf("\"" + key + "\"");
        if (keyIndex < 0) {
            return null;
        }
        int open = json.indexOf('[', keyIndex);
        if (open < 0) {
            return null;
        }
        int depth = 0;
        boolean inString = false;
        boolean escaped = false;
        for (int i = open; i < json.length(); i++) {
            char c = json.charAt(i);
            if (escaped) {
                escaped = false;
                continue;
            }
            if (c == '\\' && inString) {
                escaped = true;
                continue;
            }
            if (c == '"') {
                inString = !inString;
                continue;
            }
            if (inString) {
                continue;
            }
            if (c == '[') {
                depth++;
            } else if (c == ']') {
                depth--;
                if (depth == 0) {
                    return json.substring(open + 1, i);
                }
            }
        }
        return null;
    }

    private static List<String> objectBodies(String body) {
        List<String> values = new ArrayList<>();
        int depth = 0;
        int open = -1;
        boolean inString = false;
        boolean escaped = false;
        for (int i = 0; i < body.length(); i++) {
            char c = body.charAt(i);
            if (escaped) {
                escaped = false;
                continue;
            }
            if (c == '\\' && inString) {
                escaped = true;
                continue;
            }
            if (c == '"') {
                inString = !inString;
                continue;
            }
            if (inString) {
                continue;
            }
            if (c == '{') {
                if (depth == 0) {
                    open = i;
                }
                depth++;
            } else if (c == '}') {
                depth--;
                if (depth == 0 && open >= 0) {
                    values.add(body.substring(open + 1, i));
                    open = -1;
                }
            }
        }
        return values;
    }

    private static boolean isHex(String value, int startInclusive, int endExclusive) {
        for (int i = startInclusive; i < endExclusive; i++) {
            char c = value.charAt(i);
            boolean hex = (c >= '0' && c <= '9')
                    || (c >= 'a' && c <= 'f')
                    || (c >= 'A' && c <= 'F');
            if (!hex) {
                return false;
            }
        }
        return true;
    }
}
