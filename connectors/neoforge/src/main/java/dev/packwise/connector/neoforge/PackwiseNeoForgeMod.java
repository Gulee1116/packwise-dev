package dev.packwise.connector.neoforge;

import net.neoforged.fml.common.Mod;

@Mod(PackwiseNeoForgeMod.MOD_ID)
public final class PackwiseNeoForgeMod {
    public static final String MOD_ID = "packwise_connector";

    public PackwiseNeoForgeMod() {
        // Runtime hooks will be added after the connector-agent protocol hardens.
    }
}
