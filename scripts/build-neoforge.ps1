param(
    [string]$JavaHome = $env:PACKWISE_JDK21_HOME,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GradleArgs
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($JavaHome)) {
    $JavaHome = Join-Path $env:APPDATA ".minecraft\runtime\java-runtime-delta"
}

$javaExe = Join-Path $JavaHome "bin\java.exe"
$javacExe = Join-Path $JavaHome "bin\javac.exe"

if (-not (Test-Path -LiteralPath $javaExe) -or -not (Test-Path -LiteralPath $javacExe)) {
    throw "JDK 21 not found at '$JavaHome'. Set PACKWISE_JDK21_HOME or pass -JavaHome."
}

if (-not $GradleArgs -or $GradleArgs.Count -eq 0) {
    $GradleArgs = @("build", "--no-daemon")
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$connectorRoot = Join-Path $repoRoot "connectors\neoforge"

$env:JAVA_HOME = $JavaHome
$env:Path = "$JavaHome\bin;$env:Path"

Push-Location $connectorRoot
try {
    & ".\gradlew.bat" @GradleArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
