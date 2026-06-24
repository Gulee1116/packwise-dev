# Packwise Handoff

Review date: 2026-06-23

## Verdict

The current handoff is reasonable: it correctly frames Packwise as a training-free model + harness project, keeps Python in the offline/agent layer, keeps the Minecraft runtime connector in the JVM/mod ecosystem, and treats runtime dumps as the final source of truth for 100% accurate recipes and state.

The main caveat is terminology: several static probes are useful evidence, but they are not product features yet. Future work should keep a clear distinction between:

- implemented harness commands and tested APIs
- one-off static investigations
- planned runtime connector capabilities

## Public Repository Safety

This repository should stay source-only.

Do not commit:

- local Codex/session configuration
- raw modpack archives, sidecar jars, or downloaded third-party mods
- generated artifacts, runtime dumps, SQLite indexes, logs, saves, or player/server state
- real API keys, server addresses, session tokens, account files, or private launcher data

The `.gitignore` is configured to exclude the local modpack sample directory, runtime artifacts, build outputs, Python caches, local `.env` files, and `.codex/`.

## Local Development Environment

Use the repository-local environment contract documented in `docs/DEVELOPMENT_ENV.md` and `AGENTS.md`.

Default entry points:

```bash
./scripts/dev setup
./scripts/dev doctor
./scripts/dev test-python
./scripts/dev test-java-protocol
./scripts/dev build-neoforge
```

All Python, Java, Gradle, pip, and bytecode cache state should stay under `.packwise-env/`. Do not use global pip installs, system Java assumptions, or the default `~/.gradle` cache for this project.

## Current State

- Project docs exist in `PROJECT_IDEA.md` and `TECHNICAL_ROUTE.md`.
- The installed StoneBlock 4 instance structure has been documented in `STONEBLOCK4_INSTANCE_STRUCTURE.md` using redacted placeholder paths.
- Connector-agent protocol draft exists in `docs/protocol/CONNECTOR_AGENT_PROTOCOL.md`.
- Python agent harness exists in `apps/agent`.
- NeoForge connector skeleton exists in `connectors/neoforge`.
- CloudBase has been selected as the preferred public API deployment target: the Minecraft server connector should push authoritative state outbound to CloudBase, while clients query CloudBase directly.
- Java protocol/model tests can run without launching Minecraft.
- Python harness tests can run without launching Minecraft.
- Static FTB Quests parsing exists for chapter/quest/task/reward/dependency skeletons.
- A one-off static Create fan recipe probe is documented in `docs/STATIC_CREATE_FAN_RECIPE_PROBE.md`.

## Important Caveats

- Packwise does not yet have a formal recipe query product surface.
- Static recipe probing can produce useful preloaded indexes, but KubeJS execution, datapack priority, tag expansion, mod conditions, duplicate recipe IDs, and runtime-only registrations still require runtime reconciliation.
- The NeoForge connector has a buildable skeleton and protocol upload pieces, but in-game commands and full runtime recipe/tag/registry dumps are still future work.
- The current Python service stores state in memory; durable server/player memory is not implemented yet.
- CloudBase functions must be treated as stateless request handlers. Do not rely on in-process `AgentService` dictionaries for durable state after deployment; persist latest snapshots, manifests, logs, and large dump objects in CloudBase DB/Storage.

## Suggested Next Steps

1. Define the minimum CloudBase schema for `server_snapshots`, `runtime_dumps`, token metadata, and query logs.
2. Define the server connector snapshot push payload and token authentication boundary.
3. Split the Python harness service boundary so the same protocol logic can run behind stateless CloudBase HTTP handlers.
4. Add a NeoForge runtime recipe/tag dump and compare it against static preload output.
5. Turn the one-off recipe probe into an `inspect-recipes` command with source and confidence annotations.
6. Keep public fixtures tiny and synthetic unless third-party redistribution rights are explicit.
