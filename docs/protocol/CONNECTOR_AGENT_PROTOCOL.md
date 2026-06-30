# Packwise Connector-Agent Protocol v1

状态：draft

目标：让 Minecraft JVM mod 和 Packwise agent service 通过语言无关的结构化协议通信。协议是产品边界，不绑定 Java、Kotlin、Python 或具体模型供应商。

## 原则

- Connector 负责 Minecraft runtime 事实：registries、recipes、tags、quests、advancements、player/team progress、stage state。
- Agent service 负责索引、检索、路线规划、模型调用、记忆和自然语言回答。
- Connector 和用户客户端只调用 Packwise agent/backend；只有 backend 调用 OpenAI-compatible 模型供应商。
- 模型供应商 API key 只存在于 backend 环境，不属于 connector/client 配置或协议字段。
- 双方只交换 JSON 数据，不共享语言运行时。
- 所有消息都带 `protocol`、`message_type`、`message_id`、`sent_at`。
- 第一版优先 HTTP JSON；后续可以用 WebSocket/NDJSON 复用同一消息体。

## 版本

当前协议版本：

```text
packwise.connector.v1
```

不兼容变更必须升版本。兼容新增字段时，接收方必须忽略未知字段。

## 运行形态

`side` 表示 connector 当前提供的能力边界：

- `client`：用户端 only。
- `server`：服务端 only。
- `client_server`：双端协同。

`capabilities` 是字符串数组。第一批能力：

- `runtime_dump`
- `commands`
- `server_progress`
- `client_context`
- `inventory_snapshot`
- `quest_progress`
- `stage_state`

## Connector Hello

方向：connector -> agent

用途：注册 connector、声明 loader/pack/runtime 能力。

HTTP：

```text
POST /v1/connectors/hello
```

请求：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "connector.hello",
  "message_id": "msg_0001",
  "sent_at": "2026-06-14T08:00:00Z",
  "connector": {
    "id": "stoneblock4-dev-server",
    "side": "server",
    "loader": "neoforge",
    "loader_version": "21.1.233",
    "minecraft_version": "1.21.1",
    "pack_id": "ftb-stoneblock-4",
    "pack_name": "FTB StoneBlock 4",
    "pack_version": "1.14.2",
    "connector_mod_id": "packwise_connector",
    "connector_version": "0.1.0",
    "capabilities": [
      "runtime_dump",
      "commands",
      "server_progress",
      "quest_progress",
      "stage_state"
    ]
  }
}
```

响应：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "connector.ack",
  "message_id": "msg_0002",
  "in_reply_to": "msg_0001",
  "sent_at": "2026-06-14T08:00:01Z",
  "accepted": true,
  "agent": {
    "name": "packwise-agent",
    "capabilities": [
      "ask",
      "next_steps",
      "goal_planning"
    ]
  }
}
```

## Connector Status

方向：client/web/dev -> agent

用途：查询 agent 当前记住的 connector hello、静态上下文状态和该 connector
已上传的 runtime dump 摘要。第一版用于在线 `/packwise dump` 后确认
`connector.hello` 已被 agent 接收，并确认 dump 被归到正确 connector。

HTTP：

```text
GET /v1/connectors/{connector_id}
```

如果 agent 没有该 connector 的 hello、static inspect、quest book 或 runtime
dump 状态，返回 404 `not_found`。

响应：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "connector.status",
  "connector_id": "atm9sky-dev-server",
  "hello_present": true,
  "hello": {
    "message_id": "msg_0001",
    "sent_at": "2026-06-14T08:00:00Z"
  },
  "connector": {
    "id": "atm9sky-dev-server",
    "side": "server",
    "loader": "forge",
    "loader_version": "47.4.20",
    "minecraft_version": "1.20.1",
    "pack_id": "atm9sky",
    "pack_name": "All the Mods 9 - To the Sky",
    "pack_version": "1.1.0",
    "connector_mod_id": "packwise_connector",
    "connector_version": "0.1.0",
    "capabilities": [
      "runtime_dump",
      "commands"
    ]
  },
  "static_inspect_present": false,
  "quest_book_present": false,
  "runtime_dumps": [
    {
      "dump_id": "dump_20260614_081000",
      "minecraft_version": "1.20.1",
      "loader": "forge",
      "loader_version": "47.4.20",
      "connector_mod_id": "packwise_connector",
      "connector_version": "0.1.0",
      "section_count": 7,
      "declared_sections": [
        "mods",
        "items",
        "blocks",
        "fluids",
        "tags",
        "recipes",
        "advancements"
      ],
      "uploaded_sections": [
        "mods",
        "items",
        "blocks",
        "fluids",
        "tags",
        "recipes",
        "advancements"
      ],
      "uploaded_section_count": 7,
      "missing_sections": [],
      "extra_sections": [],
      "upload_complete": true,
      "indexed_summary": {
        "recipes": 12000,
        "tags": 3000
      },
      "runtime_consistency_errors": []
    }
  ]
}
```

`runtime_dumps[*].upload_complete` 只有在 manifest 中声明的每个 section 都已
成功上传并通过 count/hash 校验后才为 `true`；`missing_sections` 用于定位
manifest 已到达但 section upload 中断的在线 dump。

## Ask Request

方向：connector/client/web -> agent

用途：自然语言问题。第一版不要求 agent 已有完整 KG；可以先基于 source inventory、runtime dump 摘要和模型回答。

HTTP：

```text
POST /v1/query/ask
```

请求：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "query.ask",
  "message_id": "msg_0100",
  "sent_at": "2026-06-14T08:05:00Z",
  "question": "我下一步该干什么？",
  "locale": "zh_cn",
  "context": {
    "connector_id": "stoneblock4-dev-server",
    "server_id": "local-dev",
    "team_id": "team-main",
    "player_id": "00000000-0000-0000-0000-000000000000",
    "player_name": "DevPlayer",
    "known_progress": {
      "completed_quests": [],
      "stages": []
    }
  }
}
```

