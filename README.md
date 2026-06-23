# Packwise

Packwise 是面向 Minecraft 整合包服务器的进度指导 agent。当前仓库处在协议和 harness 起步阶段。

## 当前模块

- `docs/HANDOFF.md`：当前交接状态、公开仓库安全边界和下一步建议。
- `docs/protocol/CONNECTOR_AGENT_PROTOCOL.md`：connector-agent JSON 协议草案。
- `connectors/neoforge`：Java/NeoForge connector 骨架，按 StoneBlock 4 的 Minecraft `1.21.1` + NeoForge `21.1.233` 对齐。
- `apps/agent`：轻量 Python agent service/harness。

## 本地测试

Java 协议层测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-java-protocol.ps1
```

Python agent 测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-agent.ps1
```

无 Minecraft 依赖的协议层测试只需要普通 JDK。NeoForge connector 完整构建需要 JDK 21；可以设置 `PACKWISE_JDK21_HOME`，构建脚本也会默认尝试 `%APPDATA%\.minecraft\runtime\java-runtime-delta`。NeoForge connector 已接入 Gradle Wrapper `8.8`，完整构建通过。

不启动游戏的已安装实例只读检查：

```powershell
$env:PYTHONPATH = "$PWD\apps\agent"
python -m packwise_agent inspect "<installed-instance>" --pretty
```

不启动游戏的 FTB Quests 任务书骨架抽取：

```powershell
$env:PYTHONPATH = "$PWD\apps\agent"
python -m packwise_agent inspect-quests "<installed-instance>" --output ".\artifacts\stoneblock4-quests-skeleton.json" --pretty
```

NeoForge connector 完整构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-neoforge.ps1
```

产物位于 `connectors/neoforge/build/libs/`。

## 启动轻量 Agent Service

```powershell
cd .\apps\agent
$env:PACKWISE_LLM_MODEL = "deepseek-v4-pro"
$env:PACKWISE_LLM_BASE_URL = "https://api.deepseek.com"
$env:DEEPSEEK_API_KEY = "<your-api-key>"
python -m packwise_agent --host 127.0.0.1 --port 8765
```

需要实际调用 DeepSeek/OpenAI-compatible API 时加：

```powershell
python -m packwise_agent --host 127.0.0.1 --port 8765 --enable-llm
```

当前 HTTP endpoints：

- `GET /v1/health`
- `POST /v1/connectors/hello`
- `POST /v1/connectors/{connector_id}/runtime-dumps`
- `POST /v1/connectors/{connector_id}/runtime-dumps/{dump_id}/sections/{section_name}`
- `GET /v1/runtime-dumps/{dump_id}/mods`
- `POST /v1/query/ask`

DeepSeek/OpenAI-compatible client 已接入为可选 answer pipeline；默认不调用外部 API，避免测试时误触发付费请求。
