package dev.packwise.connector.protocol;

import java.util.List;
import java.util.Objects;

public record RuntimeDumpUploadResult(
        String helloResponse,
        String manifestResponse,
        List<String> sectionResponses) {

    public RuntimeDumpUploadResult(String manifestResponse, List<String> sectionResponses) {
        this("", manifestResponse, sectionResponses);
    }

    public RuntimeDumpUploadResult {
        Objects.requireNonNull(helloResponse, "helloResponse");
        Objects.requireNonNull(manifestResponse, "manifestResponse");
        sectionResponses = List.copyOf(Objects.requireNonNull(sectionResponses, "sectionResponses"));
    }
}
