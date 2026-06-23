# Packwise Technical Route

这个文档记录当前技术路线，预期会频繁调整。稳定的项目定位和预计产物放在 `PROJECT_IDEA.md`。

## 当前假设

- 主要运行场景是 Minecraft 整合包服务器。
- 早期优先支持只读指导，不让 agent 执行危险服务器命令。
- 整合包来源包括 CurseForge、Modrinth 和普通 zip。
- 服务端 loader 需要覆盖 Fabric、Forge、NeoForge，但可以先选一个落地。
- Agent 需要以整合包实际文件为准，通用互联网资料只能作为补充。
- Python 可以作为早期 harness 和 agent service 实现语言，但不能成为玩家或服主安装 mod 时的运行前提。
- Minecraft 侧连接器必须按 mod 生态分发，优先使用 JVM 语言实现。

## 分发与运行时兼容性

核心原则：`Python-first harness, JVM-first connector, runtime-agnostic protocol`。

含义：

- Python 优先用于早期离线解析、索引、RAG/KG 实验、评测 harness 和 agent service 快速迭代。
- Python 不进入 Minecraft mod 的硬依赖链；玩家和服主不应被要求自行安装 Python。
- Minecraft 侧的 client/server connector 和 runtime dumper 用 Java/Kotlin 实现，作为 NeoForge/Fabric/Forge mod 分发。
- connector 不直接调用 Python 代码，而是通过稳定协议交换 JSON/NDJSON/HTTP/WebSocket 数据。
- agent service 可以用 Python 实现，但发布给普通用户时需要被打包为桌面 exe、Docker 镜像、服务端二进制包，或由 Packwise 托管。

推荐分发形态：

- 用户端 only：客户端 mod + 本地/远程 agent。适合查询本地整合包知识、物品来源、任务文本和个人记忆，但拿不到完整服务器权威进度。
- 服务端 only：服务端 mod + agent。适合服务器聊天命令、多人共同上下文、任务/阶段/队伍进度同步，是主推荐形态。
- 用户端 + 服务端同时存在：服务端提供权威状态，客户端提供更好的 UI、个人偏好、快捷交互和本地上下文；这是体验最完整的形态。

协议边界：

- connector 输出事实：pack identity、mod list、registries、recipes、tags、quests、advancements、player/team progress、stage state。
- agent 输出建议：answer packet、route plan、next-step recommendation、source refs、confidence/uncertainty。
- 双方只共享结构化数据和能力声明，不共享语言运行时。

## 当前样本包实测

路径：`<repo-root>\Raw-stoneblock-modpack`

目录内容：

- `ftb-stoneblock-4-1.14.2.zip`
- `CustomSkinLoader_Universal-14.28.jar`
- `jecharacters-1.21-neoforge-4.5.24.jar`

`ftb-stoneblock-4-1.14.2.zip` 是 CurseForge manifest 风格整合包，而不是已安装好的 Minecraft 实例。

manifest 关键信息：

- name: `FTB StoneBlock 4`
- version: `1.14.2`
- Minecraft: `1.21.1`
- loader: `neoforge-21.1.233`
- recommended RAM: `8192`
- overrides directory: `overrides`
- CurseForge file references: `409`

zip 内容概况：

- `manifest.json`: 1 个
- `overrides`: 6551 个文件
- `overrides/config`: 1871 个文件
- `overrides/datapacks`: 2790 个文件
- `overrides/kubejs`: 1141 个文件
- `overrides/mods`: 3 个内置 jar
- `overrides/config/ftbquests/quests`: FTB Quests 任务线

安装方式推断：

1. PCL2 导入 `ftb-stoneblock-4-1.14.2.zip`。
2. PCL2 读取 `manifest.json`，创建 MC `1.21.1` + NeoForge `21.1.233` 实例。
3. PCL2 根据 manifest 中的 CurseForge `projectID` + `fileID` 下载 409 个必需文件，通常落到实例的 `mods/`。
4. PCL2 将 `overrides/` 目录内容复制到实例根目录，例如 `config/`、`kubejs/`、`datapacks/`、`defaultconfigs/`。
5. 当前目录里的两个外部 jar 不在 zip manifest 内，需要作为 sidecar mods 处理；如果只导入 zip，它们不会自动安装。

对 Packwise 的影响：

