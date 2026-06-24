package dev.packwise.connector.forge;

import dev.packwise.connector.protocol.JsonText;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Optional;

public record ForgePackMetadata(String packId, String packName, String packVersion) {
    public static final ForgePackMetadata UNKNOWN = new ForgePackMetadata("unknown-pack", "Unknown Pack", "unknown");

    public static ForgePackMetadata detect(Path root) {
        for (String filename : new String[]{"modpackinfo.json", "manifest.json", "modrinth.index.json"}) {
            Optional<ForgePackMetadata> detected = detectFile(root.resolve(filename), filename);
            if (detected.isPresent()) {
                return detected.get();
            }
        }
        return UNKNOWN;
    }

    private static Optional<ForgePackMetadata> detectFile(Path path, String filename) {
        if (!Files.isRegularFile(path)) {
            return Optional.empty();
        }
        try {
            String json = Files.readString(path);
            return switch (filename) {
                case "modpackinfo.json" -> fromNameVersion(
                        objectStringField(json, "modpack", "name")
                                .or(() -> topLevelStringField(json, "name"))
                                .orElse(""),
                        objectStringField(json, "modpack", "version")
                                .or(() -> topLevelStringField(json, "version"))
                                .orElse(""));
                case "manifest.json" -> fromNameVersion(
                        topLevelStringField(json, "name").orElse(""),
                        topLevelStringField(json, "version").orElse(""));
                case "modrinth.index.json" -> fromNameVersion(
                        topLevelStringField(json, "name").orElse(""),
                        topLevelStringField(json, "versionId")
                                .or(() -> topLevelStringField(json, "version"))
                                .orElse(""));
                default -> Optional.empty();
            };
        } catch (IOException error) {
            return Optional.empty();
        }
    }

    private static Optional<ForgePackMetadata> fromNameVersion(String name, String version) {
        if (name == null || name.isBlank()) {
            return Optional.empty();
        }
        String normalizedVersion = version == null || version.isBlank() ? "unknown" : version;
        return Optional.of(new ForgePackMetadata(slug(name), name, normalizedVersion));
    }

    private static String slug(String value) {
        StringBuilder slug = new StringBuilder();
        boolean previousDash = false;
        String lower = value.toLowerCase(Locale.ROOT);
        for (int i = 0; i < lower.length(); i++) {
            char c = lower.charAt(i);
            if (Character.isLetterOrDigit(c)) {
                slug.append(c);
                previousDash = false;
            } else if (!previousDash) {
                slug.append('-');
                previousDash = true;
            }
        }
        String result = slug.toString().replaceAll("^-+|-+$", "");
        return result.isBlank() ? "unknown-pack" : result;
    }

    private static Optional<String> objectStringField(String json, String objectKey, String fieldKey) {
        return objectBody(json, objectKey).flatMap(body -> topLevelStringField(body, fieldKey));
    }

    private static Optional<String> topLevelStringField(String json, String key) {
        int depth = 0;
        boolean inString = false;
        boolean escaped = false;
        for (int i = 0; i < json.length(); i++) {
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
                if (!inString && depth == 1) {
                    int end = stringEnd(json, i + 1);
                    if (end < 0) {
                        return Optional.empty();
                    }
                    String candidateKey = JsonText.unescape(json.substring(i + 1, end));
                    int colon = nextNonWhitespace(json, end + 1);
                    if (candidateKey.equals(key) && colon < json.length() && json.charAt(colon) == ':') {
                        int valueStart = nextNonWhitespace(json, colon + 1);
                        if (valueStart < json.length() && json.charAt(valueStart) == '"') {
                            int valueEnd = stringEnd(json, valueStart + 1);
                            if (valueEnd >= 0) {
                                return Optional.of(JsonText.unescape(json.substring(valueStart + 1, valueEnd)));
                            }
                        }
                    }
                    i = end;
                    continue;
                }
                inString = !inString;
                continue;
            }
            if (inString) {
                continue;
            }
            if (c == '{' || c == '[') {
                depth++;
            } else if (c == '}' || c == ']') {
                depth--;
            }
        }
        return Optional.empty();
    }

    private static Optional<String> objectBody(String json, String key) {
        int depth = 0;
        boolean inString = false;
        boolean escaped = false;
        for (int i = 0; i < json.length(); i++) {
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
                if (!inString && depth == 1) {
                    int end = stringEnd(json, i + 1);
                    if (end < 0) {
                        return Optional.empty();
                    }
                    String candidateKey = JsonText.unescape(json.substring(i + 1, end));
                    int colon = nextNonWhitespace(json, end + 1);
                    if (candidateKey.equals(key) && colon < json.length() && json.charAt(colon) == ':') {
                        int valueStart = nextNonWhitespace(json, colon + 1);
                        if (valueStart < json.length() && json.charAt(valueStart) == '{') {
                            int valueEnd = matchingEnd(json, valueStart, '{', '}');
                            if (valueEnd >= 0) {
                                return Optional.of(json.substring(valueStart, valueEnd + 1));
                            }
                        }
                    }
                    i = end;
                    continue;
                }
                inString = !inString;
                continue;
            }
            if (inString) {
                continue;
            }
            if (c == '{' || c == '[') {
                depth++;
            } else if (c == '}' || c == ']') {
                depth--;
            }
        }
        return Optional.empty();
    }

    private static int matchingEnd(String json, int start, char openChar, char closeChar) {
        int depth = 0;
        boolean inString = false;
        boolean escaped = false;
        for (int i = start; i < json.length(); i++) {
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
            if (c == openChar) {
                depth++;
            } else if (c == closeChar) {
                depth--;
                if (depth == 0) {
                    return i;
                }
            }
        }
        return -1;
    }

    private static int stringEnd(String json, int start) {
        boolean escaped = false;
        for (int i = start; i < json.length(); i++) {
            char c = json.charAt(i);
            if (escaped) {
                escaped = false;
                continue;
            }
            if (c == '\\') {
                escaped = true;
                continue;
            }
            if (c == '"') {
                return i;
            }
        }
        return -1;
    }

    private static int nextNonWhitespace(String json, int start) {
        int index = start;
        while (index < json.length() && Character.isWhitespace(json.charAt(index))) {
            index++;
        }
        return index;
    }

}
