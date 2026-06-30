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
./scripts/dev pr-fast-gate
./scripts/dev test-python
./scripts/dev test-java-protocol
./scripts/dev build-forge
./scripts/dev build-neoforge
```

All Python, Java, Gradle, pip, and bytecode cache state should stay under `.packwise-env/`. Do not use global pip installs, system Java assumptions, or the default `~/.gradle` cache for this project.
`./scripts/dev setup` provisions both `.packwise-env/jdk` for JDK 21 builds and
`.packwise-env/jdk17` for Java 17 Minecraft client smoke launchers.

## CI/CD Integration-Test Automation Update

Automation update date: 2026-06-24

### Layer 1: PR Fast Gate

Added `./scripts/dev pr-fast-gate` as the single local PR gate. It runs, in
order:

```bash
./scripts/dev doctor
./scripts/dev test-python
./scripts/dev test-java-protocol
./scripts/dev build-forge
./scripts/dev build-neoforge
git diff --check
git diff --cached --check
```

Future agents should run:

```bash
./scripts/dev pr-fast-gate
```

Passed in this run: `./scripts/dev pr-fast-gate` completed successfully,
including 131 Python tests, all Java protocol tests, Forge build, NeoForge
build, `git diff --check`, and `git diff --cached --check`.

Generated artifacts remain in existing ignored locations: `.packwise-env/`
for Python/JDK/Gradle caches and connector-local `build/` directories.

### Layer 2: Headless Dedicated Server Smoke Harness

Added `./scripts/dev smoke-forge-server`, backed by
`scripts/forge-server-smoke`. The default path downloads/caches the Forge
1.20.1 / 47.4.20 installer under `.packwise-env/cache/`, installs server
libraries under `.packwise-env/forge-server-smoke/`, creates a temporary server
run under `artifacts/forge-server-smoke/<run-id>/server/`, copies the newly
built Forge connector jar into `mods/`, starts the server with `nogui`, sends:

```text
packwise status
packwise dump
stop
```

over server stdin, copies `logs/latest.log`, and validates the generated dump.

Future agents should run the minimal smoke after building the Forge jar:

```bash
./scripts/dev smoke-forge-server --require-phase1
```

For a faster harness-only rerun when the jar already exists:

```bash
./scripts/dev smoke-forge-server --skip-build --require-phase1
```

Passed in this run:

```bash
./scripts/dev smoke-forge-server --skip-build --require-phase1 --timeout 240 --startup-timeout 180 --shutdown-timeout 60
```

Evidence from the passing run:

```text
artifacts/forge-server-smoke/20260624T185448Z-3952814/
```

The validation report was `valid: true`, Forge `47.4.20`, Minecraft `1.20.1`,
connector `packwise_connector 0.1.0`, and non-empty Phase 1 sections:
`mods=3`, `items=1255`, `blocks=1003`, `fluids=5`, `tags=556`,
`recipes=1174`, `advancements=1271`. Server logs also show the connector load
line, `/packwise status` identity lines, and `/packwise dump` output with
`connector_id`, `dump_id`, and local dump `path`.

Artifacts/logs/dumps live under:

```text
artifacts/forge-server-smoke/<run-id>/
artifacts/forge-server-smoke/<run-id>/server-console.log
artifacts/forge-server-smoke/<run-id>/latest.log
artifacts/forge-server-smoke/<run-id>/packwise-dumps/<dump_id>/
artifacts/forge-server-smoke/<run-id>/validate-dump.json
```

When `--server-dir` points at an existing external server pack, the harness
copies that directory to `artifacts/forge-server-smoke/<run-id>/server/` by
default and runs only against the disposable copy. Symlinks are dereferenced
during this copy so mutable paths such as `mods/`, `world/`, `logs/`, and
`config/` do not point back to the original server directory. Replacing Packwise
jars, accepting EULA, server-generated `world/`, `logs/`, and any server
properties changes stay in that evidence copy. Pass `--in-place-server` only
when the caller intentionally wants to run directly in the supplied server
directory.

Remaining limitation: this is the smallest Forge dedicated-server smoke. It
does not prove ATM9Sky optional integrations because the smoke server only
loads Minecraft, Forge, and Packwise.

### Layer 3: GameTest Layer

GameTest was investigated and skipped for this run. The current Gradle task
surface has server runs only:

```bash
source scripts/env.sh
cd connectors/forge
./gradlew tasks --all | rg -i "gametest|game test|runServer|runClient"

source scripts/env.sh
cd connectors/neoforge
./gradlew tasks --all | rg -i "gametest|game test|runServer|runClient"
```

Observed result: Forge exposes `prepareRunServer`, `prepareRunServerCompile`,
and `runServer`; NeoForge exposes `runServer`. No `runGameTestServer`,
GameTest source set, GameTest structure templates, or existing GameTest
registration exists in this repo. Adding a non-vacuous GameTest for
`ForgeRuntimeDumpCollector.collect(MinecraftServer)` would require introducing
the Forge GameTest run configuration plus test classes and structure assets,
then proving that task in Gradle. That is a real setup task, not a quick local
toggle, so the dedicated-server smoke above is the verified real
`MinecraftServer` runtime proof for now.

No GameTest artifacts are generated. Future GameTest artifacts should stay
under `artifacts/gametest/` or connector `run*/` directories ignored by Git
(`connectors/forge/run*/` and `connectors/neoforge/run*/`).

### Layer 4: ATM9Sky Headless Nightly/On-Demand Lane

Added `./scripts/dev atm9sky-headless`, backed by `scripts/atm9sky-headless`.
It reuses the Forge smoke harness against an externally supplied ATM9Sky server
pack, copies the server pack to disposable evidence by default, copies in the
freshly built connector jar for the run, requires Phase 1 dump validation, and
runs `phase1-acceptance` when an installed ATM9Sky instance path is supplied.
The original external server directory is not modified unless
`--in-place-server` is passed.

Future operators should provide the real server pack and installed instance
outside Git, then run:

```bash
PACKWISE_ATM9SKY_SERVER_DIR="<external-atm9sky-server>" \
PACKWISE_ATM9SKY_INSTANCE_DIR="<installed-atm9sky-instance>" \
PACKWISE_ATM9SKY_ITEM_ID="<item-with-runtime-recipe-or-quest-ref>" \
./scripts/dev atm9sky-headless
```

If the pack start script cannot be inferred, pass:

```bash
./scripts/dev atm9sky-headless \
  --server-dir "<external-atm9sky-server>" \
  --instance "<installed-atm9sky-instance>" \
  --server-command "./startserver.sh nogui" \
  --item-id "<item-with-runtime-recipe-or-quest-ref>"
