package dev.packwise.connector.protocol;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;

public final class AgentHttpClient {
    private final URI baseUri;
    private final HttpClient client;

    public AgentHttpClient(URI baseUri) {
        this(baseUri, Duration.ofSeconds(10));
    }

    public AgentHttpClient(URI baseUri, Duration timeout) {
        this.baseUri = Objects.requireNonNull(baseUri, "baseUri");
        this.client = HttpClient.newBuilder()
                .connectTimeout(Objects.requireNonNull(timeout, "timeout"))
                .build();
    }

    public String sendHello(ConnectorHello hello) throws IOException, InterruptedException {
        return postJson("/v1/connectors/hello", hello.toJson());
    }

    public String sendRuntimeDumpManifest(RuntimeDumpManifest manifest) throws IOException, InterruptedException {
        return postJson("/v1/connectors/" + manifest.connectorId() + "/runtime-dumps", manifest.toJson());
    }

    public String sendRuntimeDumpSection(
            String connectorId,
            String dumpId,
            String sectionName,
            String contentType,
            String body) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(resolve("/v1/connectors/" + connectorId + "/runtime-dumps/" + dumpId + "/sections/" + sectionName))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", contentType)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("Agent returned HTTP " + response.statusCode() + ": " + response.body());
        }
        return response.body();
    }

    public String postJson(String path, String json) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(resolve(path))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", "application/json; charset=utf-8")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("Agent returned HTTP " + response.statusCode() + ": " + response.body());
        }
        return response.body();
    }

    private URI resolve(String path) {
        String normalizedBase = baseUri.toString();
        if (!normalizedBase.endsWith("/")) {
            normalizedBase += "/";
        }
        String normalizedPath = path.startsWith("/") ? path.substring(1) : path;
        return URI.create(normalizedBase).resolve(normalizedPath);
    }
}
