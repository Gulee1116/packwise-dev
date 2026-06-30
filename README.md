# Packwise

Packwise 是面向 Minecraft 整合包服务器的进度指导 agent。当前仓库处在协议和 harness 起步阶段。

## 当前模块

- `AGENTS.md`：后续 agent 的本地环境和启动约定。
- `docs/HANDOFF.md`：当前交接状态、公开仓库安全边界和下一步建议。
- `docs/DEVELOPMENT_ENV.md`：项目专属 Python/Java 环境说明。
- `docs/ATM9SKY_PHASE1_ACCEPTANCE.md`：ATM9Sky Phase 1 真实服务器验收步骤和证据报告命令。
- `docs/protocol/CONNECTOR_AGENT_PROTOCOL.md`：connector-agent JSON 协议草案。
- `connectors/common`：无 Minecraft/loader 依赖的 Java connector-common 协议、NDJSON dump helper 和命令响应模型。
- `connectors/forge`：Java/Forge connector，按 ATM9 To The Sky 的 Minecraft `1.20.1` + Forge `47.4.20` 对齐。
- `connectors/neoforge`：Java/NeoForge connector 骨架，按 StoneBlock 4 的 Minecraft `1.21.1` + NeoForge `21.1.233` 对齐。
- `apps/agent`：轻量 Python agent service/harness。

## 本地环境

本项目约定所有 Python、Java、Gradle 和缓存状态都局限在仓库内的 `.packwise-env/`。不要使用全局 pip、用户级 pip、系统 Java 或默认 `~/.gradle` 缓存来运行本项目。

首次准备环境：

```bash
./scripts/dev setup
```

日常检查和进入环境：

```bash
./scripts/dev doctor
./scripts/dev shell
```

如果需要执行原生命令，先从仓库根目录激活：

```bash
source scripts/env.sh
```

详细约定见 `docs/DEVELOPMENT_ENV.md`。

## 本地测试

Linux/macOS 推荐使用统一入口：

```bash
./scripts/dev test-python
./scripts/dev test-java-protocol
./scripts/dev build-forge
./scripts/dev build-neoforge
```

Windows PowerShell 脚本仍可直接运行。Java 协议层测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-java-protocol.ps1
```

Python agent 测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-agent.ps1
```

无 Minecraft 依赖的协议层测试只需要普通 JDK。NeoForge connector 完整构建需要 JDK 21；可以设置 `PACKWISE_JDK21_HOME`，构建脚本也会默认尝试 `%APPDATA%\.minecraft\runtime\java-runtime-delta`。NeoForge connector 已接入 Gradle Wrapper `8.8`，完整构建通过。

不启动游戏的已安装实例只读检查：

```bash
./scripts/dev inspect "<installed-instance>" --pretty
```

不启动游戏的 FTB Quests 任务书骨架抽取：

```bash
./scripts/dev inspect-quests "<installed-instance>" --output "artifacts/stoneblock4-quests-skeleton.json" --pretty
```

从静态检查和 runtime dump section 文件构建规范化 Packwise index：

```bash
./scripts/dev validate-dump "runtime-dumps/dump_1" --require-phase1 --pretty
./scripts/dev import-dump "runtime-dumps/dump_1" --instance "<installed-instance>" --require-phase1 --pretty
./scripts/dev build-index "<installed-instance>" --runtime-dir "runtime-dumps/dump_1" --pretty
./scripts/dev ask-local "<installed-instance>" --runtime-dir "runtime-dumps/dump_1" --item-id "minecraft:stone" --question "当前目标缺哪些前置机器/任务/材料？" --pretty
```

`validate-dump --require-phase1` 会校验 manifest、section count/hash、Phase 1 section 是否齐全，并要求 `mods`、`items`、`blocks`、`fluids`、`tags`、`recipes`、`advancements` 全部非空；当 registry section 存在时，还会校验 recipes/tags 和 FTB quest item refs 引用的 runtime item/block/fluid 是否存在；当 optional progression section 存在时，还会校验 typed quest dependencies、completed quest refs 和 player stage refs 的一致性。`ask-local` 默认使用同样的 Phase 1 runtime 要求；仅探索不完整 dump 时可追加 `--allow-partial-runtime`。

