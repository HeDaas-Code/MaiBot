# MaiBot Fork 开发日志

## 2026-10-15: 项目初始化与核心功能实现

### 项目背景

从 [MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot) 分支并开始二次开发。目标是在保持原项目"真实感"设计理念的基础上，增强智能性、自主性，并提升隐私保护。

### 完成的工作

#### 1. 群聊事件跟踪器 (Group Event Tracker)

**设计理念**:
- 智能识别群聊中的热点事件
- 跨群关联同一事件的讨论
- 分析期间保持中立，避免草率表态
- 分析完成后确认立场并保持一致
- 事件结束后归档，不再主动注入立场

**核心实现**:
1. **事件检测** (`src/services/group_event_service.py`):
   - 活跃度门槛：10分钟≥8条消息，≥3位发言者，≥3倍基线
   - 语义聚类识别同一话题
   - 跨群关联（同平台、同账号、同作用域，置信度≥0.85）

2. **生命周期管理**:
   ```
   候选 → 信息积累 → 待确认 → 立场活跃 → 复核/冷却 → 已归档
   ```

3. **中立性保障**:
   - Replyer 生成后审核中立性
   - 检测到偏向则重写
   - 不合格时使用中性模板
   - 在 `send_service.py` 统一检查，防止绕过

4. **立场确认机制**:
   - 等待下一条相关消息触发
   - Planner 必须先确认立场才能回复
   - 提供去标识化的跨群摘要
   - 不暴露其他群原文或成员身份

5. **数据持久化**:
   - 数据库升级 v43 → v44
   - 新增 `events` 表存储事件档案
   - 新增 `event_messages` 表存储消息快照

6. **WebUI 集成**:
   - 事件列表页面
   - 事件详情和时间线可视化
   - 观点流派对比展示
   - 只读模式，不可编辑

**技术难点**:
- 跨群事件去重和合并算法
- 中立性审核的准确性
- 事件状态流转的复杂性
- 性能优化（后台异步处理）

**测试覆盖**:
- 事件检测边界测试
- 跨群关联准确性测试
- 中立性审核测试
- 立场确认流程测试
- 生命周期完整性测试

#### 2. 本地 Embedding 支持

**设计目标**:
- 降低 API 成本
- 提升隐私保护
- 减少网络延迟
- 充分利用本地 GPU

**实现方案**:
1. **插件架构**:
   - 创建 `maibot_local_embedding` 插件
   - 实现 `LocalEmbeddingClient`
   - 注册到 `ClientRegistry`

2. **透明集成**:
   - 无需修改现有代码
   - 自动替换远程 API 调用
   - 失败时降级到远程 API

3. **性能优化**:
   - GPU 加速推理
   - 批量处理提升吞吐量
   - 智能内存管理
   - 模型缓存复用

4. **模型支持**:
   - BGE-M3 (1024维)
   - 支持其他 Sentence-Transformers 模型
   - 动态模型加载

**Bug 修复**:
- 修复 `maibot_local_embedding` 客户端未注册
- 修复表达向量索引历史补建失败
- 完善 Embedding 指纹验证流程
- 改进降级机制

#### 3. 文档体系建设

**技术文档** (`docs/technical/`):
1. **项目架构分析** (`project-analysis.md`):
   - 消息处理流程详解
   - Maisaka 核心工作原理
   - 心流管理器机制
   - 记忆系统架构
   - 模型编排系统
   - 完整数据流路径

2. **群聊事件跟踪器** (`group-event-tracker.md`):
   - 设计目标和核心概念
   - 完整工作流程
   - 技术实现细节
   - 测试要点
   - 监控指标
   - 未来扩展方向

3. **本地 Embedding 插件** (`local-embedding-plugin.md`):
   - 技术架构
   - 实现细节
   - 性能优化
   - 部署配置
   - 故障处理
   - 测试方法

4. **文档索引** (`README.md`):
   - 快速导航
   - 架构图示
   - 开发资源
   - 贡献指南

**项目文档更新**:
- 更新主 README 标注分支状态
- 创建 CHANGELOG_FORK.md
- 更新 AGENTS.md 开发规范
- 同步所有文档中英文内容

#### 4. 配置系统改进