```

For online upload evidence:

```bash
PACKWISE_BACKEND_BASE_URL="<agent-url>" ./scripts/dev atm9sky-headless ...
```

For an explicitly mutable local server workspace, pass `--in-place-server`.
This should be avoided for nightly/CI evidence because Packwise jar
replacement, EULA changes, logs, and world writes will happen in the supplied
server directory.

Skipped in this run: no redistributable ATM9Sky server pack or installed
instance is committed or available as an approved repo fixture, and pack
acquisition/licensing must stay external. Expected artifacts live under:

```text
artifacts/atm9sky-headless/<run-id>/
artifacts/atm9sky-headless/<run-id>/server/
artifacts/atm9sky-headless/<run-id>/latest.log
artifacts/atm9sky-headless/<run-id>/packwise-dumps/<dump_id>/
artifacts/atm9sky-headless/<run-id>/validate-dump.json
artifacts/atm9sky-headless/<run-id>/phase1-acceptance.json
```

### Layer 5: Headless Client/Server 联调 Lane

Added `./scripts/dev atm9sky-client-server`, backed by
`scripts/atm9sky-client-server`, as the repeatable ATM9Sky server/client smoke
lane. It is still an external/manual lane, not a PR gate, because the repo does
not and should not commit a real client instance, launcher files, account state,
or modpack archives.

The lane starts from the real server pack, `/opt/atm9sky` by default, copies it
to a disposable run directory under the evidence root, copies in the current
Forge Packwise connector jar, accepts the EULA only in the copy, and forces a
known local `server-port` in the copied `server.properties` and
`default-server.properties` while binding the disposable server to
`127.0.0.1`. The Forge connector metadata declares server-side compatibility
with clients that do not install the Packwise jar, so this lane keeps the
connector in the disposable server copy only. It removes any copied server
`logs/` before startup so join detection cannot match historical `latest.log`
entries from the source pack. It then starts the server under Java 17, verifies
the Packwise connector load line, sends `packwise status` on the server console,
starts the supplied client launcher command under independently configured Java
17, waits for the server/client logs to prove a localhost join or a concrete
failure, sends post-join `say packwise-smoke` and `list` commands on the server
console, and polls both processes plus post-join server/client log tails during
the hold so login-after-crash and login-then-disconnect cases fail the lane.
The lane passes only when `summary.json` has `exit_status: "passed"`,
`client_joined: true`, and post-join `list` evidence showing at least one player
online.

Required client inputs are external:

```bash
PACKWISE_ATM9SKY_CLIENT_INSTANCE_DIR="<installed-atm9sky-client-instance>" \
PACKWISE_ATM9SKY_CLIENT_COMMAND="<launcher command>" \
./scripts/dev atm9sky-client-server
```

The client command may use these placeholders, which are shell-quoted before
execution:

```text
{server_host}
{server_port}
{instance_dir}
{java}
{artifact_dir}
```

The server command exports `JAVA_HOME` and prepends
`PACKWISE_ATM9SKY_SERVER_JAVA` to `PATH`; by default that Java is the repo-local
`.packwise-env/jdk17/bin/java` provisioned by `./scripts/dev setup`. The
configured server Java must report version 17, matching the ATM9Sky 1.1.9 /
Forge 47.4.10 server expectation and preventing `./scripts/dev`'s JDK 21 build
environment from leaking into the server runtime.

The same values are also exported to the launcher process as
`PACKWISE_SMOKE_SERVER_HOST`, `PACKWISE_SMOKE_SERVER_PORT`,
`PACKWISE_SMOKE_CLIENT_INSTANCE`, `PACKWISE_SMOKE_CLIENT_JAVA`, and
`PACKWISE_SMOKE_ARTIFACT_DIR`. The lane exports `JAVA_HOME` and prepends
`PACKWISE_ATM9SKY_CLIENT_JAVA` to `PATH`; by default that Java is the
repo-local `.packwise-env/jdk17/bin/java` provisioned by `./scripts/dev setup`.
The configured Java must report version 17, matching the ATM9Sky 1.1.9 / Forge
47.4.10 client expectation.
The raw launcher command is executed but is not persisted to `summary.json` or
`commands.log`; those artifacts store only a redacted marker with the command's
SHA-256 fingerprint, because launcher arguments can contain account tokens.
Recommended Prism/MultiMC-style launcher commands should use the placeholders
instead of hard-coded paths. For example, adapt the executable path and instance
name to the runner:

```bash
PACKWISE_ATM9SKY_CLIENT_COMMAND='prismlauncher --launch "ATM9Sky" --server {server_host}:{server_port}'
./scripts/dev atm9sky-client-server
```

If a launcher does not expose a `--server` flag, wrap the launcher command in a
repo-local script that consumes `PACKWISE_SMOKE_SERVER_HOST` and
`PACKWISE_SMOKE_SERVER_PORT`; do not add UI clicking as a nightly pass
condition.

Common options and env vars:

```bash
PACKWISE_ATM9SKY_SERVER_DIR="/opt/atm9sky" \
PACKWISE_ATM9SKY_SERVER_PORT="25565" \
PACKWISE_ATM9SKY_SERVER_JAVA=".packwise-env/jdk17/bin/java" \
PACKWISE_ATM9SKY_CLIENT_JAVA=".packwise-env/jdk17/bin/java" \
PACKWISE_ATM9SKY_CLIENT_PACK_VERSION="1.1.9" \
PACKWISE_ATM9SKY_CLIENT_MINECRAFT_VERSION="1.20.1" \
PACKWISE_ATM9SKY_CLIENT_FORGE_VERSION="47.4.10" \
PACKWISE_ATM9SKY_XVFB="auto" \
./scripts/dev atm9sky-client-server
```

If the default server command cannot be inferred from `run.sh`,
`startserver.sh`, `start.sh`, or Forge `unix_args.txt`, pass:

```bash
./scripts/dev atm9sky-client-server \
  --server-command "./startserver.sh nogui" \
  --client-instance "<installed-atm9sky-client-instance>" \
  --client-command "<launcher command>"
