package dev.packwise.connector.protocol;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public final class RuntimeDumpUploaderTest {
    public static void main(String[] args) throws Exception {
        uploadsManifestThenSections();
        uploadsConnectorHelloBeforeManifestWhenConnectorInfoIsProvided();
        System.out.println("RuntimeDumpUploaderTest passed");
    }

    private static void uploadsManifestThenSections() throws Exception {
        CapturingHandler handler = new CapturingHandler();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/connectors/stoneblock4-dev-server/runtime-dumps", handler::handle);
        server.createContext("/v1/connectors/stoneblock4-dev-server/runtime-dumps/dump_1/sections/mods", handler::handle);
        server.start();
        try {
            AgentHttpClient client = new AgentHttpClient(URI.create("http://127.0.0.1:" + server.getAddress().getPort()));
            RuntimeDumpUploader uploader = new RuntimeDumpUploader(client);
            RuntimeDumpContent mods = ModsSectionDumper.dump(List.of(new ModSnapshot("minecraft", "Minecraft", "1.21.1", "builtin")));

            RuntimeDumpUploadResult result = uploader.upload(
                    "msg_0200",
                    "2026-06-14T08:10:00Z",
                    "stoneblock4-dev-server",
                    "dump_1",
                    "1.21.1",
                    "neoforge",
                    "21.1.233",
                    List.of(mods));

            assertEquals(2, handler.requests.size(), "request count");
            assertContains(handler.requests.get(0).body, "\"message_type\":\"runtime_dump.manifest\"");
            assertContains(handler.requests.get(1).body, "\"mod_id\":\"minecraft\"");
            assertEquals(1, result.sectionResponses().size(), "section responses");
        } finally {
            server.stop(0);
        }
    }

    private static void uploadsConnectorHelloBeforeManifestWhenConnectorInfoIsProvided() throws Exception {
        CapturingHandler handler = new CapturingHandler();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/connectors/hello", handler::handle);
        server.createContext("/v1/connectors/atm9sky-dev-server/runtime-dumps", handler::handle);
        server.createContext("/v1/connectors/atm9sky-dev-server/runtime-dumps/dump_1/sections/mods", handler::handle);
        server.start();
        try {
            AgentHttpClient client = new AgentHttpClient(URI.create("http://127.0.0.1:" + server.getAddress().getPort()));
            RuntimeDumpUploader uploader = new RuntimeDumpUploader(client);
            RuntimeDumpContent mods = ModsSectionDumper.dump(List.of(new ModSnapshot("minecraft", "Minecraft", "1.20.1", "builtin")));
            ConnectorInfo connector = new ConnectorInfo(
                    "atm9sky-dev-server",
                    ConnectorSide.SERVER,
                    "forge",
                    "47.4.20",
                    "1.20.1",
                    "atm9sky",
                    "All the Mods 9 - To the Sky",
                    "1.1.0",
                    "packwise_connector",
                    "0.1.0",
                    List.of("runtime_dump", "commands"));

            RuntimeDumpUploadResult result = uploader.upload(
                    "msg_0200",
                    "2026-06-14T08:10:00Z",
                    connector,
                    "dump_1",
                    List.of(mods));

            assertEquals(3, handler.requests.size(), "request count");
            assertEquals("/v1/connectors/hello", handler.requests.get(0).path, "hello path");
            assertContains(handler.requests.get(0).body, "\"message_type\":\"connector.hello\"");
            assertContains(handler.requests.get(0).body, "\"pack_id\":\"atm9sky\"");
            assertContains(handler.requests.get(0).body, "\"connector_mod_id\":\"packwise_connector\"");
            assertContains(handler.requests.get(0).body, "\"connector_version\":\"0.1.0\"");
            assertContains(handler.requests.get(1).body, "\"message_type\":\"runtime_dump.manifest\"");
            assertContains(handler.requests.get(1).body, "\"connector_mod_id\":\"packwise_connector\"");
            assertContains(handler.requests.get(1).body, "\"connector_version\":\"0.1.0\"");
            assertContains(handler.requests.get(2).body, "\"mod_id\":\"minecraft\"");
            assertContains(result.helloResponse(), "\"message_type\":\"connector.ack\"");
            assertEquals(1, result.sectionResponses().size(), "section responses");
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
        private final List<RequestRecord> requests = new ArrayList<>();

        private void handle(HttpExchange exchange) throws IOException {
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            requests.add(new RequestRecord(exchange.getRequestURI().getPath(), body));
            String path = exchange.getRequestURI().getPath();
            String type;
            if (path.equals("/v1/connectors/hello")) {
                type = "connector.ack";
            } else if (path.contains("/sections/")) {
                type = "runtime_dump.section_ack";
            } else {
                type = "runtime_dump.ack";
            }
            byte[] response = ("{\"protocol\":\"packwise.connector.v1\",\"message_type\":\"" + type + "\",\"message_id\":\"ack\",\"sent_at\":\"2026-06-14T08:10:01Z\",\"accepted\":true}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        }
    }

    private record RequestRecord(String path, String body) {
    }
}