**模型配置** (v11 → v12):
```toml
[tasks.event_analysis]
description = "事件分析和中立性审核"
default_model = "gpt-6.1-sol"
temperature = 0.3
max_tokens = 4000

[models.local-bge-m3]
api_provider = "maibot_local_embedding"
model_name = "BAAI/bge-m3"
dimension = 1024
```

**群聊事件配置**:
```toml
[group_event_tracker]
enabled = true
activity_window_minutes = 10
min_messages = 8
min_participants = 3
baseline_multiplier = 3.0
cross_group_threshold = 0.85
stabilization_minutes = 30
archive_cooldown_hours = 24
```

#### 5. 代码质量提升

**修复的问题**:
- 事件检测不启用
- 跨群事件去重逻辑
- 时间线显示问题
- Embedding 客户端注册
- 前端构建警告

**改进的方面**:
- 更完善的错误处理
- 更清晰的日志记录
- 更健壮的降级机制
- 更好的性能监控

### 技术栈

**后端**:
- Python 3.12+
- SQLite (数据持久化)
- asyncio (异步处理)
- Sentence-Transformers (Embedding)
- PyTorch (GPU 推理)

**前端**:
- React + TypeScript
- Vite (构建工具)
- TailwindCSS (样式)

**AI 模型**:
- Gemini 3.8 Flash (主模型)
- GPT-6.1-Sol (中等任务)
- GPT-6-Luna (简单任务)
- BGE-M3 (本地 Embedding)

### 下一步计划

#### 短期 (1-2周)
- [ ] 完善事件跟踪器的边界情况处理
- [ ] 优化本地 Embedding 的内存使用
- [ ] 增加更多单元测试和集成测试
- [ ] 收集用户反馈并迭代

#### 中期 (1-2个月)
- [ ] 私聊事件跟踪支持
- [ ] 更复杂的观点分析
- [ ] 事件知识图谱
- [ ] 自适应活跃度门槛
- [ ] 更多本地模型支持

#### 长期 (3-6个月)
- [ ] 跨平台事件关联
- [ ] 增量学习用户偏好
- [ ] 长期趋势分析
- [ ] 与记忆系统深度集成
- [ ] 多模态事件理解

### 开发笔记

#### 经验教训

1. **事件循环不能阻塞**:
   - 同步工作必须放入线程池
   - 后台任务通过队列异步处理
   - 监控事件循环卡顿

2. **中立性审核很重要**:
   - LLM 容易无意中表达偏向
   - 需要多轮审核和回退机制
   - 中性模板是最后保障

3. **跨群关联要谨慎**:
   - 不能泄露其他群信息
   - 去标识化处理至关重要
   - 隐私边界必须明确

4. **文档先于代码**:
   - 先写设计文档再实现
   - 文档即需求，文档即测试
   - 好文档节省大量沟通成本

#### 性能数据

**事件检测**:
- 候选检测延迟: <100ms
- 语义聚类时间: ~200ms (10条消息)
- 跨群关联检查: ~50ms

**本地 Embedding**:
- 单文本编码: ~10ms (GPU)
- 批量编码 (32): ~50ms (GPU)
- 内存占用: ~2GB (BGE-M3)

**系统开销**:
- 事件跟踪增加: ~5% CPU
- 本地 Embedding: ~15% GPU (推理时)
- 数据库增长: ~1MB/天/事件

### 参考资料

**上游项目**:
- [MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot)
- [插件 SDK](https://github.com/Mai-with-u/maibot-plugin-sdk)
- [插件仓库](https://github.com/Mai-with-u/plugin-repo)

**技术文档**:
- [Sentence-Transformers](https://www.sbert.net/)
- [BGE-M3](https://huggingface.co/BAAI/bge-m3)
- [PyTorch](https://pytorch.org/)
- [FastAPI](https://fastapi.tiangolo.com/)

**设计参考**:
- ReAct: Reasoning and Acting with LLMs
- Prompt Engineering Guide
- LangChain Architecture

### 致谢

感谢上游 MaiBot 项目及其社区的优秀工作，为本项目提供了坚实的基础。

---

**下次更新**: 功能迭代和性能优化

**维护者**: HeDaas  
**最后更新**: 2026-10-15
