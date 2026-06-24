package dev.packwise.connector.protocol;

import java.util.List;
import java.util.Objects;

public record CommandResponse(
        boolean accepted,
        String summary,
        List<String> details) {

    public CommandResponse {
        Objects.requireNonNull(summary, "summary");
        details = List.copyOf(Objects.requireNonNull(details, "details"));
    }

    public String toJson() {
        StringBuilder json = new StringBuilder();
        json.append('{');
        json.append("\"accepted\":").append(accepted).append(',');
        json.append("\"summary\":\"").append(JsonText.escape(summary)).append("\",");
        json.append("\"details\":[");
        for (int i = 0; i < details.size(); i++) {
            if (i > 0) {
                json.append(',');
            }
            json.append('"').append(JsonText.escape(details.get(i))).append('"');
        }
        json.append("]}");
        return json.toString();
    }
}
