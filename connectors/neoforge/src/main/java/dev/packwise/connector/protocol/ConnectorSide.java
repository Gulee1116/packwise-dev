package dev.packwise.connector.protocol;

public enum ConnectorSide {
    CLIENT("client"),
    SERVER("server"),
    CLIENT_SERVER("client_server");

    private final String wireValue;

    ConnectorSide(String wireValue) {
        this.wireValue = wireValue;
    }

    public String wireValue() {
        return wireValue;
    }

    public static ConnectorSide fromWireValue(String value) {
        for (ConnectorSide side : values()) {
            if (side.wireValue.equals(value)) {
                return side;
            }
        }
        throw new IllegalArgumentException("Unsupported connector side: " + value);
    }
}