- `packwise inspect <path>` 需要能识别“目录里包含一个 CurseForge zip + 若干 sidecar jar”的输入形式。
- 只解析这个 zip 可以拿到任务、KubeJS、datapacks、配置和 3 个内置 jar，但拿不到 409 个 CurseForge 依赖 jar 的实际文件内容。
- 想完整解析所有 mod 内置 recipe、tag、Patchouli、lang 和 mod metadata，需要读取 PCL2 已安装实例的 `mods/`，或实现 CurseForge 文件解析/下载流程。
- Sidecar jar 要进入实际 mod 列表，但应标记来源为 `sidecar`，和 manifest 下载项区分。

## 已安装 StoneBlock 4 实例实测

路径：`<installed-instance>`

详细结构记录见 `STONEBLOCK4_INSTANCE_STRUCTURE.md`。

结论：

- 这是 PCL2 安装后的版本隔离实例；版本目录同时是游戏目录。
- `PCL\Setup.ini` 和 `FTB StoneBlock 4.json` 均确认 Minecraft `1.21.1` + NeoForge `21.1.233`。
- `mods/` 内实际有 `404` 个 jar，应优先于原始 manifest 的依赖数量作为本地静态事实。
- `config\ftbquests\quests` 有 `64` 个 SNBT 文件、`22` 个章节，是进度图的核心来源。
- `kubejs/` 有 `1158` 个文件，其中 `server_scripts/recipes` 有 `85` 个 JS 文件，并且存在 quest/stage 同步逻辑。
- `datapacks/` 有 `2790` 个文件，其中 `datapacks\ftb\data` 下识别到 `371` 个 recipe JSON。

路线影响：

- Packwise 第一版必须支持“已安装实例目录”输入，而不只是压缩包。
- KubeJS 不能放到低优先级补充层；对 StoneBlock 4，它是配方、阶段、事件和自定义机器的重要事实源。
- 为了追求 100% 准确信息查找，静态解析必须和 NeoForge runtime dump 结合。只读静态扫描可以建立索引和候选图，但最终配方/标签/注册表应以运行后 dump 为准。
- 客户端已安装实例不足以回答服务器实时进度；多人进度、玩家状态和任务完成情况需要服务器 connector 或服务端 dump。

## 推荐架构

```text
Modpack zip / mrpack
        |
        v
Packwise Core
  - unpack
  - detect loader/version
  - parse recipes/tags/quests/docs/scripts
  - normalize entities
  - build indexes and progression graph
        |
        v
Packwise Agent Service
  - query API
  - route planner
  - retrieval
  - answer generation
  - source citations
        ^
        |
Minecraft Server Connector
  - commands
  - player state
  - advancements
  - quest progress
  - websocket/http sync
        |
        v
Players in server chat
```

## 组件拆分

### `packwise-core`

解析和索引整合包。

职责：

- 解包并识别整合包格式。
- 解析基础 metadata。
- 抽取 recipes、tags、advancements、loot tables。
- 抽取 FTB Quests、Patchouli、KubeJS、CraftTweaker 等高价值来源。
- 输出标准化实体和关系。

早期技术选择：

- 语言：Python-first，用于 harness、离线解析、索引和 agent 快速迭代；不作为 mod 用户侧硬依赖。
- 存储：SQLite。
- 搜索：SQLite FTS 起步，后续再加向量索引。
- 图：先用关系表表达 recipe/progression graph，不急着引入图数据库。

### `packwise-agent`

对外提供问答和规划能力。

职责：

- 接收自然语言问题。
- 从结构化图和文本索引检索上下文。
- 根据服务器状态生成建议。
- 返回可追溯来源。

关键能力：

- `ask(question, server_context?)`
- `next_steps(player_or_team_context)`
- `plan_goal(target_item, current_state)`
- `explain_recipe(item_id)`
- `explain_blocker(goal, current_state)`

### `packwise-connector`

Minecraft 连接器和 runtime dumper。

职责：

- 注册 `/packwise` 命令。
- 读取必要服务器状态。
- 把状态同步到 agent service。
- 把 agent 的回答发回游戏聊天。
- 在服务端或客户端运行时 dump registries、recipes、tags、quests、advancements 等真值。
- 暴露 connector capabilities，说明当前是在 client-only、server-only 还是 client+server 协同形态下运行。

实现约束：