Forge connector 的 `/packwise dump` 会在服务器工作目录下写出 `packwise-dumps/<dump_id>/manifest.json` 和各 section 的 `*.ndjson` 文件；配置 `PACKWISE_BACKEND_BASE_URL` 或 `PACKWISE_AGENT_BASE_URL` 时会同时上传给 backend；`PACKWISE_AGENT_URL` 仍作为兼容旧脚本的 backend 地址别名。
`import-dump` 会使用和 HTTP 上传一致的 AgentService manifest/section handler 导入本地 dump；带 `--instance` 时还会导入静态检查和任务书上下文，并返回同一内存态 service 构建出的 Packwise index 摘要。
Agent 侧 runtime index 支持 Phase 1 核心 section，也支持 `potions`、`mob_effects` 语义 section，以及可选的 `ftb_quests`、`player_progress`、`team_progress`、`stages`；这些 section 会提升药水/效果路线、进度/解锁/阻塞问题的 readiness。
Forge 侧 recipe dump 会尽量写出 `ingredient_items`，agent 可据此回答基础“缺哪些材料”问题；如果服务器加载了 FTB Quests、FTB Teams 或 GameStages，Forge connector 会通过 soft-linked reflection 尝试写出 quest/progress/stage optional sections。复杂机器链仍需要任务和进度 section 补充。
ATM9Sky Phase 1 真实服务器验收必须在运行过 `/packwise status` 和 `/packwise dump` 后执行 `phase1-acceptance`，详见 `docs/ATM9SKY_PHASE1_ACCEPTANCE.md`。

```bash
./scripts/dev phase1-acceptance --instance "<installed-atm9sky-instance>" --runtime-dir "<dump-dir>" --server-log "<server-log>" --item-id "<item-with-runtime-recipe-or-quest-ref>" --pretty
```

NeoForge connector 完整构建：

```bash
./scripts/dev build-neoforge
```

产物位于 `connectors/neoforge/build/libs/`。

## 启动轻量 Agent Service

Packwise 采用集中式后端推理拓扑：

- Minecraft server connector 只配置 Packwise backend 地址，例如 `PACKWISE_BACKEND_BASE_URL="http://<packwise-backend-host>:8765"`；Forge connector 也接受 `PACKWISE_AGENT_BASE_URL` 和 legacy `PACKWISE_AGENT_URL` 作为别名。
- 未来用户客户端只配置 Packwise backend 地址，例如 `PACKWISE_BACKEND_BASE_URL="http://<packwise-backend-host>:8765"`。
- 只有 Packwise backend 配置并调用 OpenAI-compatible 模型服务。
- 模型 API key 只放在 backend 环境里，不放在 Minecraft server、connector、客户端或示例配置里。

Backend 启动示例：

```bash
PACKWISE_LLM_MODEL="deepseek-v4-pro" \
PACKWISE_LLM_BASE_URL="https://<model-provider-host>/v1" \
PACKWISE_LLM_API_KEY="<backend-side-secret>" \
./scripts/dev serve --host 127.0.0.1 --port 8765
```

需要实际调用 OpenAI-compatible API 时加：

```bash
PACKWISE_LLM_MODEL="deepseek-v4-pro" \
PACKWISE_LLM_BASE_URL="https://<model-provider-host>/v1" \
PACKWISE_LLM_API_KEY="<backend-side-secret>" \
./scripts/dev serve --host 127.0.0.1 --port 8765 --enable-llm
```

Windows PowerShell 中仍可使用 `$env:PACKWISE_LLM_* = "..."` 的变量写法。

Backend 模型连通性检查：

```bash
PACKWISE_LLM_MODEL="deepseek-v4-pro" \
PACKWISE_LLM_BASE_URL="https://<model-provider-host>/v1" \
PACKWISE_LLM_API_KEY="<backend-side-secret>" \
./scripts/dev model-check --pretty
```

该命令只在 backend 侧执行，默认同时检查 OpenAI-compatible `/v1/models`
可达、包含 `PACKWISE_LLM_MODEL`，并发送一次 `max_tokens=1` 的最小 chat
completion 以确认模型可实际调用。仅诊断模型列表端点时才使用
`--skip-chat-smoke`。

当前 HTTP endpoints：

路径中的 `{connector_id}`、`{dump_id}`、`{section_name}` 按单个 URL path
segment percent-encoding。

- `GET /v1/health`
- `POST /v1/connectors/hello`
- `GET /v1/connectors/{connector_id}`
- `POST /v1/connectors/{connector_id}/static-inspect`
- `POST /v1/connectors/{connector_id}/quest-book`
- `POST /v1/connectors/{connector_id}/runtime-dumps`
- `POST /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/sections/{section_name}`
- `GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/mods`
- `GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/recipes`
- `GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/index-summary`
- `GET /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/pack-index`
- `GET /v1/runtime-dumps/{dump_id}/mods`
- `GET /v1/runtime-dumps/{dump_id}/recipes`
- `GET /v1/runtime-dumps/{dump_id}/index-summary`
- `POST /v1/query/ask`

OpenAI-compatible client 已接入为可选 answer pipeline；默认不调用外部 API，避免测试时误触发付费请求。
