# FTB StoneBlock 4 已安装实例结构

扫描日期：2026-06-14

检查路径：`<installed-instance>`

本次检查是只读扫描，没有改动已安装游戏目录。

## 概览

这个目录是 PCL2 安装后的 FTB StoneBlock 4 版本隔离实例。它不只是 vanilla `.minecraft\versions\<version>` 那种只存 jar/json 的版本元数据目录；PCL2 把这个版本目录同时作为游戏目录使用，所以整合包实际内容直接落在该根目录下。

关键身份信息：

- 整合包：`FTB StoneBlock 4`
- 整合包版本：`1.14.2`
- Minecraft：`1.21.1`
- Loader：NeoForge `21.1.233`
- 主类：`cpw.mods.bootstraplauncher.BootstrapLauncher`
- 启动目标：`forgeclient`
- `mods/` 中实际安装的 mod jar：`404`

证据：

- `PCL\Setup.ini` 包含 `VersionVanillaName:1.21.1`、`VersionNeoForge:21.1.233`、`VersionArgumentIndieV2:True`。
- `FTB StoneBlock 4.json` 的启动参数包含 `--fml.neoForgeVersion 21.1.233`、`--fml.mcVersion 1.21.1`、`--launchTarget forgeclient`。
- `modpackinfo.json` 标识中文整合包名为 `石头世界4`，版本 `1.14.2`。

## 安装形态

原始文件 `<repo-root>\Raw-stoneblock-modpack\ftb-stoneblock-4-1.14.2.zip` 是 CurseForge manifest 风格整合包。结合已安装实例判断，PCL2 大概率按如下方式安装：

1. 读取 CurseForge `manifest.json`。
2. 创建名为 `FTB StoneBlock 4` 的 Minecraft `1.21.1` + NeoForge `21.1.233` 版本。
3. 写入 PCL/vanilla 启动元数据：`FTB StoneBlock 4.json`、`FTB StoneBlock 4.jar`、`PCL\Setup.ini`。
4. 启用版本隔离，因此 `${game_directory}` 解析到已安装实例目录。
5. 下载/解析 mod jar 到 `mods/`。
6. 把整合包 overrides 复制到实例根目录，形成 `config/`、`kubejs/`、`datapacks/`、`defaultconfigs/` 等目录。
7. 原始项目目录里的 sidecar mods，包括 `CustomSkinLoader_Universal-14.28.jar` 和 `jecharacters-1.21-neoforge-4.5.24.jar`，也出现在已安装实例的 `mods/` 中。

原始 manifest 有 409 个 CurseForge 文件引用，而当前已安装实例的 `mods/` 中有 404 个 jar。Packwise 应把已安装实例视为比分发 manifest 更强的本地静态事实源，因为启动器可能在安装时跳过、替换、去重或额外加入文件。

## 顶层结构

| 路径 | 文件数 | 目录数 | Packwise 处理建议 |
| --- | ---: | ---: | --- |
| `mods/` | 404 | 0 | 高价值输入。解析 jar 元数据，并作为 runtime dump 的 classpath 背景。 |
| `config/` | 1923 | 151 | 高价值输入。包含 FTB Quests 和大量 mod 配置。 |
| `kubejs/` | 1158 | 285 | 高价值输入。包含自定义配方、阶段、资产和脚本。 |
| `datapacks/` | 2790 | 888 | 高价值输入。包含配方、交易、结构、标签和数据文件。 |
| `defaultconfigs/` | 11 | 5 | 高价值输入。包含 FTB mods、AE2 等默认服务端/客户端配置。 |
| `configureddefaults/` | 6 | 3 | 中价值输入。主要是启动器/整合包默认设置，不一定是进度事实。 |
| `resourcepacks/` | 43 | 27 | 中价值输入。需要 lang/assets 时再解析。 |
| `shaderpacks/` | 617 | 41 | 默认忽略。只影响视觉。 |
| `dynamic-resource-pack-cache/` | 539 | 0 | 默认忽略。生成缓存。 |
| `logs/` | 11 | 4 | 默认忽略。运行时/隐私/调试数据。 |
| `saves/` | 0 | 0 | 默认忽略。世界和玩家数据，隐私敏感。 |
| `PCL/` | 1 | 0 | 只解析启动器元数据，例如版本隔离和 loader 信息。 |
| `ftbteambases/` | 92 | 29 | 运行时团队基地数据。客户端实例中默认不摄取。 |
| `local/` | 13 | 7 | 本地运行状态。默认不摄取。 |
| `cache/` | 2 | 1 | 默认忽略。生成缓存。 |

