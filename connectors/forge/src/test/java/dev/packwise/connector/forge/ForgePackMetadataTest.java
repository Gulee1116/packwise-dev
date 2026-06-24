package dev.packwise.connector.forge;

import java.nio.file.Files;
import java.nio.file.Path;

public final class ForgePackMetadataTest {
    public static void main(String[] args) throws Exception {
        detectsPclModpackInfo();
        detectsTopLevelModpackInfo();
        detectsCurseForgeManifest();
        detectsCurseForgeManifestVersionWhenMinecraftVersionAppearsFirst();
        detectsModrinthIndex();
        fallsBackWhenNoMetadataExists();
        System.out.println("ForgePackMetadataTest passed");
    }

    private static void detectsPclModpackInfo() throws Exception {
        Path root = Files.createTempDirectory("packwise-forge-metadata");
        Files.writeString(
                root.resolve("modpackinfo.json"),
                "{\"modpack\":{\"name\":\"All the Mods 9 - To the Sky\",\"version\":\"1.1.0\"}}\n");

        ForgePackMetadata metadata = ForgePackMetadata.detect(root);

        assertEquals("all-the-mods-9-to-the-sky", metadata.packId(), "pack id");
        assertEquals("All the Mods 9 - To the Sky", metadata.packName(), "pack name");
        assertEquals("1.1.0", metadata.packVersion(), "pack version");
    }

    private static void detectsTopLevelModpackInfo() throws Exception {
        Path root = Files.createTempDirectory("packwise-forge-metadata");
        Files.writeString(
                root.resolve("modpackinfo.json"),
                "{\"name\":\"Top Level Pack\",\"version\":\"4.5.6\"}\n");

        ForgePackMetadata metadata = ForgePackMetadata.detect(root);

        assertEquals("top-level-pack", metadata.packId(), "pack id");
        assertEquals("Top Level Pack", metadata.packName(), "pack name");
        assertEquals("4.5.6", metadata.packVersion(), "pack version");
    }

    private static void detectsCurseForgeManifest() throws Exception {
        Path root = Files.createTempDirectory("packwise-forge-metadata");
        Files.writeString(
                root.resolve("manifest.json"),
                "{\"name\":\"Second Forge Pack\",\"version\":\"2.0.0\",\"minecraft\":{\"version\":\"1.20.1\"}}\n");

        ForgePackMetadata metadata = ForgePackMetadata.detect(root);

        assertEquals("second-forge-pack", metadata.packId(), "pack id");
        assertEquals("Second Forge Pack", metadata.packName(), "pack name");
        assertEquals("2.0.0", metadata.packVersion(), "pack version");
    }

    private static void detectsCurseForgeManifestVersionWhenMinecraftVersionAppearsFirst() throws Exception {
        Path root = Files.createTempDirectory("packwise-forge-metadata");
        Files.writeString(
                root.resolve("manifest.json"),
                "{\"minecraft\":{\"version\":\"1.20.1\"},\"name\":\"Second Forge Pack\",\"version\":\"2.0.0\"}\n");

        ForgePackMetadata metadata = ForgePackMetadata.detect(root);

        assertEquals("second-forge-pack", metadata.packId(), "pack id");
        assertEquals("Second Forge Pack", metadata.packName(), "pack name");
        assertEquals("2.0.0", metadata.packVersion(), "pack version");
    }

    private static void detectsModrinthIndex() throws Exception {
        Path root = Files.createTempDirectory("packwise-forge-metadata");
        Files.writeString(
                root.resolve("modrinth.index.json"),
                "{\"name\":\"Sky Dev Pack\",\"versionId\":\"3.0.1\",\"dependencies\":{\"minecraft\":\"1.20.1\"}}\n");

        ForgePackMetadata metadata = ForgePackMetadata.detect(root);

        assertEquals("sky-dev-pack", metadata.packId(), "pack id");
        assertEquals("Sky Dev Pack", metadata.packName(), "pack name");
        assertEquals("3.0.1", metadata.packVersion(), "pack version");
    }

    private static void fallsBackWhenNoMetadataExists() throws Exception {
        Path root = Files.createTempDirectory("packwise-forge-metadata");

        ForgePackMetadata metadata = ForgePackMetadata.detect(root);

        assertEquals("unknown-pack", metadata.packId(), "pack id");
        assertEquals("Unknown Pack", metadata.packName(), "pack name");
        assertEquals("unknown", metadata.packVersion(), "pack version");
    }

    private static void assertEquals(Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + " but got " + actual);
        }
    }
}
