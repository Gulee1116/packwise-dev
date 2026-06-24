package dev.packwise.connector.protocol;

import java.util.List;
import java.util.Objects;

public record ConnectorHello(
        String protocol,
        String messageType,
        String messageId,
        String sentAt,
        ConnectorInfo connector) {

    public static final String PROTOCOL = "packwise.connector.v1";
    public static final String MESSAGE_TYPE = "connector.hello";

    public ConnectorHello {
        Objects.requireNonNull(protocol, "protocol");
        Objects.requireNonNull(messageType, "messageType");
        Objects.requireNonNull(messageId, "messageId");
        Objects.requireNonNull(sentAt, "sentAt");
        Objects.requireNonNull(connector, "connector");
        if (!PROTOCOL.equals(protocol)) {
            throw new IllegalArgumentException("Expected protocol " + PROTOCOL + " but got " + protocol);
        }
        if (!MESSAGE_TYPE.equals(messageType)) {
            throw new IllegalArgumentException("Expected message_type " + MESSAGE_TYPE + " but got " + messageType);
        }
    }

    public static ConnectorHello create(String messageId, String sentAt, ConnectorInfo connector) {
        return new ConnectorHello(PROTOCOL, MESSAGE_TYPE, messageId, sentAt, connector);
    }

    public String toJson() {
        StringBuilder json = new StringBuilder();
        json.append('{');
        appendField(json, "protocol", protocol).append(',');
        appendField(json, "message_type", messageType).append(',');
        appendField(json, "message_id", messageId).append(',');
        appendField(json, "sent_at", sentAt).append(',');
        json.append("\"connector\":{");
        appendField(json, "id", connector.id()).append(',');
        appendField(json, "side", connector.side().wireValue()).append(',');
        appendField(json, "loader", connector.loader()).append(',');
        appendField(json, "loader_version", connector.loaderVersion()).append(',');
        appendField(json, "minecraft_version", connector.minecraftVersion()).append(',');
        appendField(json, "pack_id", connector.packId()).append(',');
        appendField(json, "pack_name", connector.packName()).append(',');
        appendField(json, "pack_version", connector.packVersion()).append(',');
        appendField(json, "connector_mod_id", connector.connectorModId()).append(',');
        appendField(json, "connector_version", connector.connectorVersion()).append(',');
        json.append("\"capabilities\":[");
        for (int i = 0; i < connector.capabilities().size(); i++) {
            if (i > 0) {
                json.append(',');
            }
            json.append('"').append(JsonText.escape(connector.capabilities().get(i))).append('"');
        }
        json.append("]}}");
        return json.toString();
    }

    public static ConnectorHello fromJson(String json) {
        String protocol = readString(json, "protocol");
        String messageType = readString(json, "message_type");
        String messageId = readString(json, "message_id");
        String sentAt = readString(json, "sent_at");
        ConnectorInfo connector = new ConnectorInfo(
                readString(json, "id"),
                ConnectorSide.fromWireValue(readString(json, "side")),
                readString(json, "loader"),
                readString(json, "loader_version"),
                readString(json, "minecraft_version"),
                readString(json, "pack_id"),
                readString(json, "pack_name"),
                readString(json, "pack_version"),
                JsonText.readStringField(json, "connector_mod_id").orElse("unknown"),
                JsonText.readStringField(json, "connector_version").orElse("unknown"),
                readStringArray(json, "capabilities"));
        return new ConnectorHello(protocol, messageType, messageId, sentAt, connector);
    }

    private static StringBuilder appendField(StringBuilder json, String key, String value) {
        return json.append('"').append(key).append("\":\"").append(JsonText.escape(value)).append('"');
    }

    private static String readString(String json, String key) {
        return JsonText.readStringField(json, key)
                .orElseThrow(() -> new IllegalArgumentException("Missing JSON string field: " + key));
    }

    private static List<String> readStringArray(String json, String key) {
        if (!json.contains("\"" + key + "\"")) {
            throw new IllegalArgumentException("Missing JSON array field: " + key);
        }
        return JsonText.readStringArrayField(json, key);
    }
}