根目录文件：

- `FTB StoneBlock 4.json`：启动器/版本元数据。
- `FTB StoneBlock 4.jar`：该版本的 Minecraft client jar。
- `modpackinfo.json`：整合包元数据和中文翻译元数据。
- `default-server.properties`：整合包附带的默认服务端配置。
- `options.txt`：用户本地客户端设置，默认忽略。
- `patchouli_data.json`：小型 Patchouli 运行时/缓存标记。
- `LICENSE`：整合包许可文本。

## 高价值事实源

### FTB Quests

路径：`config\ftbquests\quests`

观察结果：

- `64` 个 SNBT 文件。
- `22` 个章节文件位于 `chapters/`。
- 根文件包括 `chapter_groups.snbt` 和 `data.snbt`。

章节文件：

- `bounty_board.snbt`
- `creative.snbt`
- `draconic_evolution.snbt`
- `exploration__combat.snbt`
- `gearing_up.snbt`
- `general_magic.snbt`
- `getting_started.snbt`
- `logistics__storage.snbt`
- `mekanism.snbt`
- `oritech.snbt`
- `power.snbt`
- `processing__automation.snbt`
- `resource_generation.snbt`
- `technology.snbt`
- `thebackrooms.snbt`
- `useful_items_tips.snbt`
- `welcome.snbt`
- `world_engine__tier_1.snbt`
- `world_engine__tier_2.snbt`
- `world_engine__tier_3.snbt`
- `world_engine__tier_4.snbt`
- `world_engine__tier_5.snbt`

重要影响：任务书不是单纯说明书。它编码了进度、依赖、奖励和 game stage。多个任务文件提到 `gamestage`，并且 KubeJS 有脚本会把任务完成状态同步到玩家/队伍阶段。

### KubeJS

路径：`kubejs`

观察到的文件类型：

- `.png`：410
- `.md`：287
- `.js`：209
- `.json`：160
- `.ogg`：51
- `.mcmeta`：34
- `.nbt`：3

重要子目录：

- `kubejs\server_scripts`：189 个 JS 文件。
- `kubejs\server_scripts\recipes`：85 个 JS 文件。
- `kubejs\server_scripts\systems`：28 个 JS 文件。
- `kubejs\server_scripts\unification`：27 个 JS 文件。
- `kubejs\server_scripts\tags`：8 个 JS 文件。
- `kubejs\startup_scripts`：14 个 JS 文件。
- `kubejs\client_scripts`：6 个 JS 文件。
- `kubejs\data`：10 个 JSON 文件，包括自定义 `ftb:machine` 定义。

代表性脚本证据：

- `event_handlers\player\quest_stage_sync.js` 监听 FTB quest 完成事件，并把 team stages 同步给玩家。
- `event_handlers\player\stage_sync.js` 在玩家登录时同步 team stages 到 player stages。
- `event_handlers\player\quest\worldengine_quests.js` 处理世界引擎结构/机器重置的自定义任务奖励。
- `recipes\disable.js` 和 `recipes\removals.js` 会移除配方、隐藏禁用物品。
- `recipes\mods\*.js` 添加或替换 mod 专属配方。
- `startup_scripts\registry\items.js` 定义 KubeJS 自定义物品。

重要影响：KubeJS 必须是一等事实源。只做静态 datapack recipe parser 会漏掉移除、替换、自定义配方、自定义阶段和运行时事件行为。

### Datapacks

路径：`datapacks`

观察结果：

- 总文件数：2790。
- JSON 文件：2040。
- NBT 文件：742。
- `datapacks\ftb\data` 下的 recipe JSON：371。

