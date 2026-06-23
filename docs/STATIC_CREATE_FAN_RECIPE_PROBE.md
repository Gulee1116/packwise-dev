# StoneBlock 4 Static Create Fan Recipe Probe

Date: 2026-06-15

This note records a one-off static probe for Create Encased Fan processing recipes in the installed StoneBlock 4 instance:

`<installed-instance>`

The game instance was treated as read-only. The probe did not start Minecraft.

## Question

Can Packwise answer questions like "what recipes are related to the Create fan, such as bulk smelting and bulk washing" from static files alone, or is a runtime dump mandatory?

## Sources Read

- Mod and datapack recipe JSON under `data/*/recipe/**/*.json`.
- Create mod jar classes to confirm fan processing type mapping.
- KubeJS scripts that add or remove Create/unification recipes:
  - `kubejs\server_scripts\recipes\mods\_create_definitions.js`
  - `kubejs\server_scripts\unification\mods\create.js`
  - `kubejs\startup_scripts\unification.js`
  - `kubejs\server_scripts\unification\remove.js`
  - `kubejs\server_scripts\unification\removals.js`

## Confirmed Create Fan Mapping

Create 6 exposes these fan processing families:

- Bulk washing: `create:splashing`
- Bulk haunting: `create:haunting`
- Bulk smoking: `minecraft:smoking` and `minecraft:campfire_cooking`
- Bulk blasting: `minecraft:blasting`

`minecraft:smelting` was collected as furnace-smelting-related, but it is not confirmed as a separate fan processing type from the Create fan classes observed in this probe.

## Probe Method

1. Scan datapack recipe JSON and recipe JSON embedded in mod jars.
2. Keep recipe types related to Create fan processing.
3. Apply simple top-level `neoforge:conditions` / `fabric:load_conditions` `mod_loaded` filters where statically obvious.
4. Parse simple KubeJS removal calls such as `removeRecipe` / `event.remove`.
5. Infer the structured KubeJS additions in `kubejs\server_scripts\unification\mods\create.js`, especially the material loops for washing/blasting/smelting.

Output artifact:

`<repo-root>\artifacts\static-create-fan-recipes.json`

## Results

Active recipe candidates after static removals:

- Bulk washing: 67
- Bulk haunting: 23
- Bulk smoking: 31
- Bulk blasting: 151
- Furnace smelting, not confirmed as fan type: 229

KubeJS-modeled material set:

`iron`, `gold`, `copper`, `aluminum`, `nickel`, `zinc`, `osmium`, `tin`, `lead`, `uranium`, `platinum`, `silver`

## Static Viability

Static preloading is viable for useful Create fan recipe answers in StoneBlock 4.

For this class of recipe, static analysis works better than expected because Create uses a small fixed set of recipe types and StoneBlock's KubeJS unification scripts are structured enough to pattern-match. It can provide fast offline answers with source and confidence annotations.

Static-only is not enough for the final "100% accurate" target. Runtime recipe dump remains the arbiter for:

- final datapack priority and duplicate recipe IDs
- executed KubeJS output
- tag expansion
- mod condition evaluation beyond simple `mod_loaded`
- recipes removed or mutated through dynamic script logic
- any runtime-only recipe registrations

Recommended path: build a static recipe preload first, then reconcile it with a NeoForge runtime recipe dump when available.

## Implementation Follow-Up

Add a real `inspect-recipes` prototype with:

- jar/datapack JSON recipe scanner
- duplicate ID and pack priority handling
- simple condition filtering
- KubeJS removal extractor
- targeted KubeJS pattern extractors for common recipe helper loops
- source and confidence annotations per recipe
- later runtime dump comparison as ground truth
