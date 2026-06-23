# Packwise Connector-Agent Protocol v1

状态：draft

目标：让 Minecraft JVM mod 和 Packwise agent service 通过语言无关的结构化协议通信。协议是产品边界，不绑定 Java、Kotlin、Python 或具体模型供应商。

## 原则

- Connector 负责 Minecraft runtime 事实：registries、recipes、tags、quests、advancements、player/team progress、stage state。
- Agent service 负责索引、检索、路线规划、模型调用、记忆和自然语言回答。
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
    "player": {
      "uuid": "00000000-0000-0000-0000-000000000000",
      "name": "DevPlayer"
    },
    "known_progress": {
      "completed_quests": [],
      "stages": []
    }
  }
}
```

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

HTTP：

```text
POST /v1/connectors/{connector_id}/runtime-dumps
```

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
- `advancements`
- `ftb_quests`
- `player_progress`
- `team_progress`
- `stages`

## Runtime Dump Section Upload

方向：connector -> agent

用途：上传 runtime dump manifest 中声明的具体 section 内容。第一版使用 NDJSON，便于逐行流式处理和后续拆分大文件。

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

## Runtime Mods Query

方向：client/web/dev -> agent

用途：查询 agent 已索引的 `mods` section。第一版用于验证 connector 是否真的把服务端 mod 列表同步到了 agent。

HTTP：

```text
GET /v1/runtime-dumps/{dump_id}/mods
```

响应：

```json
{
  "protocol": "packwise.connector.v1",
  "message_type": "runtime_dump.mods",
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
- connector 可以按 manifest -> section 顺序上传 runtime dump。
- agent 收到 runtime dump section 后返回 `runtime_dump.section_ack` 并保存 section 内容。
- agent 必须校验 runtime dump section 的 `count` 和 `sha256`。
- agent 必须能解析 `mods` section 并通过 `GET /v1/runtime-dumps/{dump_id}/mods` 返回已索引 mod 列表。
