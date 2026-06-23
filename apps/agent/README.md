# Packwise Agent Harness

轻量级 agent service，用于先验证 Packwise 的协议、检索/规划 harness 和模型调用效果。

当前实现不依赖 FastAPI 等第三方库，方便早期跑通：

- `packwise_agent.protocol`：协议模型和校验。
- `packwise_agent.service`：内存态 agent service。
- `packwise_agent.runtime_index`：轻量 runtime section 索引，当前支持 `mods` NDJSON。
- `packwise_agent.static_inspector`：不启动游戏的本地实例只读摘要，当前支持 PCL2 已安装实例。
- `packwise_agent.snbt` / `packwise_agent.ftbquests`：FTB Quests SNBT 子集解析和任务书骨架抽取。
- `packwise_agent.http_api`：标准库 HTTP API，支持 health、hello、runtime dump manifest、runtime dump section、mods query、ask。
- `packwise_agent.llm`：OpenAI-compatible chat client，默认模型名可设为 `deepseek-v4-pro`。

运行测试：

```powershell
..\..\scripts\test-agent.ps1
```

启动本地服务：

```powershell
python -m packwise_agent --host 127.0.0.1 --port 8765
```

只读检查已安装整合包目录，不启动游戏：

```powershell
$env:PYTHONPATH = "$PWD"
python -m packwise_agent inspect "<installed-instance>" --pretty
```

只读解析 FTB Quests 任务书骨架，不启动游戏：

```powershell
$env:PYTHONPATH = "$PWD"
python -m packwise_agent inspect-quests "<installed-instance>" --output "..\..\artifacts\stoneblock4-quests-skeleton.json" --pretty
```

启用 DeepSeek/OpenAI-compatible 调用：

```powershell
$env:PACKWISE_LLM_MODEL = "deepseek-v4-pro"
$env:PACKWISE_LLM_BASE_URL = "https://api.deepseek.com"
$env:DEEPSEEK_API_KEY = "<your-api-key>"
python -m packwise_agent --host 127.0.0.1 --port 8765 --enable-llm
```

后续可以替换为 FastAPI/Uvicorn，但协议对象和测试应保持稳定。

环境变量建议：

- `PACKWISE_LLM_MODEL=deepseek-v4-pro`
- `PACKWISE_LLM_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_API_KEY=...`
