# Agent Working Contract

This repository uses a project-local development environment. Future agents should keep all toolchain changes inside the repository and avoid relying on global Java, Python, pip, or Gradle state.

## Start Here

Always work from the repository root:

```bash
cd /mnt/cpfs/ziyuew/packwise-dev
```

Use the tracked development wrapper for normal work:

```bash
./scripts/dev doctor
./scripts/dev test-python
./scripts/dev test-java-protocol
./scripts/dev build-neoforge
```

For an interactive shell:

```bash
./scripts/dev shell
```

If `.packwise-env/` is missing on a new machine, run:

```bash
./scripts/dev setup
```

## Local Environment Boundary

The only approved local environment directory is:

```text
.packwise-env/
```

It contains the Python venv, JDK 21, Gradle cache, pip cache, and Python bytecode cache. It is intentionally ignored by Git.

Do not run global installs for this project:

```text
sudo apt install ...
pip install --user ...
pip install globally ...
gradle with default ~/.gradle cache ...
```

The wrapper and activation script set:

```text
JAVA_HOME=.packwise-env/jdk
PACKWISE_JDK21_HOME=.packwise-env/jdk
GRADLE_USER_HOME=.packwise-env/gradle
PIP_CACHE_DIR=.packwise-env/pip-cache
PYTHONPYCACHEPREFIX=.packwise-env/pycache
PYTHONPATH=apps/agent
```

## Manual Activation

Prefer `./scripts/dev ...`. If a raw shell command is needed, source the environment first:

```bash
source scripts/env.sh
```

Then run commands from the repository root or from the module directory required by the command.
