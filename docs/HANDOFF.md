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

## Current State

- Project docs exist in `PROJECT_IDEA.md` and `TECHNICAL_ROUTE.md`.
- The installed StoneBlock 4 instance structure has been documented in `STONEBLOCK4_INSTANCE_STRUCTURE.md` using redacted placeholder paths.
- Connector-agent protocol draft exists in `docs/protocol/CONNECTOR_AGENT_PROTOCOL.md`.
- Python agent harness exists in `apps/agent`.
- NeoForge connector skeleton exists in `connectors/neoforge`.
- Java protocol/model tests can run without launching Minecraft.
- Python harness tests can run without launching Minecraft.
- Static FTB Quests parsing exists for chapter/quest/task/reward/dependency skeletons.
- A one-off static Create fan recipe probe is documented in `docs/STATIC_CREATE_FAN_RECIPE_PROBE.md`.

## Important Caveats

- Packwise does not yet have a formal recipe query product surface.
- Static recipe probing can produce useful preloaded indexes, but KubeJS execution, datapack priority, tag expansion, mod conditions, duplicate recipe IDs, and runtime-only registrations still require runtime reconciliation.
- The NeoForge connector has a buildable skeleton and protocol upload pieces, but in-game commands and full runtime recipe/tag/registry dumps are still future work.
- The current Python service stores state in memory; durable server/player memory is not implemented yet.

## Suggested Next Steps

1. Turn the one-off recipe probe into an `inspect-recipes` command with source and confidence annotations.
2. Add duplicate recipe ID and datapack priority handling.
3. Add targeted KubeJS extractors for common recipe/removal helper patterns.
4. Add a NeoForge runtime recipe/tag dump and compare it against static preload output.
5. Keep public fixtures tiny and synthetic unless third-party redistribution rights are explicit.