从抽样解析中看到的配方类型包括：

- `minecraft:crafting_shaped`
- `minecraft:crafting_shapeless`
- `minecraft:stonecutting`
- `industrialforegoing:dissolution_chamber`
- `apotheosis:sized_upgrade_recipe`
- `avaritia:extreme_shaped`
- `avaritia:compressor`
- `oritech:fuel_generator`
- `immersiveengineering:thermoelectric_source`
- `extendedae:crystal_assembler`
- `gateways:gate_recipe`

重要影响：配方解析必须是 schema-extensible 的。大量重要配方不是 vanilla crafting。

### Mods

路径：`mods`

观察结果：

- `404` 个 jar 文件。
- FTB 相关 jar 包括 `ftb-quests-neoforge-2101.1.24.jar`、`ftb-teams-neoforge-2101.1.10.jar`、`ftb-team-bases-21.1.13.jar`、`ftb-xmod-compat-neoforge-21.1.8.jar` 等。
- 配方/查看器/脚本生态包括 `jei-1.21.1-neoforge-19.27.0.340.jar`、`kubejs-neoforge-2101.7.2-build.368.jar`、`almostunified-neoforge-1.21.1-1.4.2.jar` 和相关兼容包。

重要影响：jar metadata 能识别已安装 mod，但最准确的配方、标签和物品注册表需要从实际 NeoForge 环境中的 registry 和 recipe manager dump 出来。

## 隐私与忽略规则

对用户提供的客户端实例，Packwise 默认不应摄取这些内容：

- `logs/`
- `saves/`
- `crash-reports/`，如果存在
- `screenshots/`，如果存在
- `options.txt`
- `servers.dat`，如果存在
- `usercache.json`，如果存在
- `local/`
- `ftbteambases/`
- `cache/`
- `dynamic-resource-pack-cache/`
- 任何启动器账号、session、token 相关文件，如果存在

Packwise 可以报告这些目录存在、统计文件数量，但默认不复制、不索引其内容，除非用户显式授权。

## 对 Packwise 的影响

1. 已安装 PCL2 实例足以提供很强的静态快照：pack identity、实际 mod 列表、config、FTB Quests、KubeJS、datapacks、docs/assets。
2. 它本身不足以做服务器实时指导。服务器里的多人进度、玩家状态、任务完成情况，需要 connector 或服务端 dump。
3. 它本身也不足以保证配方真值 100% 准确。动态注册、运行时 recipe manager 和标签最终需要 NeoForge-side dumper。
4. 第一版 `packwise inspect <path>` 至少应该支持两种输入：
   - `<repo-root>\Raw-stoneblock-modpack` 这种 CurseForge manifest 包目录；
   - 当前这种 PCL2 已安装隔离实例目录。
5. 输入路径永远按只读处理。Packwise 只把抽取/索引产物写入自己的 workspace/cache。

## 推荐下一步 Harness

轻量 harness：

- 静态 inspector 读取 launcher metadata、`mods/`、`config/ftbquests`、`kubejs`、`datapacks`、`defaultconfigs` 和 pack metadata。
- 建立可查询的 source inventory，记录文件 hash 和 source references。
- 把 FTB Quests SNBT 解析为 chapters、quests、dependencies、tasks、rewards 和 stage metadata。
- 用 schema registry 解析 datapack JSON recipes/tags。
- 对 KubeJS 文本建索引，并保守识别常见 recipe/removal/stage 模式。

中量 harness：

- 启动或接入本地 NeoForge server/client，加载 Packwise dump mod。
- 在所有 mods/scripts 完成加载后，dump item/block/fluid registries、tags、recipes、advancements、FTB Quests definitions、stage data 和 mod list。
- 把 runtime dump 与静态解析对比，并标记冲突。

重量 harness：

- 基于 runtime dump、quest、stage 数据构建标准化 progression graph。
- 为目标物品查询和下一步建议生成确定性的 answer packet。
- 让便宜/本地模型解释和排序预计算路线，而不是对原始文件做自由 ReAct。
