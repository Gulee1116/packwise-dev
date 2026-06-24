package dev.packwise.connector.protocol;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class RuntimeDumpFileWriterTest {
    public static void main(String[] args) throws Exception {
        writesManifestAndSectionFiles();
        writesCustomNonNdjsonSectionsAsTextFiles();
        rejectsDumpIdsThatResolveToCurrentOrParentDirectory();
        rejectsSectionNamesThatResolveToSameFile();
        System.out.println("RuntimeDumpFileWriterTest passed");
    }

    private static void writesManifestAndSectionFiles() throws Exception {
        Path root = Files.createTempDirectory("packwise-dump-writer-test");
        RuntimeDumpContent mods = ModsSectionDumper.dump(List.of(
                new ModSnapshot("minecraft", "Minecraft", "1.20.1", "builtin")));

        Path dumpDirectory = new RuntimeDumpFileWriter().write(
                root,
                "msg_0200",
                "2026-06-14T08:10:00Z",
                new ConnectorInfo(
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
                        List.of("runtime_dump", "commands")),
                "dump_test",
                List.of(mods));

        String manifest = Files.readString(dumpDirectory.resolve("manifest.json"));
        String modsBody = Files.readString(dumpDirectory.resolve("mods.ndjson"));

        assertContains(manifest, "\"message_type\":\"runtime_dump.manifest\"");
        assertContains(manifest, "\"connector_id\":\"atm9sky-dev-server\"");
        assertContains(manifest, "\"connector_mod_id\":\"packwise_connector\"");
        assertContains(manifest, "\"connector_version\":\"0.1.0\"");
        assertContains(manifest, "\"name\":\"mods\"");
        assertContains(modsBody, "\"mod_id\":\"minecraft\"");
    }

    private static void writesCustomNonNdjsonSectionsAsTextFiles() throws Exception {
        Path root = Files.createTempDirectory("packwise-dump-writer-text-test");
        String body = "diagnostic note\n";
        RuntimeDumpContent notes = new RuntimeDumpContent(
                "diagnostic/notes",
                "text/plain",
                body,
                1,
                NdjsonSectionDumper.sha256(body));

        Path dumpDirectory = new RuntimeDumpFileWriter().write(
                root,
                "msg_0200",
                "2026-06-14T08:10:00Z",
                "forge-test-server",
                "dump_test",
                "1.20.1",
                "forge",
                "47.4.20",
                List.of(notes));

        String manifest = Files.readString(dumpDirectory.resolve("manifest.json"));
        String notesBody = Files.readString(dumpDirectory.resolve("diagnostic_notes.txt"));

        assertContains(manifest, "\"name\":\"diagnostic/notes\"");
        assertContains(manifest, "\"content_type\":\"text/plain\"");
        assertContains(notesBody, "diagnostic note");
    }

    private static void rejectsDumpIdsThatResolveToCurrentOrParentDirectory() throws Exception {
        Path root = Files.createTempDirectory("packwise-dump-writer-segment-test");
        RuntimeDumpContent mods = ModsSectionDumper.dump(List.of(
                new ModSnapshot("minecraft", "Minecraft", "1.20.1", "builtin")));
        RuntimeDumpFileWriter writer = new RuntimeDumpFileWriter();

        assertThrows(
                IllegalArgumentException.class,
                () -> writeUnchecked(writer, root, ".", mods),
                "current directory dump id");
        assertThrows(
                IllegalArgumentException.class,
                () -> writeUnchecked(writer, root, "..", mods),
                "parent directory dump id");
    }

    private static void rejectsSectionNamesThatResolveToSameFile() throws Exception {
        Path root = Files.createTempDirectory("packwise-dump-writer-collision-test");
        String body = "diagnostic note\n";
        RuntimeDumpContent notesA = new RuntimeDumpContent(
                "diagnostic/notes",
                "text/plain",
                body,
                1,
                NdjsonSectionDumper.sha256(body));
        RuntimeDumpContent notesB = new RuntimeDumpContent(
                "diagnostic_notes",
                "text/plain",
                body,
                1,
                NdjsonSectionDumper.sha256(body));
        RuntimeDumpFileWriter writer = new RuntimeDumpFileWriter();

        assertThrows(
                IllegalArgumentException.class,
                () -> writeUnchecked(writer, root, "dump_test", notesA, notesB),
                "section filename collision");
    }

    private static void writeUnchecked(
            RuntimeDumpFileWriter writer,
            Path root,
            String dumpId,
            RuntimeDumpContent... contents) {
        try {
            writer.write(
                    root,
                    "msg_0200",
                    "2026-06-14T08:10:00Z",
                    "forge-test-server",
                    dumpId,
                    "1.20.1",
                    "forge",
                    "47.4.20",
                    List.of(contents));
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new RuntimeException(error);
        }
    }

    private static void assertContains(String actual, String expected) {
        if (!actual.contains(expected)) {
            throw new AssertionError("Expected text to contain " + expected + " but was " + actual);
        }
    }

    private static void assertThrows(Class<? extends Throwable> type, Runnable action, String label) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return;
            }
            throw new AssertionError(
                    label + ": expected " + type.getName() + " but got " + error.getClass().getName(),
                    error);
        }
        throw new AssertionError(label + ": expected exception " + type.getName());
    }
}