```

If the launcher needs an explicit graceful shutdown action after the join is
seen, pass `--client-stop-command` or set
`PACKWISE_ATM9SKY_CLIENT_STOP_COMMAND`. Otherwise the lane terminates the
client process during cleanup immediately after the post-join hold period
instead of waiting for the graceful shutdown timeout.

The client static preflight enforces the installation convention from
`how-to-make-a-client.txt`: the instance must expose `mods/`, `config/`,
`kubejs/`, and `defaultconfigs/`; include
`mods/I18nUpdateMod-3.7.0-all.jar`; set `lang:zh_cn` in `options.txt` and, when
present, `config/defaultsettings/Default/options.txt`; and identify ATM9Sky
`1.1.9`, Minecraft `1.20.1`, and Forge `47.4.10` through supported launcher
metadata such as CurseForge `manifest.json` or Prism/MultiMC `mmc-pack.json`.
It also requires the resolved client game directory's `mods/` to contain no
`packwise_connector*.jar`, because this lane keeps the connector server-side
only. The `/packwise status` and `/packwise dump` client commands are not this
lane's acceptance steps; they belong only to a separate client-side or
integrated-server dump workflow where the matching connector was explicitly
installed into that client instance.
For Prism/MultiMC instance roots, static game-file checks resolve the game
directory under `.minecraft/` when that is where `mods/`, `config/`, `kubejs/`,
`defaultconfigs/`, and `options.txt` live.
For launchers that keep version metadata outside the instance root, provide
`PACKWISE_ATM9SKY_CLIENT_PACK_VERSION`,
`PACKWISE_ATM9SKY_CLIENT_MINECRAFT_VERSION`, and
`PACKWISE_ATM9SKY_CLIENT_FORGE_VERSION` or the matching CLI flags; the static
report records those values as explicit evidence.
If those inputs are missing, the lane exits non-zero with
`exit_status: "blocked"` rather than attempting a partial client launch.

Artifacts live under:

```text
artifacts/atm9sky-client-server/<run-id>/
artifacts/atm9sky-client-server/<run-id>/server/
artifacts/atm9sky-client-server/<run-id>/server-console.log
artifacts/atm9sky-client-server/<run-id>/server-latest.log
artifacts/atm9sky-client-server/<run-id>/client.log
artifacts/atm9sky-client-server/<run-id>/client-latest.log
artifacts/atm9sky-client-server/<run-id>/client-provided.log
artifacts/atm9sky-client-server/<run-id>/client-static-acceptance.json
artifacts/atm9sky-client-server/<run-id>/post-join-console-validation.json
artifacts/atm9sky-client-server/<run-id>/diagnostics/diagnostics.json
artifacts/atm9sky-client-server/<run-id>/diagnostics/screenshot-*.png
artifacts/atm9sky-client-server/<run-id>/diagnostics/screenshot-*.xwd
artifacts/atm9sky-client-server/<run-id>/commands.log
artifacts/atm9sky-client-server/<run-id>/summary.json
```

`summary.json` always contains the required top-level fields
`server_started`, `client_started`, `client_joined`,
`packwise_connector_loaded`, `exit_status`, and `failure_reason`, plus nested
server/client/static-acceptance evidence, post-join console validation, and a
top-level `diagnostics` object. The nested server evidence records the server
Java path and reported Java version; nested client evidence records the client
Java path and reported Java version. A passing full smoke requires
`client_joined: true` and post-join `list` evidence proving at least one player
online; a blocked preflight is explicit and is not a substitute for
server/client acceptance.

The default path is CLI/console/log driven. Xvfb is a virtual display used to
run the real Minecraft client in headless environments; it is not a UI-clicking
acceptance layer. Screenshot capture is attempted only on failed runtime paths
such as client launch failure, join timeout, post-join disconnect, or
client/server crash. If an owned Xvfb display or existing `DISPLAY` is
available, the lane tries `import`, `scrot`, `gnome-screenshot`, then `xwd` and
writes results under `diagnostics/`. If no display or screenshot tool is
available, `diagnostics.json` records the skipped reason without replacing the
original `failure_reason`.

Current limitation for this run: `/opt/atm9sky` and a repo-local Java 17 are
available, and Xvfb is installed, but no real installed ATM9Sky client instance
or configured launcher command was found in the local workspace. The implemented
lane can therefore produce a truthful blocked summary until those external
client inputs are supplied.

Implementation/review loop notes for the ATM9Sky client/server lane:

- Round 1 implementation: added post-join server-console validation with
  redacted `list` evidence, failure-only diagnostics metadata, screenshot
  capture under `diagnostics/`, and owned-Xvfb display startup when available.
  Raw launcher commands remain redacted to a SHA-256 marker.
- Round 1 independent review: no blocking issues. It found one low-severity
  Bash status handling bug where a zero-player `list` result would fail only
  after timeout with a less precise reason, and a local-artifact caution that
  copied launcher/client logs may contain whatever a launcher prints even though
  the configured launcher command itself is redacted.
- Follow-up fix after review: preserved the post-join validation helper exit
  status so a zero-player `list` result fails immediately with the explicit
  no-player reason. No further implementation round is planned unless a real
  client run exposes a new issue.
- Round 2 fix verification: no additional edits were needed; the current script
  already preserves the post-join validation status and the handoff note matches
  that behavior.
- Final independent review: no findings requiring another fix round. The review
  re-confirmed the default CLI/console/log path, required post-join `list`
  evidence, failure-only diagnostics, launcher command redaction, no default UI
  clicking, and loop notes.
- Verification evidence from this run:
  `bash -n scripts/dev scripts/forge-server-smoke scripts/atm9sky-client-server`
  passed; `./scripts/dev pr-fast-gate` passed; the real ATM9Sky server-only
  smoke passed against `/opt/atm9sky` with
  `artifacts/forge-server-smoke/verify-atm9sky-server-20260626T035942Z/validate-dump.json`
  reporting `valid: true`; synthetic client/server runs verified preflight
  blocked behavior, post-join `list` pass behavior, zero-player failure
  behavior, and Xvfb screenshot diagnostics on runtime failure.
- Current remaining limitation: this workspace still needs a real installed
  ATM9Sky client instance and launcher command before `client_joined=true` can
  be verified against the actual client.

### Layer 6: CloudBase/Agent Integration Lane

Added `./scripts/dev agent-http-e2e`, backed by `scripts/agent-http-e2e`. This
is the local first step for the CloudBase/agent lane: it starts the in-memory
agent HTTP service, sends `connector.hello`, uploads a synthetic runtime dump
manifest and all Phase 1 sections over HTTP, then verifies connector status,
scoped index summary, scoped pack index, and `query.ask` source references.

Future agents should run:

```bash
./scripts/dev agent-http-e2e
```

Passed in this run:

```text
artifacts/agent-http-e2e/20260624T185339Z-3951043/summary.json
```

The summary reported `valid: true` and checked:

- connector.hello accepted
- runtime dump manifest and sections accepted
- connector status reports `upload_complete`
- scoped `index-summary` has runtime sections
- scoped `pack-index` builds from the uploaded dump
- `query.ask` returns source refs

Remaining CloudBase-specific gap: durable CloudBase DB/Storage handlers,
deployment config, auth/token policy, and stateless persistence are still not
implemented. The local HTTP E2E proves the connector/agent protocol path only.
Generated evidence lives under:

```text
artifacts/agent-http-e2e/<run-id>/
```

## QA Readable Item Labels Update

Update date: 2026-06-26

Player-facing `query.ask` answers now build a runtime item-label layer before
prompting or fallback summary generation. Labels prefer runtime
`translated_name`, then Chinese/runtime display names, known ATM9Sky Chinese
names, runtime display names, and finally a readable fallback derived from the
registry path. Prose uses `名称（registry:id）`, while `source_refs` keep exact
registry IDs and recipe/quest paths as evidence anchors.

The LLM prompt now receives `item_labels`, labeled matched/related items,
labeled recipe result/ingredient facts, runtime counts/readiness, quest facts,
and source refs. The prompt explicitly tells the model to use readable item
names in prose and keep IDs in parentheses or source refs. LLM summaries are
post-processed against the evidence so omitted critical runtime items are
supplemented with labels and raw item IDs in generated text are localized when
the evidence contains a label.

Fallback summaries and `next_steps` use the same label layer. QA-1
Everlasting Abilities answers now render examples such as
`能力瓶（everlastingabilities:ability_bottle）` and
`能力图腾（everlastingabilities:ability_totem）`; QA-5 Thermal upgrade answers
render `硬化升级组件（thermal:upgrade_augment_1）`,
`强化升级组件（thermal:upgrade_augment_2）`, and
`谐振升级组件（thermal:upgrade_augment_3）` instead of naked ID chains.

Forge runtime item dump rows now optionally include:

```json
{"translation_key":"item.example.id","display_name":"Example Name"}
```

Existing dumps remain valid because the agent treats these fields as optional.
The server-side Forge dump can only expose the display text available in that
runtime; Chinese client-side language assets still require a translated client
dump or a later asset-ingestion path. Until that exists, known ATM9Sky names and
readable fallback labels fill gaps without pretending to be official
translations.

Implementation/review loop notes for the readable-name QA update:

- Round 1 implementation: added runtime item label parsing, LLM evidence labels,
  fallback/next-step localization, QA-1/QA-5 tests for readable prose and exact
  source refs, and optional Forge item `translation_key`/`display_name` dump
  fields.
- Round 1 independent review: found exact item asks could widen into sibling
  upgrade recipes, and runtime display/translated names were not used for item
  lookup.
- Round 1 follow-up fix: exact item asks now stay item-specific unless the
  question has family/order cues; runtime display/translated aliases can match
  Chinese/readable-name questions; tests cover both cases.
- Round 2 independent review: found exact item asks still emitted sibling
  `recipe_usage` refs, display-name aliases were shadowed by translated names,
  and `thermal_extra:*` item IDs could cite the `thermal` mod source ref.
- Round 2 follow-up fix: usage refs are only collected for explicit family
  questions, matching considers all runtime aliases, and explicit item
  namespaces choose exact mod refs before compact prefix matching.

Verification evidence from this run:

```bash
./scripts/dev test-python
./scripts/dev pr-fast-gate
```

Both passed. `test-python` currently runs 144 Python tests. `pr-fast-gate`
passed doctor, Python tests, Java protocol tests, Forge build, NeoForge build,
and diff whitespace checks.

Real API QA-1/QA-5 small eval was rerun against the current ATM9Sky runtime dump
with the provided key only in process environment, not persisted:

```text
artifacts/small-eval/readable-names-api-20260626T091554Z/summary.json
```

The requested alias `dpskv4pro` returned HTTP 403 for this key, so the eval used
`deepseek-v4-pro`. Both cases passed the readable-name checks:

- `qa01_everlasting_abilities`
- `qa05_thermal_upgrades`

The summary records `api_key_saved: false`; a follow-up source/artifact scan did
not find the provided API key written to files.

## Centralized Backend Inference Update

Update date: 2026-06-26

Packwise is now documented and wired for a centralized backend inference
topology:

- Minecraft server connectors send runtime dumps, status, and ask requests to
  the Packwise backend.
- Future user clients should also call the Packwise backend, using a backend URL
  such as `PACKWISE_BACKEND_BASE_URL`.
- Only the Packwise backend calls the OpenAI-compatible model provider.
- Model provider API keys must live only in the backend process environment.

The backend-side LLM variables are:

```text
PACKWISE_LLM_BASE_URL=https://<model-provider-host>/v1
PACKWISE_LLM_MODEL=deepseek-v4-pro
PACKWISE_LLM_API_KEY=<backend-side-secret>
```

Do not configure `dpskv4pro` as `PACKWISE_LLM_MODEL`; a real eval showed that
alias can return HTTP 403 for the supplied provider key. Use the actual model
ID `deepseek-v4-pro`.

Implementation details:

- The OpenAI-compatible client now normalizes base URLs with or without `/v1`
  and calls `/v1/chat/completions` and `/v1/models` without producing double
  `/v1/v1` paths.
- Added `python -m packwise_agent model-check` and `./scripts/dev model-check`
  to check backend-side model configuration. By default it verifies
  `/v1/models` reachability, confirms that `deepseek-v4-pro` is listed, and
  sends one minimal chat completion request; `--skip-chat-smoke` is available
  for list-only diagnostics.
- Model-check reports redact the configured API key and do not write secrets to
  artifacts.
- README and agent docs now show connector/client-to-backend variables
  separately from backend-to-model-provider variables, and use only placeholder
  secrets.
- Forge connector docs explicitly state that `PACKWISE_BACKEND_BASE_URL` and
  `PACKWISE_AGENT_BASE_URL` are Packwise backend URLs, that
  `PACKWISE_AGENT_URL` is a legacy alias, and that `PACKWISE_LLM_*` keys do not
  belong on the Minecraft server.

Implementation/review loop notes for the centralized inference update:

- Round 1 implementation: added the backend `model-check` command, `/v1` base
  URL normalization, docs/examples for the centralized topology, and focused
  LLM tests.
- Round 1 independent review: found that default model-check did not prove chat
  usability, legacy provider defaults could silently use stale env, and some
  docs still steered readers toward raw PowerShell/Python commands instead of
  the repo-local wrapper.
- Round 1 follow-up fix: model-check now defaults to a minimal chat completion
  smoke test, list-only checks require `--skip-chat-smoke`, backend model config
  requires explicit `PACKWISE_LLM_BASE_URL` and `PACKWISE_LLM_API_KEY`, the
  legacy `DEEPSEEK_API_KEY` fallback was removed, docs now use
  `PACKWISE_LLM_MODEL=deepseek-v4-pro`, and tests cover default chat smoke,
  skip-smoke, missing base URL, and ignored legacy key behavior.
- Round 2 independent review: no material findings. The review checked for
  accidental `dpskv4pro` configuration, `sk-*` leakage, connector/client
  API-key guidance, stale `model-check` docs/help, broken `./scripts/dev`
  wrapper paths, and missing config/default tests.
- Continuation implementation pass: re-audited the current centralized
  inference worktree, preserved the existing readable-name QA changes, and
  confirmed the backend-only `PACKWISE_LLM_*` path, backend URL connector
  aliases, `model-check` command, and docs/examples remained aligned.
- Continuation independent review: no material findings. The review checked the
  configured model name, removed `DEEPSEEK_API_KEY` fallback, backend-only API
  key boundary, `model-check` `/v1/models` plus chat-smoke behavior, wrapper
  help paths, secret scans, and focused config/default tests.

Verification evidence from this run:

```bash
./scripts/dev test-python
source scripts/env.sh && cd apps/agent && python -m unittest tests.test_llm
PACKWISE_LLM_API_KEY='unit-placeholder-secret' \
  PACKWISE_LLM_MODEL='deepseek-v4-pro' \
  ./scripts/dev model-check --base-url http://127.0.0.1:9/v1 --pretty || true
