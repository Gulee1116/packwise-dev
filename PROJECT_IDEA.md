# Packwise Project Idea

## 一句话定位

Packwise 是一个面向 Minecraft 整合包服务器的进度指导 agent：把整合包文件交给它，再接入服务器状态，它就能基于真实配方、任务线、进度和玩家当前资源，回答“下一步该做什么”“这个东西怎么解锁”“我们卡在哪里”。

## 背景

我们经常玩 Minecraft 整合包，但查资料和判断进度很麻烦。整合包里的信息分散在 JEI/REI、FTB Quests、Patchouli 书籍、配置文件、KubeJS/CraftTweaker 脚本、mod 文档和玩家经验里。尤其是在服务器里多人推进时，常见问题不是“不知道一个物品怎么合成”，而是：

- 当前阶段应该优先推进哪条线。
- 想做某个目标物品，需要先解锁哪些机器、维度或任务。
- 某个配方为什么和网上资料不一样。
- 团队现有资源够不够，缺什么材料。
- 谁已经完成了关键进度，服务器整体卡在哪个节点。

Packwise 的目标是把这些信息整理成一个可靠、可追溯、能结合服务器状态的指导系统。

## 目标用户

- 主要用户：在自建或朋友服务器里玩整合包的玩家。
- 次要用户：服务器管理员、整合包作者、想快速理解大型整合包路线的新玩家。

## 核心原则

- Server-first：主要围绕服务器使用场景设计，而不是只做单机离线百科。
- Source-grounded：回答必须尽量附带来源，例如任务章节、配方文件、Patchouli 页面或脚本位置。
- Read-only first：早期只读取服务器状态和给建议，不自动执行高风险服务器命令。
- Pack-specific：以当前整合包的实际文件为准，不默认相信通用 Wiki。
- Progress-aware：不仅回答“怎么做”，还要回答“现在该不该做、做之前缺什么”。
- Multiplayer-aware：把团队进度、共享资源和多人分工作为一等场景。

## 预计产物

### 1. Packwise Core

负责解析整合包，生成结构化知识库。

预计能力：

- 识别 CurseForge `manifest.json`、Modrinth `.mrpack` 和普通整合包 zip。
- 读取 loader、Minecraft 版本、mod 列表和配置文件。
- 解析数据包中的 recipe、tag、loot table、advancement。
- 解析常见整合包内容来源：
  - FTB Quests
  - Patchouli
  - KubeJS
  - CraftTweaker
  - mod/config 配置
- 建立物品、配方、任务、进度、维度、机器之间的关系图。

### 2. Packwise Agent Service

负责查询、推理和对话。

预计能力：

- 提供 HTTP/WebSocket API。
- 支持自然语言问题。
- 支持目标规划，例如“从当前状态到 ME 系统怎么走”。
- 支持下一步建议，例如“我们现在最值得做的三件事”。
- 在回答里返回引用来源和缺失材料。

### 3. Minecraft Server Connector

运行在 Minecraft 服务器里的只读连接器。

预计能力：

- 提供游戏内命令，例如 `/packwise next`、`/packwise goal <item>`、`/packwise ask <question>`。
- 读取玩家背包、维度、坐标、advancement、任务进度等必要上下文。
- 将服务器状态同步给 Packwise Agent Service。
- 按 loader 拆分实现：
  - Fabric connector
  - Forge connector
  - NeoForge connector

### 4. Web Console

提供服务器外的可视化界面。

预计能力：

- 上传整合包并查看解析状态。
- 查看任务线、配方图、目标路径和缺失材料。
- 查看服务器团队进度。
- 管理服务器连接、权限和 API token。

### 5. Admin / CLI 工具

给开发、调试和服务器管理员使用。

预计能力：

- 本地解析整合包。
- 重建索引。
- 导出知识库摘要。
- 检查 connector 与 agent service 的连接状态。

### 6. 文档与示例

预计包含：

- 快速开始。
- 支持的整合包格式。
- 服务端接入教程。
- 安全与权限说明。
- 示例整合包 fixture。

## MVP 边界

第一阶段不追求“全自动玩游戏”，而是做一个可靠的只读指导系统。

优先做：

- 整合包上传和解析。
- 基于配方、任务、文档的问答。
- 服务端只读状态同步。
- 游戏内命令问答。
- 回答附来源。

暂不做：

- 自动执行 `/give`、`/tp`、`/op` 等高风险命令。
- 自动修改世界、自动放置方块、自动操作机器。
- 对所有 mod 的深度专用集成。
- 复杂图数据库和重型微服务架构。

## 成功标准

- 对一个真实整合包，Packwise 能说明主线阶段和关键进度节点。
- 玩家问一个目标物品时，Packwise 能给出当前包内真实可行的路径。
- 在服务器里，Packwise 能结合玩家当前状态给出下一步建议。
- 回答里的核心结论可以追溯到整合包文件或服务器状态。
- 多人服务器使用时，Packwise 能减少查资料和反复问队友的成本。