- 使用 Java/Kotlin 等 JVM 生态语言，按普通 mod 方式分发。
- 不依赖系统 Python。
- 与 agent service 之间只通过协议通信。

建议拆分：

```text
connector-common
connector-client-common
connector-server-common
connector-fabric
connector-forge
connector-neoforge
```

早期可先只做 NeoForge server-side connector/runtime dumper，因为当前样本包就是 NeoForge。等协议稳定后再补客户端能力和其他 loader。

### `packwise-web`

Web 控制台。

职责：

- 上传整合包。
- 展示解析进度。
- 浏览任务线、配方链、缺失材料。
- 管理服务器连接和 token。

早期可以先不做完整 UI，用简单开发页面验证 API。

## 数据模型草案

核心实体：

- `Pack`
- `Mod`
- `Item`
- `Block`
- `Fluid`
- `Recipe`
- `RecipeInput`
- `RecipeOutput`
- `Tag`
- `Quest`
- `QuestChapter`
- `QuestDependency`
- `Advancement`
- `DocumentPage`
- `ScriptPatch`
- `SourceRef`

服务器实体：

- `Server`
- `Player`
- `Team`
- `InventorySnapshot`
- `ProgressSnapshot`
- `DimensionState`
- `KnownStorage`

核心关系：

- item produced by recipe
- item consumed by recipe
- item belongs to tag
- quest depends on quest
- quest unlocks item or stage
- advancement unlocks stage
- document mentions item
- player/team has item
- player/team completed quest

## 解析优先级

### 第一优先级

- 已安装实例 metadata：PCL/launcher metadata、version JSON、modpack metadata。
- 整合包 manifest 和 mod 列表。
- `data/*/recipes/**/*.json`
- `data/*/tags/**/*.json`
- `data/*/advancements/**/*.json`
- FTB Quests。
- KubeJS server/startup scripts 中的 recipe、removal、tag、stage、quest hook。
- Patchouli 文档。

### 第二优先级

- CraftTweaker scripts。
- 常见 config 中影响配方、矿物、世界生成和难度的配置。
- KubeJS client scripts 和 assets 文档。

### 第三优先级

- Mod 专用 API 或复杂内部数据。
- JEI/REI runtime-only 信息。
- 机器状态和世界扫描。

## Server Connector 路线

### 命令设计

建议命令：

- `/packwise ask <question>`
- `/packwise next`
- `/packwise goal <item>`
- `/packwise missing <item>`
- `/packwise sync`
- `/packwise status`

### 同步内容

早期同步：

- 玩家 UUID、名称。
- 当前维度。
- 背包快照。
- advancement 完成状态。
- FTB Quests 进度，如果当前 loader 和版本可接入。

后续同步：

- 末影箱。
- 团队共享任务进度。
- 重要存储系统摘要。
- 玩家死亡点、传送点、waypoint。
- 已探索维度和关键结构。

### 安全边界

默认只读。

需要明确禁止或单独授权：

- 执行服务器命令。
- 修改玩家背包。
- 修改世界方块。
- 读取敏感服务器文件。
- 泄露服务器地址、token、玩家身份信息。

## Agent 回答策略

优先顺序：

1. 结构化数据：配方、任务依赖、advancement、标签。
2. 整合包内文本：Patchouli、任务描述、脚本注释。
3. 服务器状态：玩家资源、团队进度、当前阶段。
4. LLM 常识和外部资料。

回答必须尽量包含：

- 结论。
- 下一步行动。
- 缺少材料或前置条件。
- 来源引用。
- 不确定性说明。

## 初期里程碑

### Milestone 0：项目骨架

- 建立文档。
- 确认仓库结构。
- 放入一个真实整合包样本或 fixture。
- 明确第一个支持的 loader。

### Milestone 1：离线解析 MVP

- 支持上传或指定整合包 zip。
- 识别格式、版本、loader、mod 列表。
- 解析 vanilla/datapack recipes 和 tags。
- 输出 SQLite 数据库。
- 提供 CLI 查询物品配方。

### Milestone 2：知识问答 MVP

- 接入文本索引。
- 支持对任务、Patchouli 页面、配方进行检索。
- 支持 `ask` API。
- 回答带来源。

### Milestone 3：服务端只读接入

- 实现第一个 connector。
- 支持 `/packwise status`、`/packwise ask`、`/packwise next`。
- 同步玩家背包和 advancement。
- Agent 能结合当前玩家状态回答。

