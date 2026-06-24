# ATM9Sky Phase 1 Acceptance

This checklist is the reproducible proof path for Packwise Phase 1 on All the
Mods 9: To the Sky. Local tests can prove the framework and connector build;
Phase 1 is accepted only when these steps are run against a real ATM9Sky Forge
1.20.1 server.

## Local Gates

Run from the repository root:

```bash
./scripts/dev doctor
./scripts/dev test-python
./scripts/dev test-java-protocol
./scripts/dev build-forge
./scripts/dev build-neoforge
git diff --check
```

The Forge connector jar is written to:

```text
connectors/forge/build/libs/packwise_connector-0.1.0.jar
```

## Live Server Steps

1. Copy `connectors/forge/build/libs/packwise_connector-0.1.0.jar` into the
   ATM9Sky server `mods/` directory.
2. Start the ATM9Sky server.
3. Run these commands from the server console or as an operator:

```text
/packwise status
/packwise dump
```

`/packwise dump` always writes a local dump directory under
`packwise-dumps/<dump_id>/` unless `PACKWISE_DUMP_DIR` or `-Dpackwise.dumpDir`
overrides the location. The directory must contain `manifest.json` and the
Phase 1 section files:

```text
mods.ndjson
items.ndjson
blocks.ndjson
fluids.ndjson
tags.ndjson
recipes.ndjson
advancements.ndjson
```

`validate-dump --require-phase1` verifies manifest hashes/counts, requires all
Phase 1 section files, rejects non-NDJSON content types for standard runtime
sections, checks recipe/tag references against runtime registries when those
registry sections are present, checks optional quest/progress/stage references
when those sections are present, and fails if any required section is empty:
`mods`, `items`, `blocks`, `fluids`, `tags`, `recipes`, or `advancements`.
Use `build-index --require-phase1` for acceptance evidence; without that flag,
`build-index` remains useful for exploratory partial dumps and reports missing
sections in the generated index.

If the path or manifest is wrong, `validate-dump`, `import-dump`,
`build-index --require-phase1`, and `ask-local` still print a structured JSON
report and exit non-zero.
If an agent URL is configured but upload fails after the local dump is written,
the command still prints `connector_id=...`, `dump_id=...`, `path=...`, and
`upload_error=...`; use the local path for acceptance validation.
If online upload is configured and succeeds, the agent can also be checked with
scoped diagnostic URLs:

```bash
curl "<agent-url>/v1/connectors/<connector_id>"
curl "<agent-url>/v1/connectors/<connector_id>/runtime-dumps/<dump_id>/index-summary"
curl "<agent-url>/v1/connectors/<connector_id>/runtime-dumps/<dump_id>/pack-index"
```

These HTTP checks are useful evidence that `connector.hello` and the runtime
dump reached the agent, but they do not replace the required server log and
local dump validation in the acceptance report.

Keep the server log that contains the `/packwise status` and `/packwise dump`
output, usually `logs/latest.log`. The same log must also include the startup
line `Packwise connector loaded: mod_id=packwise_connector, version=...`, whose
version must match the inspected Forge jar metadata and proves the Forge
connector jar was actually loaded by the ATM9Sky server.
The connector mirrors `/packwise status` and `/packwise dump` response lines to
the Forge server logger, so `logs/latest.log` should contain the same evidence
whether the command was run from the console or by an operator in-game.
`/packwise ask` answer lines, including compact `Sources:` refs, are mirrored
to the same log for optional live answer debugging. The acceptance report
surfaces those refs as the non-blocking `live_packwise_ask_sources_seen` check
when they include a dump-scoped runtime section ref such as
`runtime_dump_section:<dump_id>/recipes`.
The `/packwise status` evidence must include the Forge 47 / Minecraft `1.20.1`
connector identity, `Connector Mod: packwise_connector <version>`, `Connector
ID: ...`, pack line, capabilities line, optional integrations line, and agent
URL line printed by the command. The connector mod version must match the
inspected Forge jar metadata, and the connector ID must match the runtime dump
manifest `connector_id`. The pack line may show `Unknown Pack` if pack identity
JVM properties or environment variables were not configured; the installed
instance and runtime dump checks still prove the ATM9Sky target identity.
The `/packwise dump` evidence must refer to the same dump being validated,
with the manifest `connector_id` printed as `connector_id=...` and either the
manifest `dump_id` printed as `dump_id=...` or the local `path=` printed by the
command.

`/packwise status` prints `Optional integrations: ...`; `/packwise dump` prints
`connector_id=...`, `dump_id=...`, `optional_integrations=...`, and
`optional_sections=...`, which are diagnostic evidence for FTB Quests, FTB
Teams, GameStages, and KubeJS soft-linked support.
When optional sections `ftb_quests`, `player_progress`, `team_progress`, and
`stages` are present and parseable, the acceptance report marks
`runtime_progression_truth_ready` as passing. That check is non-blocking so core
Forge/runtime validation can still pass while live optional integration probes
are being adjusted for a specific ATM9Sky server build.

If the log contains `Packwise skipped recipe ...`, keep it with the acceptance
artifact; the connector skipped a failing custom recipe and continued dumping
the remaining server runtime recipes.

## Acceptance Report

With the ATM9Sky installed instance path, the runtime dump directory, and the
server log available on the development machine, run. The instance path may be a
PCL2 directory, a CurseForge manifest directory, a Modrinth index directory, or a
Prism/MultiMC instance; the static inspector normalizes those into one pack
identity/loader summary.

