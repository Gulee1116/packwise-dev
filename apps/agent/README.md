# Packwise Agent Harness

轻量级 agent service，用于先验证 Packwise 的协议、检索/规划 harness 和模型调用效果。

当前实现不依赖 FastAPI 等第三方库，方便早期跑通：

- `packwise_agent.protocol`：协议模型和校验。
- `packwise_agent.service`：内存态 agent service。
- `packwise_agent.runtime_index`：轻量 runtime section 索引，支持 `mods`、registries、tags、recipes、potions、mob effects、advancements、`ftb_quests`、player/team progress、stages NDJSON。
- `packwise_agent.runtime_dump_importer`：把本地 `packwise-dumps/<dump_id>/` 按 connector HTTP 上传相同的 service handler 导入内存态 agent。
- `recipes` section 保留 `ingredient_items`，并可包含 `ingredient_slots`、shape/raw metadata、NBT/display name 候选，用于特殊配方的槽位和数量事实；`potions` / `mob_effects` section 用于药水效果和属性 modifier 语义。
- Forge connector 会在加载 FTB Quests、FTB Teams、GameStages 时 soft-link optional runtime sections；agent 侧把这些 section 用于 progression/unlock/blocker readiness。
- 即使没有单独上传静态任务书，agent 也可以直接用 runtime `ftb_quests` + player/team progress 给出基础解锁/下一步回答和 source refs。
- `packwise_agent.static_inspector`：不启动游戏的本地实例只读摘要，支持 PCL2、CurseForge manifest、Modrinth index、Prism/MultiMC pack metadata，以及无 launcher metadata 的 Forge/NeoForge server layout。
- `packwise_agent.pack_profiles` / `packwise_agent.pack_index`：数据驱动 pack profile 选择，以及静态来源 + runtime dump 的规范化 Packwise index。
- `packwise_agent.phase1_acceptance`：ATM9Sky Phase 1 验收报告，汇总 Forge jar、runtime dump、pack index、本地回答和真实服务器日志证据。
- `packwise_agent.snbt` / `packwise_agent.ftbquests`：FTB Quests SNBT 子集解析和任务书骨架抽取。
- `packwise_agent.http_api`：标准库 HTTP API，支持 health、hello、static inspect、quest book、runtime dump、pack index、ask。
- `packwise_agent.llm`：OpenAI-compatible chat client，模型供应商配置来自 backend 环境变量。

运行测试：

```bash
cd ../..
./scripts/dev test-python
```

Windows PowerShell 脚本 `..\..\scripts\test-agent.ps1` 仍可用于 Windows 本地测试。

启动本地服务：

```bash
cd ../..
./scripts/dev serve --host 127.0.0.1 --port 8765
```

只读检查已安装整合包目录，不启动游戏：

```bash
cd ../..
./scripts/dev inspect "<installed-instance>" --pretty
```

只读解析 FTB Quests 任务书骨架，不启动游戏：

```bash
cd ../..
./scripts/dev inspect-quests "<installed-instance>" --output "artifacts/stoneblock4-quests-skeleton.json" --pretty
```

构建规范化 Packwise index，不启动游戏：

```bash
cd ../..
./scripts/dev validate-dump "runtime-dumps/dump_1" --require-phase1 --pretty
./scripts/dev import-dump "runtime-dumps/dump_1" --instance "<installed-instance>" --require-phase1 --pretty
./scripts/dev build-index "<installed-instance>" --runtime-dir "runtime-dumps/dump_1" --require-phase1 --pretty
./scripts/dev ask-local "<installed-instance>" --runtime-dir "runtime-dumps/dump_1" --item-id "minecraft:stone" --question "当前目标缺哪些前置机器/任务/材料？" --pretty
```

`validate-dump --require-phase1` 会校验 manifest、section count/hash、标准 runtime section 的 NDJSON content type、Phase 1 section 是否齐全，并要求 `mods`、`items`、`blocks`、`fluids`、`tags`、`recipes`、`advancements` 全部非空；当 registry section 存在时，还会校验 recipes/tags 和 FTB quest item refs 引用的 runtime item/block/fluid 是否存在；当 optional progression section 存在时，还会校验 typed quest dependencies、completed quest refs 和 player stage refs 的一致性。`build-index --require-phase1` 对索引构建执行同样的 Phase 1 runtime 门槛；不加该参数时仍可用于探索不完整 dump。`ask-local` 默认使用同样的 Phase 1 runtime 要求；仅探索不完整 dump 时可追加 `--allow-partial-runtime`。

ATM9Sky Phase 1 真实服务器验收报告：

```bash
cd ../..
./scripts/dev phase1-acceptance --instance "<installed-atm9sky-instance>" --runtime-dir "runtime-dumps/dump_1" --server-log "<server-log>" --item-id "<item-with-runtime-recipe-or-quest-ref>" --pretty
```

如果服务器 `/packwise dump` 已经通过 `PACKWISE_BACKEND_BASE_URL`、
`PACKWISE_AGENT_BASE_URL` 或 legacy `PACKWISE_AGENT_URL` 上传到正在运行的
backend，可追加 `--agent-url "<agent-url>"`。该选项会把在线 backend 的
`GET /v1/connectors/<connector_id>` 状态纳入验收，确认同一个
`connector.hello` 和 `dump_id` 已到达 agent、manifest 声明的 sections 已全部
上传，并继续检查 scoped `pack-index` 是否已经基于上传的 runtime sections 构建出
runtime-authoritative 索引，以及 `/v1/query/ask` 是否能基于同一个 dump 返回带
source refs 的回答。

启用 OpenAI-compatible 调用：

集中式部署时，Minecraft connector 和未来客户端只指向 Packwise backend
（`PACKWISE_BACKEND_BASE_URL` / `PACKWISE_AGENT_BASE_URL` 或 legacy
`PACKWISE_AGENT_URL`）。模型供应商 URL、
模型名和 API key 只在 backend 进程环境中配置。

```bash
cd ../..
PACKWISE_LLM_MODEL="deepseek-v4-pro" \
PACKWISE_LLM_BASE_URL="https://<model-provider-host>/v1" \
PACKWISE_LLM_API_KEY="<backend-side-secret>" \
./scripts/dev serve --host 127.0.0.1 --port 8765 --enable-llm
```

Windows PowerShell 中仍可使用 `$env:PACKWISE_LLM_* = "..."` 的变量写法。

从 backend 环境检查模型端点和最小 chat completion：

```bash
PACKWISE_LLM_MODEL="deepseek-v4-pro" \
PACKWISE_LLM_BASE_URL="https://<model-provider-host>/v1" \
PACKWISE_LLM_API_KEY="<backend-side-secret>" \
./scripts/dev model-check --pretty
```

默认检查 OpenAI-compatible `/v1/models` 可达并列出 `PACKWISE_LLM_MODEL`，
同时发送一次 `max_tokens=1` 的最小 chat completion 来确认模型可实际调用。
仅诊断模型列表端点时才使用 `--skip-chat-smoke`。

后续可以替换为 FastAPI/Uvicorn，但协议对象和测试应保持稳定。

环境变量建议：

- `PACKWISE_LLM_MODEL=deepseek-v4-pro`
- `PACKWISE_LLM_BASE_URL=https://<model-provider-host>/v1`
- `PACKWISE_LLM_API_KEY=<backend-side-secret>`