When `player_id`, `player_name`, or `team_id` is present, the agent scopes
runtime `player_progress`, `team_progress`, and `stages` to that player/team
before marking quests complete or selecting next steps. Without these fields,
answers may only safely describe aggregate runtime context.

响应：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "answer.packet",
  "message_id": "msg_0101",
  "in_reply_to": "msg_0100",
  "sent_at": "2026-06-14T08:05:01Z",
  "answer": {
    "summary": "先完成 Getting Started 里的基础资源生成链，再推进自动筛矿。",
    "next_steps": [
      "确认当前队伍是否已完成 pebble/cobblegen 相关任务。",
      "优先补齐资源生成章节的第一批机器。"
    ],
    "source_refs": [
      {
        "kind": "quest",
        "path": "config/ftbquests/quests/chapters/getting_started.snbt",
        "label": "Getting Started"
      }
    ],
    "confidence": "low",
    "model": "deepseek-v4-pro"
  }
}
```

## Runtime Dump Manifest

方向：connector -> agent

用途：runtime dump 的目录和摘要。大对象可以分块上传或写文件后由 agent 拉取。
在线上传时，connector 应先发送 `connector.hello`，再发送 runtime dump
manifest 和 section 内容。这样即使没有离线 `static-inspect`，agent 也有最小
loader、pack、capability context 可以关联 dump。

HTTP：

```text
POST /v1/connectors/{connector_id}/runtime-dumps
```

URL 中的 `{connector_id}`、`{dump_id}`、`{section_name}` 都是单个 path
segment；connector 必须对这些 segment 做 percent-encoding，agent 在路由后
按 UTF-8 解码。这样 connector ID 或 dump ID 中出现空格、冒号或斜杠时仍然
不会改变 URL 层级。

最小字段：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "runtime_dump.manifest",
  "message_id": "msg_0200",
  "sent_at": "2026-06-14T08:10:00Z",
  "connector_id": "stoneblock4-dev-server",
  "dump_id": "dump_20260614_081000",
  "minecraft_version": "1.21.1",
  "loader": "neoforge",
  "loader_version": "21.1.233",
  "connector_mod_id": "packwise_connector",
  "connector_version": "0.1.0",
  "sections": [
    {
      "name": "items",
      "content_type": "application/x-ndjson",
      "count": 12000,
      "sha256": "..."
    },
    {
      "name": "recipes",
      "content_type": "application/x-ndjson",
      "count": 8000,
      "sha256": "..."
    }
  ]
}
```

