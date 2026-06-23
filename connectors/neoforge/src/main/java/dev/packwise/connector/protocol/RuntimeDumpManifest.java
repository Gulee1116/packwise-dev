package dev.packwise.connector.protocol;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public record RuntimeDumpManifest(
        String protocol,
        String messageType,
        String messageId,
        String sentAt,
        String connectorId,
        String dumpId,
        String minecraftVersion,
        String loader,
        String loaderVersion,
        List<RuntimeDumpSection> sections) {

    public static final String PROTOCOL = "packwise.connector.v1";
    public static final String MESSAGE_TYPE = "runtime_dump.manifest";

    public RuntimeDumpManifest {
        Objects.requireNonNull(protocol, "protocol");
        Objects.requireNonNull(messageType, "messageType");
        Objects.requireNonNull(messageId, "messageId");
        Objects.requireNonNull(sentAt, "sentAt");
        Objects.requireNonNull(connectorId, "connectorId");
        Objects.requireNonNull(dumpId, "dumpId");
        Objects.requireNonNull(minecraftVersion, "minecraftVersion");
        Objects.requireNonNull(loader, "loader");
        Objects.requireNonNull(loaderVersion, "loaderVersion");
        sections = List.copyOf(Objects.requireNonNull(sections, "sections"));
        if (!PROTOCOL.equals(protocol)) {
            throw new IllegalArgumentException("Expected protocol " + PROTOCOL + " but got " + protocol);
        }
        if (!MESSAGE_TYPE.equals(messageType)) {
            throw new IllegalArgumentException("Expected message_type " + MESSAGE_TYPE + " but got " + messageType);
        }
    }

    public static RuntimeDumpManifest create(
            String messageId,
            String sentAt,
            String connectorId,
            String dumpId,
            String minecraftVersion,
            String loader,
            String loaderVersion,
            List<RuntimeDumpSection> sections) {
        return new RuntimeDumpManifest(
                PROTOCOL,
                MESSAGE_TYPE,
                messageId,
                sentAt,
                connectorId,
                dumpId,
                minecraftVersion,
                loader,
                loaderVersion,
                sections);
    }

    public void requireConnectorId(String expectedConnectorId) {
        if (!connectorId.equals(expectedConnectorId)) {
            throw new IllegalArgumentException("Expected connector_id " + expectedConnectorId + " but got " + connectorId);
        }
    }

    public String toJson() {
        StringBuilder json = new StringBuilder();
        json.append('{');
        appendField(json, "protocol", protocol).append(',');
        appendField(json, "message_type", messageType).append(',');
        appendField(json, "message_id", messageId).append(',');
        appendField(json, "sent_at", sentAt).append(',');
        appendField(json, "connector_id", connectorId).append(',');
        appendField(json, "dump_id", dumpId).append(',');
        appendField(json, "minecraft_version", minecraftVersion).append(',');
        appendField(json, "loader", loader).append(',');
        appendField(json, "loader_version", loaderVersion).append(',');
        json.append("\"sections\":[");
        for (int i = 0; i < sections.size(); i++) {
            RuntimeDumpSection section = sections.get(i);
            if (i > 0) {
                json.append(',');
            }
            json.append('{');
            appendField(json, "name", section.name()).append(',');
            appendField(json, "content_type", section.contentType()).append(',');
            json.append("\"count\":").append(section.count()).append(',');
            appendField(json, "sha256", section.sha256());
            json.append('}');
        }
        json.append("]}");
        return json.toString();
    }

    public static RuntimeDumpManifest fromJson(String json) {
        return new RuntimeDumpManifest(
                readString(json, "protocol"),
                readString(json, "message_type"),
                readString(json, "message_id"),
                readString(json, "sent_at"),
                readString(json, "connector_id"),
                readString(json, "dump_id"),
                readString(json, "minecraft_version"),
                readString(json, "loader"),
                readString(json, "loader_version"),
                readSections(json));
    }

    private static StringBuilder appendField(StringBuilder json, String key, String value) {
        return json.append('"').append(key).append("\":\"").append(escape(value)).append('"');
    }

    private static List<RuntimeDumpSection> readSections(String json) {
        String body = readArrayBody(json, "sections");
        if (body.trim().isEmpty()) {
            return List.of();
        }
        List<RuntimeDumpSection> sections = new ArrayList<>();
        Matcher objectMatcher = Pattern.compile("\\{(.*?)}", Pattern.DOTALL).matcher(body);
        while (objectMatcher.find()) {
            String object = objectMatcher.group(1);
            sections.add(new RuntimeDumpSection(
                    readString(object, "name"),
                    readString(object, "content_type"),
                    readInt(object, "count"),
                    readString(object, "sha256")));
        }
        return sections;
    }

    private static String readArrayBody(String json, String key) {
        int keyIndex = json.indexOf("\"" + key + "\"");
        if (keyIndex < 0) {
            throw new IllegalArgumentException("Missing JSON array field: " + key);
        }
        int open = json.indexOf('[', keyIndex);
        if (open < 0) {
            throw new IllegalArgumentException("Missing JSON array open for: " + key);
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
        throw new IllegalArgumentException("Unterminated JSON array field: " + key);
    }

    private static String readString(String json, String key) {
        Pattern pattern = Pattern.compile("\"" + Pattern.quote(key) + "\"\\s*:\\s*\"((?:\\\\.|[^\"])*)\"");
        Matcher matcher = pattern.matcher(json);
        if (!matcher.find()) {
            throw new IllegalArgumentException("Missing JSON string field: " + key);
        }
        return unescape(matcher.group(1));
    }

    private static int readInt(String json, String key) {
        Pattern pattern = Pattern.compile("\"" + Pattern.quote(key) + "\"\\s*:\\s*(\\d+)");
        Matcher matcher = pattern.matcher(json);
        if (!matcher.find()) {
            throw new IllegalArgumentException("Missing JSON integer field: " + key);
        }
        return Integer.parseInt(matcher.group(1));
    }

    private static String escape(String value) {
        StringBuilder out = new StringBuilder(value.length());
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\' -> out.append("\\\\");
                case '"' -> out.append("\\\"");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> out.append(c);
            }
        }
        return out.toString();
    }

    private static String unescape(String value) {
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
                case 'n' -> out.append('\n');
                case 'r' -> out.append('\r');
                case 't' -> out.append('\t');
                default -> out.append(c);
            }
            escaped = false;
        }
        if (escaped) {
            out.append('\\');
        }
        return out.toString();
    }
}