./scripts/dev model-check --help
./scripts/dev inspect --help
./scripts/dev inspect-quests --help
./scripts/dev serve --help
./scripts/dev pr-fast-gate
git diff --check && git diff --cached --check
rg -n "sk-[A-Za-z0-9]{20,}" apps connectors docs scripts artifacts README.md \
  --glob '!.packwise-env/**'
```

Results:

- `./scripts/dev test-python` passed with 150 Python tests.
- Focused `tests.test_llm` passed with 6 tests.
- Placeholder-key local failure check produced a redacted/secret-free invalid
  model-check report with `chat_smoke_requested: true`.
- CLI help for `model-check`, `inspect`, `inspect-quests`, and `serve` works
  through the repo-local wrapper.
- `./scripts/dev pr-fast-gate` passed doctor, Python tests, Java protocol
  tests, Forge build, NeoForge build, and diff whitespace checks.
- Explicit `git diff --check && git diff --cached --check` passed.
- Secret scan for `sk-*` found no matches in source, docs, scripts, or
  generated artifacts.

Live provider `model-check` was not run in this pass because the current process
did not have `PACKWISE_LLM_API_KEY` / `PACKWISE_LLM_BASE_URL` injected, and the
real key was intentionally not placed into command text or files.

Continuation verification on 2026-06-26:

```bash
./scripts/dev test-python
./scripts/dev pr-fast-gate
git diff --check && git diff --cached --check
rg -n "sk-[A-Za-z0-9]{20,}" --hidden --glob '!.git/**' \
  --glob '!.packwise-env/**' .
