# MaiBot 技术文档

本目录包含 MaiBot 二次开发分支的技术文档和设计说明。

## 文档索引

### 核心架构

- **[项目架构分析](project-analysis.md)**
  - 消息处理流程详解
  - Maisaka 核心推理机制
  - 心流管理器工作原理
  - 记忆系统架构
  - 模型编排系统
  - 完整数据流路径

### 新增功能

- **[群聊事件跟踪器](group-event-tracker.md)**
  - 事件识别和跨群关联
  - 中立分析和立场确认
  - 事件生命周期管理
  - 技术实现细节
  - 测试和监控

- **[本地 Embedding 插件](local-embedding-plugin.md)**
  - 本地 GPU 推理架构
  - 与现有系统集成
  - 性能优化策略
  - 部署配置指南
  - 故障处理和降级

## 快速导航

### 我想了解...

- **消息是如何处理的？** → [项目架构分析 - 消息处理流程](project-analysis.md#1-消息处理流程)
- **机器人如何决定是否回复？** → [项目架构分析 - 心流管理器](project-analysis.md#12-心流管理器)
- **推理引擎如何工作？** → [项目架构分析 - Maisaka 核心](project-analysis.md#13-maisaka-核心)
- **记忆系统如何存储和检索？** → [项目架构分析 - 记忆系统](project-analysis.md#2-记忆系统)
- **群聊事件跟踪如何工作？** → [群聊事件跟踪器](group-event-tracker.md)
- **如何使用本地 Embedding？** → [本地 Embedding 插件](local-embedding-plugin.md)

### 我想开发...

- **新的回复功能** → [项目架构分析 - 工具系统](project-analysis.md#工具系统)
- **插件** → [插件开发指南](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/main/docs/guide.md)
- **记忆功能** → [A_memorix 修改政策](../../src/A_memorix/MODIFICATION_POLICY.md)
- **事件跟踪扩展** → [群聊事件跟踪器 - 未来扩展](group-event-tracker.md#未来扩展)

### 我遇到了问题...

- **机器人不回复** → [项目架构分析 - 常见问题](project-analysis.md#常见问题)
- **Embedding 失败** → [本地 Embedding 插件 - 故障处理](local-embedding-plugin.md#故障处理)
- **事件未被识别** → [群聊事件跟踪器 - 测试要点](group-event-tracker.md#测试要点)

## 开发资源

### 官方文档

- [上游项目文档](https://docs.mai-mai.org)
- [部署教程](https://docs.mai-mai.org/manual/)
- [插件开发 SDK](https://github.com/Mai-with-u/maibot-plugin-sdk)
- [插件仓库](https://github.com/Mai-with-u/plugin-repo)

### 本项目文档

- [README](../../README.md)
- [贡献指南](../CONTRIBUTE.md)
- [开发规范](../../AGENTS.md)
- [分支 Changelog](../../CHANGELOG_FORK.md)

### 相关工具

- [NapCat](https://github.com/NapNeko/NapCatQQ) - QQ 协议实现
- [SnowLuma Adapter](https://github.com/Mai-with-u/MaiBot-SnowLuma-Adapter) - 多平台适配器

## 架构图示

### 消息流转路径

```
外部消息
  ↓
Platform Adapter (NapCat/Discord)
  ↓
bot.py (消息入口)
  ↓
heartflow_manager (响应决策)
  ├─ 强制触发 (@ / 命令 / 私聊)
  └─ 概率响应 (活跃度评估)
  ↓
heartflow_message_processor (预处理)
  ├─ 黑名单过滤
  ├─ 命令解析
  └─ 格式标准化
  ↓
Maisaka reasoning_engine (推理循环)
  ├─ 加载上下文 (记忆/表达/黑话)
  ├─ LLM 生成 Thought
  ├─ 解析 Action
  ├─ 执行工具 → Observation
  └─ Final Answer
  ↓
builtin_tool/reply.py (生成回复)
  ↓
SendService (统一发送)
  ↓
Platform Adapter (发送到平台)
```

### 群聊事件跟踪流程

```
高活跃群聊消息
  ↓
event_detector (活跃度检测)
  ├─ 10分钟 ≥ 8条消息
  ├─ ≥ 3位发言者
  └─ ≥ 3倍基线
  ↓
语义聚类 (Embedding 相似度)
  ├─ 跨群关联 (≥0.85)
  └─ 创建/更新事件
  ↓
event_analyzer (后台分析)
  ├─ 积累消息快照
  ├─ 提取根因和时间线
  └─ 识别观点流派
  ↓
待确认状态 (30分钟稳定期)
  ↓
下一条相关消息触发
  ↓
Planner 确认立场
  ├─ 评估证据
  ├─ 确认立场
  └─ 记录依据
  ↓
立场活跃期
  ├─ 注入上下文
  ├─ 中立性审核
  └─ 一致性回复
  ↓
归档 (24小时冷却)
```

### 本地 Embedding 架构

```
EmbeddingService
  ↓
utils_model.py (模型选择)
  ↓
ClientRegistry.get_client("maibot_local_embedding")
  ↓
LocalEmbeddingClient
  ↓
maibot_local_embedding 插件
  ↓
InferenceServer (GPU 推理)
  ├─ 模型加载 (BGE-M3)
  ├─ 批量编码
  └─ 内存管理
  ↓
返回 Embedding 向量
```

## 贡献本文档

发现文档错误或需要补充？

1. 提交 Issue 说明问题
2. 或者直接提交 PR 修改文档
3. 遵循 [Markdown 风格指南](https://www.markdownguide.org/basic-syntax/)

---

<div align="center">
  <sub>MaiBot 技术文档 · 持续更新</sub>
</div>