响应：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "runtime_dump.ack",
  "message_id": "msg_0201",
  "in_reply_to": "msg_0200",
  "sent_at": "2026-06-14T08:10:01Z",
  "accepted": true,
  "dump_id": "dump_20260614_081000",
  "section_count": 2
}
```

第一版 runtime dump 目标 section：

- `mods`
- `items`
- `blocks`
- `fluids`
- `tags`
- `recipes`
- `potions`
- `mob_effects`
- `advancements`
- `ftb_quests`
- `player_progress`
- `team_progress`
- `stages`

其中 `mods`、`items`、`blocks`、`fluids`、`tags`、`recipes`、`advancements` 是 Phase 1 connector 的核心 section；`potions`、`mob_effects` 提供药水/效果语义；`ftb_quests`、`player_progress`、`team_progress`、`stages` 是可选 runtime truth section，存在时优先于静态任务书 preload。

## Runtime Dump Section Upload

方向：connector -> agent

用途：上传 runtime dump manifest 中声明的具体 section 内容。第一版使用 NDJSON，便于逐行流式处理和后续拆分大文件。
标准 runtime section（`mods`、`items`、`blocks`、`fluids`、`tags`、`recipes`、`potions`、`mob_effects`、`advancements`、`ftb_quests`、`player_progress`、`team_progress`、`stages`）必须声明 `content_type: application/x-ndjson`。
Connector 也可以把同一份 manifest 和 section 内容写成本地文件，供离线校验、手工导入或 agent CLI `validate-dump` / `build-index` / `ask-local` 使用；本地文件布局不是独立协议，仍以 manifest 和 section 内容为准。

HTTP：

```text
POST /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/sections/{section_name}
Content-Type: application/x-ndjson
```

示例：`mods` section

```ndjson
{"mod_id":"minecraft","display_name":"Minecraft","version":"1.21.1","source":"builtin"}
{"mod_id":"neoforge","display_name":"NeoForge","version":"21.1.233","source":"neoforge:ModList"}
```

示例：`recipes` section

```ndjson
{"id":"minecraft:stonecutting/stone","type":"minecraft:stonecutting","serializer":"minecraft:stonecutting","result_item":"minecraft:stone","result_count":1,"ingredient_items":["minecraft:cobblestone"],"ingredient_slots":[{"slot":0,"empty":false,"item_ids":["minecraft:cobblestone"],"candidates":[{"item_id":"minecraft:cobblestone","count":1}]}],"source":"runtime:recipe_manager"}
```

`ingredient_items` 保留为向后兼容的去重候选物品 ID 集合。`ingredient_slots` 保留每个 recipe ingredient slot 的候选物品、计数、NBT/display name（存在时），用于恢复特殊配方的数量和槽位事实；shaped recipe 还可以带 `width`、`height`、`pattern` 或可用的 `raw_recipe`。

示例：`potions` / `mob_effects` section

```ndjson
{"id":"apotheosis:flying","translation_key":"item.minecraft.potion.effect.flying","display_name":"Potion of Flying","effects":[{"effect_id":"attributeslib:flying","duration":3600,"amplifier":0}],"source":"runtime:potion_registry"}
{"id":"attributeslib:flying","translation_key":"effect.attributeslib.flying","display_name":"Flying","description":"effect.attributeslib.flying","attribute_modifiers":[{"attribute_id":"attributeslib:creative_flight","name":"Creative flight","uuid":"00000000-0000-0000-0000-000000000001","operation":"ADDITION","amount":1.0}],"source":"runtime:mob_effect_registry"}
```

示例：可选 `ftb_quests` section

```ndjson
{"quest_id":"0000000000000002","chapter_id":"0000000000000001","title":"Getting Started","dependencies":[],"dependency_types":{},"task_item_ids":["minecraft:stone"],"reward_item_ids":["minecraft:apple"],"source":"runtime:ftb_quests"}
```

示例：可选 `team_progress` / `player_progress` / `stages` section

```ndjson
{"subject_type":"team","subject_id":"00000000-0000-0000-0000-000000000001","completed_quests":["0000000000000002"],"completed_advancements":[],"stages":[],"source":"runtime:ftb_quests","team_name":"DevTeam#00000000","members":["00000000-0000-0000-0000-000000000002"]}
{"subject_type":"player","subject_id":"00000000-0000-0000-0000-000000000002","completed_quests":["0000000000000002"],"completed_advancements":[],"stages":["stone_age"],"source":"runtime:ftb_quests","player_name":"DevPlayer","team_id":"00000000-0000-0000-0000-000000000001"}
{"subject_type":"player","subject_id":"00000000-0000-0000-0000-000000000002","stage":"stone_age","active":true,"source":"runtime:gamestages","player_name":"DevPlayer"}
```

Forge connector 对 `ftb_quests`、`player_progress`、`team_progress` 和 `stages` 使用 guarded reflection：只有对应 mod/API 存在时才写入这些 optional section；API 不存在或变更时跳过 optional section，不应影响 Phase 1 核心 dump。

## Static Inspect And Quest Book Context

方向：agent harness/tooling -> agent

用途：把离线静态检查和 FTB Quests 任务书骨架提供给 agent，作为 preload/context。runtime dump 仍是配方、标签、注册表、进度和 stage 的权威来源。

HTTP：

```text
POST /v1/connectors/{connector_id}/static-inspect
POST /v1/connectors/{connector_id}/quest-book
GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/pack-index
```

`pack-index` 响应使用 `packwise.index.v1`，记录选中的 pack profile、静态来源清单、runtime section counts、以及每类事实的 reconciliation 状态。新 Forge 1.20.1 整合包应主要通过新增/选择 profile、运行 `inspect` 和上传 runtime dump 来接入。
如果该 connector/dump 已存在但尚未上传 `static-inspect` 且 agent 也没有
`connector.hello` 可作为最小 pack context，`pack-index` 必须返回 400
`missing_instance_context`，而不是返回不完整索引或断开连接。

响应：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "runtime_dump.section_ack",
  "message_id": "msg_0202",
  "sent_at": "2026-06-14T08:10:02Z",
  "accepted": true,
  "dump_id": "dump_20260614_081000",
  "section_name": "mods",
  "line_count": 2
}
```