rg -n "sk-[A-Za-z0-9_-]{10,}" --hidden --glob '!.git/**' \
  --glob '!.packwise-env/**' .
./scripts/dev model-check --help
PACKWISE_LLM_API_KEY='unit-placeholder-secret' \
  PACKWISE_LLM_MODEL='deepseek-v4-pro' \
  ./scripts/dev model-check --base-url http://127.0.0.1:9/v1 --pretty || true
```

Results:

- `./scripts/dev test-python` passed with 150 Python tests.
- `./scripts/dev pr-fast-gate` passed doctor, Python tests, Java protocol
  tests, Forge build, NeoForge build, and diff whitespace checks.
- `git diff --check && git diff --cached --check` passed.
- Both `sk-*` scans found no matches outside `.git/` and `.packwise-env/`.
- `./scripts/dev model-check --help` passed.
- The placeholder-key local failure check returned `valid: false`, normalized
  endpoints `http://127.0.0.1:9/v1/models` and
  `http://127.0.0.1:9/v1/chat/completions`,
  `model: deepseek-v4-pro`, `chat_smoke_requested: true`, and no secret value
  in output.

Real player progress offline analysis attempt on 2026-06-26:

- Implementation subagent inspected existing runtime dump validation/import,
  Phase 1 progression acceptance, FTB Quests static parsing, and Forge optional
  FTB Quests/FTB Teams/GameStages dump support.
