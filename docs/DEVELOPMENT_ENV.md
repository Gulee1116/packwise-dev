# Development Environment

Packwise is a mixed Python and Java project:

- `apps/agent` is a standard-library Python agent harness.
- `connectors/neoforge` is a Java/NeoForge connector and requires JDK 21.

The project uses a repository-local environment so later agents and developers do not accidentally depend on global machine state.

## Directory Contract

All local tools and caches belong under:

```text
.packwise-env/
```

This directory is ignored by Git and may contain:

- `python/` for the Python virtual environment.
- `jdk/` for the project-local JDK 21.
- `gradle/` for `GRADLE_USER_HOME`.
- `pip-cache/` for pip downloads.
- `pycache/` for Python bytecode.
- `cache/` for downloaded setup archives.

Build outputs, runtime dumps, local modpacks, logs, and secrets remain excluded by `.gitignore`.

## First-Time Setup

From the repository root:

```bash
./scripts/dev setup
```

On Linux x64, this creates the Python venv and downloads a Temurin JDK 21 into `.packwise-env/jdk`.

On other platforms, install or unpack JDK 21 manually into `.packwise-env/jdk`, then run:

```bash
./scripts/dev doctor
```

## Daily Commands

Run all commands through the wrapper:

```bash
./scripts/dev doctor
./scripts/dev test-python
./scripts/dev test-java-protocol
./scripts/dev build-neoforge
```

Open an interactive shell with the project-local environment active:

```bash
./scripts/dev shell
```

For one-off commands, source the environment script first:

```bash
source scripts/env.sh
```

## Environment Variables

The wrapper and activation script set:

```text
PACKWISE_REPO_ROOT=<repo>
PACKWISE_ENV_HOME=<repo>/.packwise-env
JAVA_HOME=<repo>/.packwise-env/jdk
PACKWISE_JDK21_HOME=<repo>/.packwise-env/jdk
GRADLE_USER_HOME=<repo>/.packwise-env/gradle
PIP_CACHE_DIR=<repo>/.packwise-env/pip-cache
PYTHONPYCACHEPREFIX=<repo>/.packwise-env/pycache
PYTHONPATH=<repo>/apps/agent
```

`./scripts/dev doctor` verifies that Java and Gradle are using the local paths.

## Rules For Agents

- Work from the repository root unless a command explicitly changes directory.
- Prefer `./scripts/dev ...` over raw `python`, `java`, `javac`, or `gradle` commands.
- Do not install Python packages globally or with `--user`.
- Do not use the default `~/.gradle` cache for this project.
- Do not commit `.packwise-env/`, build outputs, runtime dumps, local modpacks, logs, or secrets.
