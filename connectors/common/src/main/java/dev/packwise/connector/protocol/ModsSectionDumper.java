package dev.packwise.connector.protocol;

import java.util.List;

public final class ModsSectionDumper {
    private ModsSectionDumper() {
    }

    public static RuntimeDumpContent dump(List<ModSnapshot> mods) {
        return NdjsonSectionDumper.dump(
                RuntimeSectionNames.MODS,
                mods.stream().map(ModSnapshot::toJsonLine).toList());
    }
}
