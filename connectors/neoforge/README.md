# Packwise NeoForge Connector

目标：作为 Minecraft/NeoForge 侧 runtime connector 和 dumper，负责采集游戏内真值并通过 Packwise Connector-Agent Protocol 发给 agent service。

当前状态：

- 协议层 Java 代码已迁到 `connectors/common`，无 Minecraft/NeoForge 依赖，可用本机 `javac` 单测。
- 已实现 `connector.hello` 和 `runtime_dump.manifest` 的 JSON 模型与 HTTP 发送。
- 已实现 `mods` section 的 NDJSON 生成、`count` / `sha256` 计算和上传编排。
- 已实现弱依赖 NeoForge `ModList` 的反射适配层，输出 `ModSnapshot`。
- NeoForge mod 骨架按 StoneBlock 4 对齐：Minecraft `1.21.1`、NeoForge `21.1.233`。
- 完整 NeoForge 构建需要项目本地 JDK 21；优先通过仓库根目录的 `./scripts/dev build-neoforge` 运行。
- 已接入 Gradle Wrapper `8.8`，并通过 `./scripts/dev build-neoforge` 验证完整 NeoForge 构建。构建中 `org.lwjgl` 依赖可优先复用 `PACKWISE_MINECRAFT_LIBRARIES` 或 `%APPDATA%\.minecraft\libraries` 下的本地 Minecraft libraries，以绕开部分机器到 `libraries.minecraft.net` 的 TLS 握手问题。

设计边界：

- mod 不依赖系统 Python。
- mod 只负责 runtime 事实、命令、同步、dump。
- agent service 负责索引、RAG/KG、模型调用、路线规划和记忆。
- connector 只配置 Packwise backend 地址；不要在 Minecraft server 或
  connector 配置 `PACKWISE_LLM_*` 或模型供应商 API key。集中式部署中只有
  backend 调用 OpenAI-compatible 模型服务，backend 模型名使用
  `PACKWISE_LLM_MODEL=deepseek-v4-pro`。

本地协议测试：

```bash
./scripts/dev test-java-protocol
```

完整 NeoForge 构建：

```bash
./scripts/dev build-neoforge
```

后续 NeoForge 目标：

- 注册 `/packwise status`、`/packwise ask`、`/packwise next`。
- 将 `NeoForgeModSnapshots.collectLoadedMods()` 接入服务端启动/命令流程，实际上传 `mods` runtime dump。
- dump registries、tags、recipes、advancements。
- 接入 FTB Quests / FTB Teams 进度。
- HTTP/WebSocket 同步到 agent service。
