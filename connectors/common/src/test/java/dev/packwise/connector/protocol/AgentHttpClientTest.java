package dev.packwise.connector.protocol;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;

public final class AgentHttpClientTest {
    public static void main(String[] args) throws Exception {
        postsConnectorHello();
        postsRuntimeDumpManifest();
        postsRuntimeDumpSection();
        encodesRuntimeDumpPathSegments();
        postsAskRequest();
        System.out.println("AgentHttpClientTest passed");
    }

    private static void postsConnectorHello() throws Exception {
        CapturingHandler handler = new CapturingHandler();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/connectors/hello", handler::handle);
        server.start();
        try {
            URI baseUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            AgentHttpClient client = new AgentHttpClient(baseUri);
            ConnectorHello hello = ConnectorHello.create(
                    "msg_0001",
                    "2026-06-14T08:00:00Z",
                    new ConnectorInfo(
                            "stoneblock4-dev-server",
                            ConnectorSide.SERVER,
                            "neoforge",
                            "21.1.233",
                            "1.21.1",
                            "ftb-stoneblock-4",
                            "FTB StoneBlock 4",
                            "1.14.2",
                            List.of("runtime_dump")));

            String response = client.sendHello(hello);

            assertEquals("POST", handler.method, "method");
            assertContains(handler.body, "\"message_type\":\"connector.hello\"");
            assertContains(response, "\"message_type\":\"connector.ack\"");
        } finally {
            server.stop(0);
        }
    }

    private static void postsRuntimeDumpManifest() throws Exception {
        CapturingHandler handler = new CapturingHandler();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/connectors/stoneblock4-dev-server/runtime-dumps", handler::handle);
        server.start();
        try {
            URI baseUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            AgentHttpClient client = new AgentHttpClient(baseUri);
            RuntimeDumpManifest manifest = RuntimeDumpManifest.create(
                    "msg_0200",
                    "2026-06-14T08:10:00Z",
                    "stoneblock4-dev-server",
                    "dump_20260614_081000",
                    "1.21.1",
                    "neoforge",
                    "21.1.233",
                    List.of(new RuntimeDumpSection("mods", "application/x-ndjson", 404, "sha-mods")));

            String response = client.sendRuntimeDumpManifest(manifest);

            assertEquals("POST", handler.method, "method");
            assertContains(handler.body, "\"message_type\":\"runtime_dump.manifest\"");
            assertContains(handler.body, "\"connector_id\":\"stoneblock4-dev-server\"");
            assertContains(response, "\"message_type\":\"runtime_dump.ack\"");
        } finally {
            server.stop(0);
        }
    }

    private static void postsRuntimeDumpSection() throws Exception {
        CapturingHandler handler = new CapturingHandler();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/connectors/stoneblock4-dev-server/runtime-dumps/dump_1/sections/mods", handler::handle);
        server.start();
        try {
            URI baseUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            AgentHttpClient client = new AgentHttpClient(baseUri);
            String body = "{\"mod_id\":\"minecraft\"}\n";

            String response = client.sendRuntimeDumpSection(
                    "stoneblock4-dev-server",
                    "dump_1",
                    "mods",
                    "application/x-ndjson",
                    body);

            assertEquals("POST", handler.method, "method");
            assertContains(handler.body, "\"mod_id\":\"minecraft\"");
            assertEquals("application/x-ndjson", handler.contentType, "content type");
            assertContains(response, "\"message_type\":\"runtime_dump.section_ack\"");
        } finally {
            server.stop(0);
        }
    }

    private static void encodesRuntimeDumpPathSegments() throws Exception {
        CapturingHandler handler = new CapturingHandler();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", handler::handle);
        server.start();
        try {
            URI baseUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            AgentHttpClient client = new AgentHttpClient(baseUri);
            RuntimeDumpManifest manifest = RuntimeDumpManifest.create(
                    "msg_0200",
                    "2026-06-14T08:10:00Z",
                    "forge:alpha/one",
                    "dump 1",
                    "1.20.1",
                    "forge",
                    "47.4.20",
                    List.of(new RuntimeDumpSection("recipes", "application/x-ndjson", 0, "sha-recipes")));

            client.sendRuntimeDumpManifest(manifest);
            assertEquals("/v1/connectors/forge%3Aalpha%2Fone/runtime-dumps", handler.path, "manifest path");

            client.sendRuntimeDumpSection(
                    "forge:alpha/one",
                    "dump 1",
                    "custom/section",
                    "application/x-ndjson",
                    "");
            assertEquals(
                    "/v1/connectors/forge%3Aalpha%2Fone/runtime-dumps/dump%201/sections/custom%2Fsection",
                    handler.path,
                    "section path");
        } finally {
            server.stop(0);
        }
    }

    private static void postsAskRequest() throws Exception {
        CapturingHandler handler = new CapturingHandler();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/query/ask", handler::handle);
        server.start();
        try {
            URI baseUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            AgentHttpClient client = new AgentHttpClient(baseUri);
            QueryAsk ask = QueryAsk.create(
                    "msg_ask_1",
                    "2026-06-14T08:20:00Z",
                    "下一步该干什么？",
                    "zh_cn",
                    java.util.Map.of("connector_id", "atm9sky-dev-server"));

            String response = client.sendAsk(ask);

            assertEquals("POST", handler.method, "method");
            assertContains(handler.body, "\"message_type\":\"query.ask\"");
            assertContains(handler.body, "\"question\":\"下一步该干什么？\"");
            assertContains(response, "\"message_type\":\"answer.packet\"");
        } finally {
            server.stop(0);
        }
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

    private static final class CapturingHandler {
        private String method = "";
        private String path = "";
        private String body = "";
        private String contentType = "";

        private void handle(HttpExchange exchange) throws IOException {
            method = exchange.getRequestMethod();
            path = exchange.getRequestURI().getRawPath();
            contentType = exchange.getRequestHeaders().getFirst("Content-Type");
            body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            String messageType;
            if (exchange.getRequestURI().getPath().contains("/sections/")) {
                messageType = "runtime_dump.section_ack";
            } else if (exchange.getRequestURI().getPath().equals("/v1/query/ask")) {
                messageType = "answer.packet";
            } else if (body.contains("runtime_dump.manifest")) {
                messageType = "runtime_dump.ack";
            } else {
                messageType = "connector.ack";
            }
            byte[] response = ("{\"protocol\":\"packwise.connector.v1\",\"message_type\":\"" + messageType + "\",\"message_id\":\"ack_1\",\"in_reply_to\":\"msg_0001\",\"sent_at\":\"2026-06-14T08:00:01Z\",\"accepted\":true,\"agent\":{\"name\":\"packwise-agent\",\"capabilities\":[\"ask\"]}}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        }
    }
}
