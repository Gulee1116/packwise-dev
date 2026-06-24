package dev.packwise.connector.forge;

import com.mojang.logging.LogUtils;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.fml.common.Mod;
import org.slf4j.Logger;

@Mod(PackwiseForgeMod.MOD_ID)
public final class PackwiseForgeMod {
    public static final String MOD_ID = "packwise_connector";
    private static final Logger LOGGER = LogUtils.getLogger();

    public PackwiseForgeMod() {
        MinecraftForge.EVENT_BUS.addListener(PackwiseForgeCommands::register);
        LOGGER.info("Packwise connector loaded: mod_id={}, version={}", MOD_ID, ForgeRuntimeIdentity.connectorVersion());
    }
}