### Milestone 4：多人进度

- 支持团队级 progress snapshot。
- 支持目标路径规划。
- 支持 Web 页面查看团队缺口。

## 建议仓库结构

```text
Packwise/
  PROJECT_IDEA.md
  TECHNICAL_ROUTE.md
  README.md
  apps/
    agent/
    web/
  packages/
    core/
    shared/
  connectors/
    common/
    fabric/
    forge/
    neoforge/
  fixtures/
    modpacks/
  docs/
  scripts/
```

## 待决策

- 第一版 connector 优先 Fabric、Forge 还是 NeoForge。
- 第一版 agent service 是只提供 CLI/API，还是同时提供打包后的本地桌面服务。
- 是否先支持 `.mrpack`，还是先支持当前手上的原始整合包目录。
- FTB Quests 目标版本和文件格式。
- 是否需要 Discord/飞书等外部聊天入口。

## 近期下一步

1. 建立 Python-first 最小 CLI：`packwise inspect <path>`。
2. 支持两种输入：CurseForge manifest 包目录、PCL2 已安装实例目录。
3. 先输出 pack identity、loader、Minecraft 版本、实际 mod jar 数、FTB Quests 章节数、KubeJS 脚本数、datapack recipe 数。
4. 加上隐私/缓存目录 ignore 规则，默认不读取 logs、saves、local、ftbteambases、options.txt。
5. 设计 connector/agent 的语言无关协议草案。
6. 设计 NeoForge runtime dump 的最小字段：registries、tags、recipes、advancements、FTB Quests、team/player stage。

## 当前实现进度

- 已建立 connector-agent 协议草案：`docs/protocol/CONNECTOR_AGENT_PROTOCOL.md`。
- 已建立 NeoForge connector 骨架：`connectors/neoforge`。
- NeoForge connector 的 Gradle 配置按 StoneBlock 4 对齐：Minecraft `1.21.1`、NeoForge `21.1.233`、Java toolchain `21`。
- 已实现无 Minecraft 依赖的 Java 协议层和 HTTP client，覆盖 `connector.hello`、`runtime_dump.manifest`、runtime dump section 上传，并用 `scripts/test-java-protocol.ps1` 验证。
- 已实现 Java `mods` section NDJSON 生成、`count` / `sha256` 计算、manifest + section 上传编排。
- 已实现弱依赖 NeoForge `ModList` 的反射适配层，输出 Packwise 自有 `ModSnapshot`。
- 已实现轻量 Python agent service/harness，支持 hello、runtime dump manifest、runtime dump section、`mods` section 解析索引、ask 和可选 DeepSeek/OpenAI-compatible 调用，并用 `scripts/test-agent.ps1` 验证。
- 已实现不启动游戏的静态 inspect harness：`python -m packwise_agent inspect <installed-instance>`。它只读 PCL2 已安装实例，输出 pack/loader 身份、mod jar 数、FTB Quests/KubeJS/datapack/defaultconfigs 计数、安全样本和默认忽略的 runtime/private 目录。
- 已实现不启动游戏的 FTB Quests SNBT 解析 harness：`python -m packwise_agent inspect-quests <installed-instance>`。当前抽取 chapter、quest、dependency、task、reward、item/stage 骨架；在 StoneBlock 4 上解析到 `22` 章、`939` 个 quest、`1603` 个 task、`1417` 个 reward、`855` 条依赖边、`116` 个 stage。
- Agent 接收 runtime dump section 时会校验 manifest 中声明的 `count` 与 `sha256`。
- 当前命令行 PATH 上的 `java/javac` 可能不是 JDK 21。完整 NeoForge 构建需要 JDK 21；可设置 `PACKWISE_JDK21_HOME`，构建脚本也会默认尝试 `%APPDATA%\.minecraft\runtime\java-runtime-delta`。
- 已接入 Gradle Wrapper `8.8` 和 `scripts/build-neoforge.ps1`，完整 NeoForge 构建通过，产物为 `connectors/neoforge/build/libs/packwise-neoforge-connector-0.1.0.jar`。
- 构建脚本中 `org.lwjgl` 依赖优先复用 PCL2 已下载的本地 Minecraft libraries，以规避本机 Gradle/JDK 到 `libraries.minecraft.net` 的 TLS 握手失败。
