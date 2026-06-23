$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$main = Join-Path $root "connectors\neoforge\src\main\java"
$test = Join-Path $root "connectors\neoforge\src\test\java"
$out = Join-Path $root "connectors\neoforge\build\protocol-test-classes"

if (Test-Path -LiteralPath $out) {
  Remove-Item -LiteralPath $out -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $out | Out-Null

$sources = @()
$sources += Get-ChildItem -LiteralPath (Join-Path $main "dev\packwise\connector\protocol") -Filter "*.java" -File | ForEach-Object { $_.FullName }
$sources += Get-ChildItem -LiteralPath (Join-Path $test "dev\packwise\connector\protocol") -Filter "*.java" -File | ForEach-Object { $_.FullName }
$sources += Join-Path $main "dev\packwise\connector\neoforge\NeoForgeModSnapshots.java"
$sources += Join-Path $test "dev\packwise\connector\neoforge\NeoForgeModSnapshotsTest.java"

javac -encoding UTF-8 -d $out $sources
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
java -cp $out dev.packwise.connector.protocol.ProtocolCodecTest
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
java -cp $out dev.packwise.connector.protocol.RuntimeDumpManifestTest
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
java -cp $out dev.packwise.connector.protocol.ModsSectionDumperTest
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
java -cp $out dev.packwise.connector.protocol.AgentHttpClientTest
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
java -cp $out dev.packwise.connector.protocol.RuntimeDumpUploaderTest
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
java -cp $out dev.packwise.connector.neoforge.NeoForgeModSnapshotsTest
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
