package dev.packwise.connector.protocol;

import java.util.List;
import java.util.Objects;

public record RuntimeDumpUploadResult(
        String manifestResponse,
        List<String> sectionResponses) {

    public RuntimeDumpUploadResult {
        Objects.requireNonNull(manifestResponse, "manifestResponse");
        sectionResponses = List.copyOf(Objects.requireNonNull(sectionResponses, "sectionResponses"));
    }
}
