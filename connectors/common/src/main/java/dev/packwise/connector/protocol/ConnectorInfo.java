package dev.packwise.connector.protocol;

import java.util.List;
import java.util.Objects;

public record ConnectorInfo(
        String id,
        ConnectorSide side,
        String loader,
        String loaderVersion,
        String minecraftVersion,
        String packId,
        String packName,
        String packVersion,
        String connectorModId,
        String connectorVersion,
        List<String> capabilities) {

    public ConnectorInfo(
            String id,
            ConnectorSide side,
            String loader,
            String loaderVersion,
            String minecraftVersion,
            String packId,
            String packName,
            String packVersion,
            List<String> capabilities
    ) {
        this(
                id,
                side,
                loader,
                loaderVersion,
                minecraftVersion,
                packId,
                packName,
                packVersion,
                "unknown",
                "unknown",
                capabilities);
    }

    public ConnectorInfo {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(side, "side");
        Objects.requireNonNull(loader, "loader");
        Objects.requireNonNull(loaderVersion, "loaderVersion");
        Objects.requireNonNull(minecraftVersion, "minecraftVersion");
        Objects.requireNonNull(packId, "packId");
        Objects.requireNonNull(packName, "packName");
        Objects.requireNonNull(packVersion, "packVersion");
        Objects.requireNonNull(connectorModId, "connectorModId");
        Objects.requireNonNull(connectorVersion, "connectorVersion");
        capabilities = List.copyOf(Objects.requireNonNull(capabilities, "capabilities"));
    }
}