校验规则：

- `{connector_id}` 必须与 manifest 中的 `connector_id` 一致。
- `{dump_id}` 必须已经通过 `runtime_dump.manifest` 注册。
- `{section_name}` 必须在 manifest 的 `sections` 中声明。
- `Content-Type` 必须与 manifest 中对应 section 的 `content_type` 一致。
- section 非空行数必须与 manifest 中对应 section 的 `count` 一致。
- section UTF-8 正文的 SHA-256 必须与 manifest 中对应 section 的 `sha256` 一致。
- agent runtime consistency validation 会校验 duplicate IDs、recipe/tag/quest item registry refs、typed FTB quest dependencies、player/team completed quest refs，以及 player progress stage refs 和 `stages` section 的一致性；不完整 optional section 应暴露为 `runtime_consistency_errors`，不能静默参与高置信回答。

## Runtime Dump Queries

方向：client/web/dev -> agent

用途：查询 agent 已索引的 runtime dump section 摘要。第一版用于验证 connector 是否真的把服务端 mod 列表、recipes 和 runtime index 同步到了 agent。

HTTP：

```text
GET /v1/connectors/{connector_id}
GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/mods
GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/recipes
GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/index-summary
GET /v1/runtime-dumps/{dump_id}/mods
GET /v1/runtime-dumps/{dump_id}/recipes
GET /v1/runtime-dumps/{dump_id}/index-summary
```

优先使用带 `{connector_id}` 的 scoped URL；不带 connector 的 URL 只适合单 dump
调试或 dump id 全局唯一的场景。
Scoped URL 如果找不到对应的 `{connector_id}` + `{dump_id}` runtime dump，
必须返回 404 `not_found`，避免把错误 connector 或重复 dump id 误报为空结果。

响应：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "runtime_dump.mods",
  "connector_id": "stoneblock4-dev-server",
  "dump_id": "dump_20260614_081000",
  "mods": [
    {
      "mod_id": "minecraft",
      "display_name": "Minecraft",
      "version": "1.21.1",
      "source": "builtin"
    },
    {
      "mod_id": "neoforge",
      "display_name": "NeoForge",
      "version": "21.1.233",
      "source": "neoforge:ModList"
    }
  ]
}
```

## 错误响应

错误也保持协议 envelope：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "error",
  "message_id": "msg_err_0001",
  "in_reply_to": "msg_0100",
  "sent_at": "2026-06-14T08:05:01Z",
  "error": {
    "code": "unsupported_protocol",
    "message": "Expected packwise.connector.v1."
  }
}
```

## TDD 契约

两端必须至少通过这些契约测试：

- `connector.hello` 可以序列化为 JSON。
- `connector.hello` 可以从 JSON 解析回同等字段。
- 错误协议版本会被拒绝。
- agent 收到 hello 后返回 `connector.ack`。
- agent 收到 ask 后返回 `answer.packet`，且必须包含 `summary`、`next_steps`、`source_refs`、`confidence`、`model`。
- `runtime_dump.manifest` 可以序列化为 JSON。
- `runtime_dump.manifest` 可以从 JSON 解析回同等字段。
- connector_id 与 URL 路径不一致时必须拒绝。
- agent 收到 runtime dump manifest 后返回 `runtime_dump.ack` 并保存 manifest。
- `mods` section 可以由 Java connector 生成 NDJSON，并计算 `count` 与 `sha256`。
- connector 可以按 hello -> manifest -> section 顺序上传 runtime dump；没有
  connector metadata 的旧客户端仍可按 manifest -> section 上传。
- agent 收到 runtime dump section 后返回 `runtime_dump.section_ack` 并保存 section 内容。
- agent 必须校验 runtime dump section 的 `count` 和 `sha256`。
- agent 必须按 connector id + dump id 隔离 runtime dump 状态，避免多个服务器或整合包使用相同本地 dump id 时互相污染。
- agent 必须能解析 `mods` section，并通过 connector-scoped `GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/mods` 返回已索引 mod 列表。