- Remote read-only SFTP inspection of `sfe4-connect.simpfun.cn:2047` was not
  possible in this context: a non-interactive no-password probe failed with
  `Permission denied (password,publickey)`.
- Ignored evidence lives at
  `testfiles-return-to-dev/real-server-progress-20260626T170904Z/`.
- No remote files were downloaded, no remote writes were attempted, no real
  player identities were added to tracked docs, and no progress counts are
  proven from this run.
- Independent review completed with no material findings. Remaining limitation:
  rerun from an echo-disabled credentialed SFTP session, then validate/import an
  existing Packwise dump or inspect only minimal offline progress files if no
  dump exists.
- Verification for this attempt passed:
  `python -m json.tool testfiles-return-to-dev/real-server-progress-20260626T170904Z/summary.json`,
  `./scripts/dev test-python` (150 tests), `./scripts/dev pr-fast-gate`,
  `git diff --check && git diff --cached --check`, and targeted scans for
  `sk-*`, inline SFTP password URI patterns, `sshpass`, and SFTP password
  environment names.

Real player progress offline analysis credential preflight on 2026-06-26:

- Implementation subagent checked the current dirty worktree, ignored evidence
  layout, repo-local toolchain, `.gitignore` coverage for
  `testfiles-return-to-dev/`, and approved local SFTP credential channels.
- No approved SFTP credential channel was available:
  `PACKWISE_REAL_SERVER_SFTP_PASSWORD` was absent, and
  `testfiles-return-to-dev/secrets/real-server-sftp-password.txt` was absent.
- No remote SFTP connection was opened, no remote `pwd` or `ls` command was
  sent, no files were downloaded, no remote writes were attempted, and no raw
  player identities were observed or added to tracked docs.
- Prior ignored evidence at
  `testfiles-return-to-dev/real-server-progress-20260626T170904Z/` was
  preserved. New ignored blocked-run evidence lives at
  `testfiles-return-to-dev/real-server-progress-20260626T173459Z/`.
- Real player progress offline analysis remains blocked for production use:
  Packwise dump presence, remote FTB Quests progress, FTB Teams membership, and
  GameStages state are all still unknown.
- Safe next step: inject the SFTP password through exactly one approved local
  channel, preferably the process-local
  `PACKWISE_REAL_SERVER_SFTP_PASSWORD` environment variable or the ignored file
  `testfiles-return-to-dev/secrets/real-server-sftp-password.txt`, then rerun
  read-only inspection. Do not place the password in command-line arguments,
  tracked files, docs, artifacts, shell history, or logs.
- Verification for this blocked preflight:
  `./scripts/dev doctor` passed; the credential preflight reported
  `env_present=0` and `secret_file_present=0`; `git check-ignore` confirmed
  the secret-file path and real-server-progress evidence paths are ignored;
  `python -m json.tool` accepted the new evidence `summary.json`;
  `git diff --check` and `git diff --cached --check` passed; targeted scans of
  the new evidence and handoff section found no concrete API-key patterns,
  inline SFTP credential URIs, unsafe SFTP password assignment patterns, or
  UUID-style player identity strings.

Real player progress offline analysis resumed preflight on 2026-06-27:

- Implementation subagent re-read the resumed run instructions, checked the
  dirty worktree without reverting unrelated edits, confirmed
  `testfiles-return-to-dev/` is ignored, and re-checked the two approved
  non-interactive SFTP credential channels.
