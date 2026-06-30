# Packwise Forge Connector

Forge connector for Minecraft 1.20.1 modpacks, with ATM9 To The Sky as the
first validation target.

The connector keeps pack-specific identity outside code. Configure these
optional JVM properties or environment variables on the server:

- `packwise.agentUrl` / `PACKWISE_BACKEND_BASE_URL` / `PACKWISE_AGENT_BASE_URL` / `PACKWISE_AGENT_URL`
- `packwise.dumpDir` / `PACKWISE_DUMP_DIR`
- `packwise.connectorId` / `PACKWISE_CONNECTOR_ID`
- `packwise.packId` / `PACKWISE_PACK_ID`
- `packwise.packName` / `PACKWISE_PACK_NAME`
- `packwise.packVersion` / `PACKWISE_PACK_VERSION`

`PACKWISE_BACKEND_BASE_URL` and `PACKWISE_AGENT_BASE_URL` are Packwise backend
URLs, not model provider URLs. `PACKWISE_AGENT_URL` remains a legacy alias for
the same backend address.
Do not configure `PACKWISE_LLM_BASE_URL`, `PACKWISE_LLM_MODEL`, or
`PACKWISE_LLM_API_KEY` on the Minecraft server. In centralized deployments,
only the Packwise backend talks to the OpenAI-compatible model provider, and
`PACKWISE_LLM_MODEL` on that backend should be `deepseek-v4-pro`.

If pack identity is not configured, the connector tries to infer it from common
server-side metadata files in the working directory: `modpackinfo.json`,
CurseForge `manifest.json`, or `modrinth.index.json`. Explicit JVM properties
or environment variables always take precedence over inferred metadata.

Commands:

- `/packwise status`
- `/packwise dump`
- `/packwise ask <question>`

`/packwise dump` collects mods, items, blocks, fluids, tags, recipes, potions,
mob effects, and advancements. Recipe rows include `ingredient_slots` in
addition to the backward-compatible de-duplicated `ingredient_items`, so special
crafting recipes can preserve slot counts, NBT candidates, and shaped dimensions
when available. If an agent URL is configured it uploads the runtime dump through
the shared connector protocol, sending `connector.hello` before the dump
manifest so the agent has loader, pack, and capability context. It always writes
a local dump first; by default that is under `packwise-dumps/<dump_id>/`
relative to the server working directory, with `manifest.json` and one
`*.ndjson` file per section. If the agent upload fails after the local write
succeeds, the command still prints the local `connector_id`, `dump_id`, `path`,
and an `upload_error=...` diagnostic so the dump can be validated/imported from
disk.
After a successful online upload, `GET /v1/connectors/<connector_id>` on the
agent returns the accepted `connector.hello` context plus the uploaded runtime
dump summaries. Use the scoped dump URLs such as
`/v1/connectors/<connector_id>/runtime-dumps/<dump_id>/index-summary` to confirm
the uploaded dump was indexed under the same connector ID. The status summary
also reports `declared_sections`, `uploaded_sections`, `missing_sections`, and
`upload_complete` so interrupted section uploads are visible. The hello context
and runtime dump summary include `connector_mod_id` and `connector_version`,
which the acceptance report matches against the inspected Forge jar when
`--agent-url` is supplied.

When the corresponding mods are loaded, `/packwise dump` also attempts guarded
optional runtime sections through reflection:

- `ftb_quests` from FTB Quests server quest data.
- `player_progress` from FTB Quests team data and GameStages player stages.
- `team_progress` from FTB Quests team data, with FTB Teams roster metadata
  when available.
- `stages` from GameStages player stage data.

These integrations are soft-linked. If an optional API is absent or changes,
the optional section is skipped and the required Phase 1 sections still dump.

`/packwise status` prints the connector mod version, connector ID, and optional
integration load state, and `/packwise dump` prints `connector_id`, `dump_id`,
`optional_integrations`, and `optional_sections` details for live log
diagnostics.

Recipe dumping is isolated per recipe. If a custom recipe throws while being
serialized, the connector logs `Packwise skipped recipe ...` and continues
writing the remaining runtime recipes instead of failing the whole dump.

`/packwise ask` sends a `query.ask` request to the configured agent. After a
successful `/packwise dump` upload, the connector includes that dump ID in ask
context so answers can cite runtime recipes, tags, potions, mob effects, and
advancements. When the
command source is a player, the connector also includes `player_id` and
`player_name` so the agent can scope runtime progress to that player or team
instead of using aggregate server progress. The command prints the answer
summary, next steps, compact `Sources:` refs, and confidence so player-facing
answers retain their runtime or quest evidence. Runtime refs should stay
dump-scoped, for example `runtime_dump_section:<dump_id>/recipes`, so live
validation can tie the answer back to the uploaded dump. These answer lines are
mirrored to the Forge server logger for live validation and debugging.

ATM9Sky validation flow:

```text
/packwise status
/packwise dump
```

Then copy or point the agent harness at the generated dump directory:

```bash
./scripts/dev validate-dump "packwise-dumps/<dump_id>" --require-phase1 --pretty
./scripts/dev import-dump "packwise-dumps/<dump_id>" --instance "<installed-instance>" --require-phase1 --pretty
./scripts/dev build-index "<installed-instance>" --runtime-dir "packwise-dumps/<dump_id>" --require-phase1 --pretty
./scripts/dev ask-local "<installed-instance>" --runtime-dir "packwise-dumps/<dump_id>" --item-id "minecraft:stone" --question "当前目标缺哪些前置机器/任务/材料？" --pretty
```

For the full Phase 1 acceptance evidence report, keep the server log that
contains the `/packwise status` and `/packwise dump` output and run from the
repository root:

The log should also include `Packwise connector loaded:
mod_id=packwise_connector, version=...` from server startup; the acceptance
report requires that version to match the inspected jar metadata and treats it
as the live proof that Forge loaded the connector jar.
The connector also mirrors `/packwise status` and `/packwise dump` response
lines to the Forge server logger, so `logs/latest.log` should contain the
evidence even when an operator runs the commands in-game.
The `/packwise status` evidence should include the Forge 47 / Minecraft 1.20.1
connector identity, `Connector Mod: packwise_connector <version>`, `Connector
ID: ...`, pack, capabilities, optional integrations, and agent URL lines. The
connector mod version must match the inspected jar metadata. The `/packwise
dump` evidence should include `connector_id=` plus `dump_id=` or `path=` for
the same dump directory being validated. The connector ID in both command
outputs must match the runtime dump manifest `connector_id`. If pack identity
properties were not configured, the status pack line may say `Unknown Pack`;
the acceptance report still verifies ATM9Sky identity from the installed
instance and runtime dump.

```bash
./scripts/dev phase1-acceptance \
  --instance "<installed-atm9sky-instance>" \
  --runtime-dir "packwise-dumps/<dump_id>" \
  --server-log "<server>/logs/latest.log" \
  --agent-url "<agent-url-if-online-upload-was-enabled>" \
  --item-id "<item-with-runtime-recipe-or-quest-ref>" \
  --pretty
```

Only pass `--agent-url` when the server used `PACKWISE_BACKEND_BASE_URL`,
`PACKWISE_AGENT_BASE_URL`, legacy `PACKWISE_AGENT_URL`, or `-Dpackwise.agentUrl`
and the upload succeeded. With that option, the acceptance
report checks the running agent's `GET /v1/connectors/<connector_id>` response
for the same accepted hello context and dump ID, verifies every declared section
uploaded, then checks the scoped `pack-index` endpoint for a
runtime-authoritative index built from the uploaded sections and `/v1/query/ask`
for an answer with source references.
