package dev.packwise.connector.neoforge;

import dev.packwise.connector.protocol.ModSnapshot;

import java.util.List;

public final class NeoForgeModSnapshotsTest {
    public static void main(String[] args) {
        extractsSnapshotsFromModInfoObjects();
        System.out.println("NeoForgeModSnapshotsTest passed");
    }

    private static void extractsSnapshotsFromModInfoObjects() {
        List<ModSnapshot> snapshots = NeoForgeModSnapshots.fromModInfoObjects(List.of(
                new FakeModInfo("minecraft", "Minecraft", new FakeVersion("1.21.1")),
                new FakeModInfo("neoforge", "NeoForge", new FakeVersion("21.1.233"))));

        assertEquals(2, snapshots.size(), "snapshot count");
        assertEquals("minecraft", snapshots.get(0).modId(), "first mod id");
        assertEquals("NeoForge", snapshots.get(1).displayName(), "second display name");
        assertEquals("21.1.233", snapshots.get(1).version(), "second version");
        assertEquals("neoforge:ModList", snapshots.get(1).source(), "source");
    }

    private static void assertEquals(Object expected, Object actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected " + expected + " but got " + actual);
        }
    }

    public static final class FakeModInfo {
        private final String modId;
        private final String displayName;
        private final FakeVersion version;

        private FakeModInfo(String modId, String displayName, FakeVersion version) {
            this.modId = modId;
            this.displayName = displayName;
            this.version = version;
        }

        public String getModId() {
            return modId;
        }

        public String getDisplayName() {
            return displayName;
        }

        public FakeVersion getVersion() {
            return version;
        }
    }

    public static final class FakeVersion {
        private final String value;

        private FakeVersion(String value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return value;
        }
    }
}