- No approved SFTP credential channel was available:
  `PACKWISE_REAL_SERVER_SFTP_PASSWORD` was absent or empty, and
  `testfiles-return-to-dev/secrets/real-server-sftp-password.txt` did not
  exist. No credential contents were read and no credentials were written.
- No remote SFTP connection was opened, no no-password probe was performed, no
  remote `pwd` or `ls` command was sent, no files were downloaded, no remote
  writes were attempted, and no raw player identities were observed or added to
  tracked docs.
- Prior ignored evidence under `testfiles-return-to-dev/real-server-progress-*`
  was preserved. New ignored blocked-run evidence lives at
  `testfiles-return-to-dev/real-server-progress-20260627T173016Z/`.
- Real progress is still not visible from this resumed preflight:
  Packwise dump presence, FTB Quests progress, player progress, team progress,
  and GameStages state all remain unknown. `production_useful_now` is `false`.
- Safe next step: inject the SFTP password through exactly one approved local
  channel, preferably the process-local
  `PACKWISE_REAL_SERVER_SFTP_PASSWORD` environment variable or the ignored file
  `testfiles-return-to-dev/secrets/real-server-sftp-password.txt`, then rerun
  read-only inspection. Do not place the password in command-line arguments,
  tracked files, docs, artifacts, shell history, or logs.
- Verification for this blocked preflight:
  `python -m json.tool` accepted the new `summary.json`,
  `sanitized-remote-layout-summary.json`, and `downloaded-files.json`;
  `git check-ignore` confirmed the secret-file path and new evidence path are
  ignored; `git diff --check` and `git diff --cached --check` passed; targeted
  scans of the new evidence and this handoff entry found no API-key patterns,
  inline SFTP credential URIs, unsafe SFTP password assignment patterns,
  password-helper command references, or UUID-style player identity strings.
  `./scripts/dev doctor` was run as the repo-local toolchain check for this
  blocked/no-code-change pass.

Real player progress offline analysis local credential preflight on
2026-06-27T17:40:17Z:

- Implementation subagent read the resumed run instructions and verified only
  the approved local credential channels. The process-local
  `PACKWISE_REAL_SERVER_SFTP_PASSWORD` value was absent or empty, and
  `testfiles-return-to-dev/secrets/real-server-sftp-password.txt` was absent.
  No credential contents were read, requested, written, or logged.
- No remote SFTP connection was opened, no no-password probe was performed, no
  remote `pwd` or `ls` command was sent, no remote layout was inspected, no
  files were downloaded, and no remote writes were attempted.
- Prior ignored evidence under `testfiles-return-to-dev/real-server-progress-*`
  was preserved. New ignored blocked-run evidence lives at
  `testfiles-return-to-dev/real-server-progress-20260627T174017Z/`.
- Real progress is not visible from this run. Packwise dump presence, FTB
  Quests progress, player progress, team progress, GameStages state, and real
  progress counts are all unknown. `production_useful_now` is `false`.
- Remaining limitation: rerun only after the SFTP password is injected through
  exactly one approved local channel. Do not place it in command-line
  arguments, tracked files, docs, artifacts, shell history, or logs.
- Verification for this blocked/no-code-change pass:
  `source scripts/env.sh` plus local credential checks reported
  `PACKWISE_REAL_SERVER_SFTP_PASSWORD=absent` and `secret_file=absent`;
  `./scripts/dev doctor` passed using `.packwise-env/`; `python -m json.tool`
  accepted the new `summary.json`, `sanitized-remote-layout-summary.json`, and
  `downloaded-files.json`; `git check-ignore -v` confirmed both the ignored
  secret-file path and new evidence path are ignored; `git diff --check` and
  `git diff --cached --check` passed; targeted scans of the new evidence and
  this handoff entry found no API-key patterns, inline credentialed SFTP URIs,
  unsafe password assignments, forbidden helper command references, or
  UUID-style player identity strings.

Real player progress offline analysis read-only SFTP run on
2026-06-28T05:22:43Z:

- The implementation subagent used the approved ignored local secret file only
  inside the SFTP connection code. The secret file is ignored by Git; no
  credential value was printed, placed on a command line, copied to tracked
  docs, or persisted in evidence.
- Remote operations were read-only SFTP: password-auth SSH connection used only
  to open SFTP, normalize/pwd, bounded directory listings/stat attributes, and
  targeted file reads. No remote shell commands were run, and no remote writes,
  uploads, deletes, renames, permission changes, config edits, server starts,
  or server stops were attempted.
- Current remote layout inspection found one server-root candidate and two
  world candidates. The latest run found `world/ftbquests`,
  `world/ftbteams`, `world/playerdata`, `world/serverconfig`, and `config`.
  No standalone GameStages directory was found; `config/ftbxmodcompat.snbt`
  shows the stage selector config is present.
- No Packwise dump root or complete dump was found:
  `packwise_dump.presence=not_found`, `candidate_dump_count=0`,
  `complete_dump_count=0`. Therefore `validate-dump` and `import-dump` were
  not run for a real dump in this pass.
- Ignored evidence lives at
  `testfiles-return-to-dev/real-server-progress-20260628T052243Z/`. Persistent
  files are `summary.json`, `sanitized-remote-layout-summary.json`,
  `downloaded-files.json`, `README.md`, and seven sanitized sample JSON
  excerpts under `samples/`.
- Downloaded sample metadata was intentionally small and targeted: two
  redacted `world/ftbquests` progress SNBT excerpts, one redacted
  `world/ftbteams/ftbteams.snbt` excerpt, one redacted FTB Teams party SNBT
  excerpt, one redacted FTB Teams player SNBT excerpt, one redacted
  `world/playerdata/*.dat` gzip-NBT string summary, and one redacted
  `config/ftbxmodcompat.snbt` excerpt. Raw native sample bytes were not
  persisted; raw UUIDs, player-name-like fields, long hex identifiers, IPs, and
  password-like assignments were redacted to placeholders.
