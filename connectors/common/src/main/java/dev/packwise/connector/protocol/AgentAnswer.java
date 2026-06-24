package dev.packwise.connector.protocol;

import java.util.List;
import java.util.Map;
import java.util.Objects;

public record AgentAnswer(
        String summary,
        List<String> nextSteps,
        String confidence,
        List<SourceRef> sourceRefs) {

    public AgentAnswer {
        Objects.requireNonNull(summary, "summary");
        nextSteps = List.copyOf(Objects.requireNonNull(nextSteps, "nextSteps"));
        Objects.requireNonNull(confidence, "confidence");
        sourceRefs = List.copyOf(Objects.requireNonNull(sourceRefs, "sourceRefs"));
    }

    public static AgentAnswer fromAnswerPacketJson(String json) {
        return new AgentAnswer(
                JsonText.readStringField(json, "summary").orElse("Agent response did not include answer.summary."),
                JsonText.readStringArrayField(json, "next_steps"),
                JsonText.readStringField(json, "confidence").orElse("unknown"),
                JsonText.readObjectArrayStringFields(json, "source_refs").stream()
                        .map(SourceRef::fromFields)
                        .toList());
    }

    public record SourceRef(String kind, String path, String label) {
        public SourceRef {
            Objects.requireNonNull(kind, "kind");
            Objects.requireNonNull(path, "path");
            Objects.requireNonNull(label, "label");
        }

        private static SourceRef fromFields(Map<String, String> fields) {
            String kind = fields.getOrDefault("kind", "source");
            String path = fields.getOrDefault("path", "");
            String label = fields.getOrDefault("label", path.isBlank() ? kind : path);
            return new SourceRef(kind, path, label);
        }

        public String compact() {
            if (path.isBlank()) {
                return kind + ":" + label;
            }
            return kind + ":" + path;
        }
    }
}