First prove the real dump and installed instance context import through the
same in-memory `AgentService` handler path used by HTTP connector uploads and
pack index creation:

```bash
./scripts/dev import-dump \
  "<server>/packwise-dumps/<dump_id>" \
  --instance "<installed-atm9sky-instance>" \
  --require-phase1 \
  --pretty
```

```bash
./scripts/dev build-index \
  "<installed-atm9sky-instance>" \
  --runtime-dir "<server>/packwise-dumps/<dump_id>" \
  --require-phase1 \
  --pretty
```

```bash
./scripts/dev phase1-acceptance \
  --instance "<installed-atm9sky-instance>" \
  --runtime-dir "<server>/packwise-dumps/<dump_id>" \
  --server-log "<server>/logs/latest.log" \
  --item-id "<item-with-runtime-recipe-or-quest-ref>" \
  --pretty
```

If `PACKWISE_AGENT_URL` was configured for the server and `/packwise dump`
uploaded successfully, include the running agent URL in the same report:

```bash
./scripts/dev phase1-acceptance \
  --instance "<installed-atm9sky-instance>" \
  --runtime-dir "<server>/packwise-dumps/<dump_id>" \
  --server-log "<server>/logs/latest.log" \
  --agent-url "<agent-url>" \
  --item-id "<item-with-runtime-recipe-or-quest-ref>" \
  --pretty
```

When `--agent-url` is supplied, the report verifies
`GET /v1/connectors/<connector_id>` and the scoped
`GET /v1/connectors/<connector_id>/runtime-dumps/<dump_id>/pack-index`, then
posts a `query.ask` to `/v1/query/ask` with the same connector and dump context.
It blocks if the online agent does not show the same accepted `connector.hello`,
the same connector mod ID/version as the inspected jar in both the hello context
and runtime dump summary, the same runtime `dump_id`, non-empty indexed summaries
for all seven required Phase 1 runtime sections, `upload_complete: true` for
the manifest-declared sections, an empty `runtime_consistency_errors` list for
that uploaded dump, a pack index with runtime-authoritative
registries/tags/recipes, and an answer with concrete source references. Omit
`--agent-url` for offline/local-dump validation runs.

The command exits non-zero until live server evidence is present and every
required check passes. Blocked reports include `next_actions`, derived from the
failed required checks, with the concrete remediation needed before rerunning
the command. A passing report means:

- the Forge jar contains the connector entrypoint, command handler, runtime
  dump collectors, and shared protocol classes;
- the Forge jar metadata identifies `packwise_connector` and targets Forge 47 /
  Minecraft `1.20.1`;
- the runtime dump manifest, counts, hashes, registry/progression references,
  and Phase 1 sections validate;
- the dump identity is Forge 47 + Minecraft `1.20.1`;
- the runtime dump manifest connector mod ID/version matches the inspected
  Forge jar metadata;
- all required Phase 1 runtime sections are non-empty:
  `mods`, `items`, `blocks`, `fluids`, `tags`, `recipes`, and `advancements`;
- the runtime dump and installed instance context import through `AgentService`
  and build the service-side Packwise index;
- the installed instance selects the `atm9sky` pack profile;
- the normalized Packwise index treats registries, tags, and recipes as
  runtime-authoritative;
- the report separately shows whether advancements, quests, player/team
  progress, and stages are also runtime-authoritative through the optional
  `runtime_progression_truth_ready` check;
- the generic Forge `1.20.1` pack profile remains selectable for a second
  Forge pack without code changes;
- the local answer path returns source references, and item-anchored answers
  cite concrete `recipe` or `quest` refs for the chosen `--item-id`;
- the four Phase 1 answer scenarios (`下一步该干什么？`, `这个物品怎么解锁？`,
  `为什么 JEI/网上配方和服务器不一样？`, `当前目标缺哪些前置机器/任务/材料？`)
  all return the required source references;
- the live server log shows the Forge connector loaded;
- the live server log shows complete `/packwise status` output and `/packwise
  dump` output for the validated connector id and dump id/path;
- if `--agent-url` was supplied, the online agent reports the same connector
  hello plus runtime dump connector mod ID/version, the same runtime dump under
  `GET /v1/connectors/<connector_id>` with all seven required Phase 1 section
  counts non-empty, every manifest-declared section uploaded, and no runtime
  consistency errors, and the scoped `pack-index` endpoint builds from the
  uploaded runtime sections;
- if `--agent-url` was supplied, `/v1/query/ask` answers against that same dump
  with runtime or item-specific source references.

For an artifact file:

```bash
./scripts/dev phase1-acceptance \
  --instance "<installed-atm9sky-instance>" \
  --runtime-dir "<server>/packwise-dumps/<dump_id>" \
  --server-log "<server>/logs/latest.log" \
  --agent-url "<agent-url>" \
  --item-id "<item-with-runtime-recipe-or-quest-ref>" \
  --output artifacts/atm9sky-phase1-acceptance.json \
  --pretty
```

The report includes SHA-256 and size evidence for the inspected Forge jar,
server log, runtime dump `manifest.json`, and each runtime dump section, so the
saved artifact can be tied back to the exact files used for acceptance.

If the command reports `status: "blocked"` only because the server log is
missing, local readiness is proven but live ATM9Sky acceptance is still open.