- Real player progress is partially visible only as native file evidence:
  FTB Quests progress files and FTB Teams files are present and sampled, and
  playerdata exists as gzip-NBT. Exact authoritative counts for
  `ftb_quests`, `player_progress`, `team_progress`, and `stages` are still
  unknown without a Packwise runtime dump or a dedicated native parser.
  `stages_present_non_empty=false` for this no-dump lane, and
  `production_useful_now=false`.
- Missing next step: run `/packwise dump` on the live server, then rerun the
  read-only lane and validate/import the latest complete dump with:

```bash
./scripts/dev validate-dump <local-dump-dir> --require-phase1 --pretty
./scripts/dev import-dump <local-dump-dir> --require-phase1 --pretty
```

- Verification for this no-code-change pass:
  `python -m json.tool` accepted `summary.json`, `downloaded-files.json`,
  `sanitized-remote-layout-summary.json`, and all sample JSON files;
  `git check-ignore -v` confirmed both the secret-file path and the evidence
  path are ignored; `git diff --check` and `git diff --cached --check` passed;
  targeted scans of tracked docs and the final evidence found no concrete
  API-key patterns, inline credentialed SFTP URIs, unsafe password assignments,
  forbidden helper command references, or raw UUID-style player identity
  strings. Expected sanitized placeholders such as `<uuid>`, `<hex-id>`,
  `<id>`, and `<redacted>` remain in ignored evidence; tracked docs also
  contain `<backend-side-secret>` only as a placeholder.
  `./scripts/dev doctor` passed using the repo-local `.packwise-env/`.

## Current State

- Project docs exist in `PROJECT_IDEA.md` and `TECHNICAL_ROUTE.md`.
- The installed StoneBlock 4 instance structure has been documented in `STONEBLOCK4_INSTANCE_STRUCTURE.md` using redacted placeholder paths.
- Connector-agent protocol draft exists in `docs/protocol/CONNECTOR_AGENT_PROTOCOL.md`.
- Python agent harness exists in `apps/agent`.
- Shared Java connector protocol/dump helpers live in `connectors/common`.
- Forge 1.20.1 connector exists in `connectors/forge` for ATM9Sky validation and writes local `packwise-dumps/<dump_id>/` directories.
- Forge connector dumps Phase 1 core runtime truth and now soft-links optional FTB Quests, FTB Teams, and GameStages sections through reflection when those mods are present.
- NeoForge connector skeleton exists in `connectors/neoforge`.
- Runtime dump validation, normalized pack index building, local answering, and ATM9Sky Phase 1 acceptance reporting exist in the agent CLI.
- Runtime dump validation and online connector status expose cross-section consistency errors for duplicate IDs, recipe item references, tag entry counts, tag registry references, typed quest dependencies, completed quest refs, quest item refs, and player stage refs; connector status also reports declared/uploaded/missing sections and `upload_complete` for partial-upload diagnosis.
- The acceptance report now exposes a non-blocking `runtime_progression_truth_ready` check so artifacts show whether runtime advancements, quests, player/team progress, and stages are authoritative in addition to the required core recipe/tag/registry truth.
- Static instance inspection now normalizes PCL2, CurseForge `manifest.json`, Modrinth `modrinth.index.json`, Prism/MultiMC `mmc-pack.json`, and plain Forge/NeoForge server layouts into the same pack/loader profile fields.
- CloudBase has been selected as the preferred public API deployment target: the Minecraft server connector should push authoritative state outbound to CloudBase, while clients query CloudBase directly.
- Java protocol/model tests can run without launching Minecraft.
- Python harness tests can run without launching Minecraft.
- Static FTB Quests parsing exists for chapter/quest/task/reward/dependency skeletons.
- A one-off static Create fan recipe probe is documented in `docs/STATIC_CREATE_FAN_RECIPE_PROBE.md`.

## Important Caveats

- Packwise does not yet have a formal recipe query product surface.
- Static recipe probing can produce useful preloaded indexes, but KubeJS execution, datapack priority, tag expansion, mod conditions, duplicate recipe IDs, and runtime-only registrations still require runtime reconciliation.
- Live ATM9Sky server acceptance is still the hard gate: run `docs/ATM9SKY_PHASE1_ACCEPTANCE.md` against a real server before calling Phase 1 complete.
- The NeoForge connector has a buildable skeleton and protocol upload pieces, but in-game commands and full runtime recipe/tag/registry dumps remain future work.
- The current Python service stores state in memory; durable server/player memory is not implemented yet.
- CloudBase functions must be treated as stateless request handlers. Do not rely on in-process `AgentService` dictionaries for durable state after deployment; persist latest snapshots, manifests, logs, and large dump objects in CloudBase DB/Storage.

## Suggested Next Steps

1. Run the ATM9Sky live server validation in `docs/ATM9SKY_PHASE1_ACCEPTANCE.md` and archive the JSON report.
2. Validate the optional FTB Quests, FTB Teams, and GameStages reflection dump paths on a real ATM9Sky server and adjust API probes if the live mod versions differ.
3. Define the minimum CloudBase schema for `server_snapshots`, `runtime_dumps`, token metadata, and query logs.
4. Define the server connector snapshot push payload and token authentication boundary.
5. Split the Python harness service boundary so the same protocol logic can run behind stateless CloudBase HTTP handlers.
6. Add a NeoForge runtime recipe/tag dump and compare it against static preload output.
7. Keep public fixtures tiny and synthetic unless third-party redistribution rights are explicit.
