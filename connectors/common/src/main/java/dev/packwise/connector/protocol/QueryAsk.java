package dev.packwise.connector.protocol;

import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public record QueryAsk(
        String protocol,
        String messageType,
        String messageId,
        String sentAt,
        String question,
        String locale,
        Map<String, String> context) {

    public static final String PROTOCOL = "packwise.connector.v1";
    public static final String MESSAGE_TYPE = "query.ask";

    public QueryAsk {
        Objects.requireNonNull(protocol, "protocol");
        Objects.requireNonNull(messageType, "messageType");
        Objects.requireNonNull(messageId, "messageId");
        Objects.requireNonNull(sentAt, "sentAt");
        Objects.requireNonNull(question, "question");
        Objects.requireNonNull(locale, "locale");
        context = Map.copyOf(Objects.requireNonNull(context, "context"));
        if (!PROTOCOL.equals(protocol)) {
            throw new IllegalArgumentException("Expected protocol " + PROTOCOL + " but got " + protocol);
        }
        if (!MESSAGE_TYPE.equals(messageType)) {
            throw new IllegalArgumentException("Expected message_type " + MESSAGE_TYPE + " but got " + messageType);
        }
        if (question.isBlank()) {
            throw new IllegalArgumentException("question must not be blank");
        }
    }

    public static QueryAsk create(
            String messageId,
            String sentAt,
            String question,
            String locale,
            Map<String, String> context) {
        return new QueryAsk(
                PROTOCOL,
                MESSAGE_TYPE,
                messageId,
                sentAt,
                question,
                locale,
                context);
    }

    public String toJson() {
        StringBuilder json = new StringBuilder();
        json.append('{');
        appendField(json, "protocol", protocol).append(',');
        appendField(json, "message_type", messageType).append(',');
        appendField(json, "message_id", messageId).append(',');
        appendField(json, "sent_at", sentAt).append(',');
        appendField(json, "question", question).append(',');
        appendField(json, "locale", locale).append(',');
        json.append("\"context\":{");
        int index = 0;
        for (Map.Entry<String, String> entry : new TreeMap<>(context).entrySet()) {
            if (index > 0) {
                json.append(',');
            }
            appendField(json, entry.getKey(), entry.getValue());
            index++;
        }
        json.append("}}");
        return json.toString();
    }

    private static StringBuilder appendField(StringBuilder json, String key, String value) {
        return json.append('"').append(JsonText.escape(key)).append("\":\"").append(JsonText.escape(value)).append('"');
    }
}
