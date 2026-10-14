# MaiBot Fork - 项目摘要

## 基本信息

- **上游项目**: [MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot)
- **本仓库**: [HeDaas-Code/MaiBot](https://github.com/HeDaas-Code/MaiBot)
- **分支策略**: 独立维护，不向上游提交 PR
- **开发分支**: `research/group-event-tracker`
- **初始提交**: 2026-10-15

## 核心改进

### 1. 群聊事件跟踪器 ⭐

智能识别和跟踪群聊热点事件，自动分析事件起因、时间线和观点流派。

**关键特性**:
- 🔍 自动识别高活跃讨论
- 🔗 跨群事件关联（同平台/账号/作用域）
- 🎯 分析期间保持中立
- 💡 完成后确认立场
- 📦 事件结束自动归档

**技术实现**:
- 活跃度门槛 + 语义聚类
- 事件生命周期管理
- 中立性审核机制
- 立场注入系统
- WebUI 可视化界面

### 2. 本地 Embedding 支持 🚀

内嵌本地 GPU 推理，替代远程 API 调用。

**优势**:
- 💰 降低 API 成本
- 🔒 提升隐私保护
- ⚡ 减少网络延迟
- 🎮 充分利用本地 GPU

**实现方式**:
- 插件化架构
- 透明集成
- 自动降级
- 批量优化

## 文档体系

### 技术文档 (`docs/technical/`)

1. **[项目架构分析](docs/technical/project-analysis.md)**
   - 消息处理流程
   - Maisaka 核心机制
   - 心流管理器
   - 记忆系统
   - 完整数据流

2. **[群聊事件跟踪器](docs/technical/group-event-tracker.md)**
   - 设计目标
   - 工作流程
   - 技术实现
   - 测试方法
   - 监控指标

3. **[本地 Embedding 插件](docs/technical/local-embedding-plugin.md)**
   - 技术架构
   - 性能优化
   - 部署配置
   - 故障处理

4. **[开发日志](docs/technical/DEVELOPMENT_LOG.md)**
   - 实现过程
   - 技术难点
   - 经验教训
   - 性能数据
   - 下一步计划

5. **[文档索引](docs/technical/README.md)**
   - 快速导航
   - 架构图示
   - 开发资源

### 项目文档

- **[README.md](README.md)**: 项目介绍和快速开始
- **[CHANGELOG_FORK.md](CHANGELOG_FORK.md)**: 分支改动记录
- **[AGENTS.md](AGENTS.md)**: 开发规范

## 快速开始

### 安装依赖

```bash
# 推荐使用 uv
pip install uv
uv pip install -r requirements.txt
```

### 配置

```bash
# 复制配置模板
cp config/bot_config.toml.template config/bot_config.toml
cp config/model_config.toml.template config/model_config.toml

# 编辑配置文件
vim config/bot_config.toml
vim config/model_config.toml
```

### 启动

```bash
# 启动机器人
python main.py

# 启动 WebUI (可选)
cd dashboard && npm run dev
```

WebUI 默认在 `http://localhost:7999`

## 技术栈

**核心**:
- Python 3.12+
- SQLite
- asyncio

**AI**:
- Gemini 3.8 Flash (主模型)
- GPT-6.1-Sol (中等任务)
- GPT-6-Luna (简单任务)
- BGE-M3 (本地 Embedding)

**前端**:
- React + TypeScript
- Vite + TailwindCSS

## 项目结构

```
MaiBot/
├── src/
│   ├── chat/                      # 聊天核心
│   │   ├── message_receive/       # 消息接收
│   │   ├── heart_flow/            # 心流管理
│   │   └── replyer/               # 回复生成
│   ├── maisaka/                   # Maisaka 核心
│   │   ├── reasoning_engine.py    # 推理引擎
│   │   └── builtin_tool/          # 内建工具
│   ├── services/                  # 服务层
│   │   ├── group_event_service.py # 事件跟踪 (新)
│   │   └── embedding_service.py   # Embedding 服务
│   ├── A_memorix/                 # 记忆系统
│   ├── llm_models/                # 模型编排
│   ├── config/                    # 配置管理
│   ├── common/                    # 公共组件
│   └── webui/                     # WebUI 后端
├── dashboard/                     # WebUI 前端
│   └── src/routes/
│       └── group-events.tsx       # 事件管理页 (新)
├── docs/
│   └── technical/                 # 技术文档 (新)
├── config/
│   ├── bot_config.toml           # 机器人配置
│   └── model_config.toml         # 模型配置
├── README.md                      # 项目介绍
├── CHANGELOG_FORK.md              # 分支改动 (新)
└── PROJECT_SUMMARY.md             # 本文档 (新)
```

## 数据流示意

### 消息处理

```
外部消息 → Platform Adapter → bot.py → heartflow_manager
→ heartflow_message_processor → Maisaka reasoning_engine
→ builtin_tool/reply.py → SendService → Platform Adapter
```

### 事件跟踪

```
高活跃消息 → event_detector → 语义聚类 → 跨群关联
→ event_analyzer → 待确认 → Planner 确认立场
→ 立场活跃 → 归档
```

### 本地 Embedding

```
EmbeddingService → utils_model → ClientRegistry
→ LocalEmbeddingClient → maibot_local_embedding 插件
→ GPU 推理 → 返回向量
```

## 开发指南

### 贡献流程

1. Fork 本仓库 (HeDaas-Code/MaiBot)
2. 创建功能分支
3. 提交改动
4. 推送分支
5. 提交 Pull Request

详见 [贡献指南](docs/CONTRIBUTE.md)

### 开发规范

- 使用 `uv` 管理依赖
- 遵循 [AGENTS.md](AGENTS.md) 规范
- 编写测试覆盖新功能
- 更新相关文档
- 保持代码风格一致

### 测试

```bash
# 运行测试
pytest

# 特定测试
pytest pytests/test_group_event_service.py

# 覆盖率
pytest --cov=src
```

## 性能指标

### 事件跟踪

- 候选检测: <100ms
- 语义聚类: ~200ms (10条消息)
- 跨群关联: ~50ms
- 系统开销: ~5% CPU

### 本地 Embedding

- 单文本编码: ~10ms (GPU)
- 批量编码 (32): ~50ms (GPU)
- 内存占用: ~2GB (BGE-M3)
- GPU 占用: ~15% (推理时)

## 路线图

### V1.0 (当前)
- ✅ 群聊事件跟踪器
- ✅ 本地 Embedding 支持
- ✅ 完整文档体系
- ✅ WebUI 事件管理

### V1.1 (计划中)
- ⏳ 完善边界情况处理
- ⏳ 优化内存使用
- ⏳ 增加测试覆盖
- ⏳ 收集用户反馈

### V2.0 (未来)
- 📅 私聊事件跟踪
- 📅 更复杂的观点分析
- 📅 事件知识图谱
- 📅 自适应活跃度门槛

## 常见问题

**Q: 为什么要 Fork？**
A: 为了自由地进行研究和功能扩展，不受上游项目约束。

**Q: 会同步上游更新吗？**
A: 会选择性同步重要的 bug 修复和功能改进。

**Q: 可以向上游提交 PR 吗？**
A: 本项目不向上游提交 PR，所有改进在本仓库维护。

**Q: 如何参与贡献？**
A: Fork 本仓库并提交 PR，详见贡献指南。

**Q: 群聊事件跟踪如何工作？**
A: 参见 [群聊事件跟踪器文档](docs/technical/group-event-tracker.md)

**Q: 本地 Embedding 有什么好处？**
A: 降低成本、提升隐私、减少延迟。详见 [本地 Embedding 文档](docs/technical/local-embedding-plugin.md)

## 许可证

GPL-3.0 - 与上游项目保持一致

## 联系方式

- GitHub Issues: [提交问题](https://github.com/HeDaas-Code/MaiBot/issues)
- Discussions: [讨论区](https://github.com/HeDaas-Code/MaiBot/discussions)

## 致谢

- **上游项目**: [MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot) 及其社区
- **千石可乐**: 原项目作者
- **所有贡献者**: 感谢每一位参与者

---

<div align="center">
  <p><strong>MaiBot Fork - 让麦麦更智能、更自主、更安全</strong></p>
  <p><sub>基于 MaiM-with-u/MaiBot 的独立开发分支</sub></p>
  <p><sub>最后更新: 2026-10-15</sub></p>
</div>
