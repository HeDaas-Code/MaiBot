# MaiBot 项目架构分析

## 项目概览

MaiBot 是一个基于大语言模型的智能聊天机器人，支持多平台接入（QQ、Discord等），具有记忆系统、表达学习、插件系统等高级特性。

## 核心架构

### 1. 消息处理流程

#### 1.1 消息接收层 (`src/chat/message_receive/`)

- **`bot.py`**: 消息入口，接收来自各平台适配器的消息
  - 注册消息处理器
  - 过滤系统消息和机器人自身消息
  - 调用心流管理器处理消息

- **消息预处理**:
  - 黑名单过滤
  - 命令解析
  - 消息格式标准化

#### 1.2 心流管理器 (`src/chat/heart_flow/`)

**核心职责**: 管理聊天会话的生命周期和消息路由

**`heartflow_manager.py`**:
- 维护活跃会话映射 (`active_flows`)
- 管理会话队列和并发
- 决策是否响应消息

**消息处理流程**:
```
incoming message
    ↓
heartflow_manager.should_process_message()
    ↓ (判断是否响应)
    ├─ 被@/命令触发 → 必须响应
    ├─ 冷却期内 → 跳过
    └─ 评估响应概率 → 可能响应
    ↓
create/get ChatFlow
    ↓
heartflow_message_processor.py
    ↓
dispatch to Maisaka
```

**响应决策机制**:
1. **强制触发条件**:
   - 被直接@
   - 以 `/` 开头的命令
   - 私聊消息

2. **概率响应**:
   - 基于会话活跃度
   - 考虑最近消息数量
   - 检查是否在冷却期

3. **冷却管理**:
   - 回复后进入冷却期
   - 避免过于频繁响应
   - 可通过配置调整冷却时长

#### 1.3 Maisaka 核心 (`src/maisaka/`)

**`reasoning_engine.py`**: 推理引擎，Maisaka 的大脑

**推理循环**:
```
1. 加载上下文（记忆、表达、黑话）
2. 调用 LLM 生成 Thought（思考）
3. 解析 Action（工具调用）
4. 执行工具 → 获得 Observation
5. 继续推理或结束（Final Answer）
```

**工具系统**:
- **内建工具** (`src/maisaka/builtin_tool/`):
  - `reply.py`: 发送消息回复
  - `search.py`: 网络搜索
  - `image_gen.py`: 图片生成
  - 等等...

- **插件工具**:
  - 通过 `proactive_plugin_executor.py` 执行
  - 插件可主动触发 Maisaka 实例

**Replyer 流转**:
- `reply.py` 的 `send_msg_reply()` 被调用
- 通过 `SendService` 发送消息
- 消息发送后记录到 `ChatFlow`
- 更新会话状态和冷却时间

#### 1.4 插件主动触发流程

```
Plugin (proactive=True)
    ↓
proactive_plugin_executor.create_maisaka_for_plugin()
    ↓
创建独立的 Maisaka 实例
    ↓
reasoning_engine 推理循环
    ↓
调用 reply 工具
    ↓
SendService.send_message()
    ↓
返回结果到插件
```

**关键点**:
- 插件触发的 Maisaka 是独立实例
- 不受心流管理器的响应概率限制
- 回复结果通过 `SendService` 统一发送
- 发送后同样更新 `ChatFlow` 状态

### 2. 记忆系统 (`src/A_memorix/`)

**三层记忆架构**:

1. **工作记忆** (Working Memory):
   - 当前对话上下文
   - 短期缓存
   - 快速访问

2. **情景记忆** (Episodic Memory):
   - 对话历史
   - 时间线索引
   - 语义检索

3. **语义记忆** (Semantic Memory):
   - 知识提取
   - 概念关系
   - 长期存储

**向量检索**:
- 使用 Embedding 模型（支持本地/远程）
- 混合检索（向量 + 稀疏）
- 相关性排序

### 3. 表达学习系统 (`src/chat/replyer/`)

**`expression_vector_index.py`**: 表达向量索引

**功能**:
- 学习用户和机器人的表达风格
- 为相似场景提供参考回复
- 支持向量化检索

**学习流程**:
1. 收集对话消息
2. 提取表达特征
3. 计算向量表示
4. 存储到索引
5. 检索时返回相似表达

### 4. 模型编排系统 (`src/llm_models/`)

**`utils_model.py`**: 统一的模型调度器

**支持的模型类型**:
- `chat`: 对话生成
- `embedding`: 向量化
- `utils`: 通用任务
- `event_analysis`: 事件分析

**多提供商支持**:
- OpenAI
- Anthropic
- 自定义 API (通过适配器)
- 本地模型

**关键特性**:
- 自动重试和降级
- 负载均衡
- 成本估算
- 流式输出

### 5. 数据持久化

**SQLite 数据库** (`data/maibot.db`):
- 聊天历史
- 会话状态
- 表达学习数据
- 黑话词库
- 事件档案

**向量存储**:
- 记忆向量索引
- 表达向量索引
- 支持增量更新

## Maisaka 模块定位

**Maisaka 专注于对话场景**:
- 群聊回复
- 私聊对话
- 实时交互

**非对话任务的限制**:
- 生成长文本（如影评）需要特殊设计
- 生成视频等多媒体内容需要专门工具
- 复杂创作任务可能需要独立模块

**扩展方向**:
- 可以通过插件扩展非对话能力
- 可以创建专门的"创作模式"
- 可以集成外部内容生成服务

## 心流清理机制

**清理策略** (`heartflow_manager.py`):
- 长时间无活动的会话会被清理
- **清理=从内存移除**，不是删除数据
- 数据仍保存在数据库中

**唤醒机制**:
- 新消息到达时自动重新创建 `ChatFlow`
- 从数据库加载历史状态
- 恢复会话上下文

**配置参数**:
```python
max_idle_time: int  # 最大空闲时间
cleanup_interval: int  # 清理检查间隔
```

## 关键数据流

### 消息接收到回复的完整路径

```
1. Platform Adapter (NapCat/Discord)
    ↓
2. bot.py (消息入口)
    ↓
3. heartflow_manager (响应决策)
    ↓
4. heartflow_message_processor (预处理)
    ↓
5. Maisaka reasoning_engine (推理)
    ↓
6. builtin_tool/reply.py (生成回复)
    ↓
7. SendService (统一发送)
    ↓
8. Platform Adapter (发送到平台)
```

### 插件主动触发路径

```
1. Plugin (proactive_plugin_executor)
    ↓
2. 创建独立 Maisaka 实例
    ↓
3. reasoning_engine 推理
    ↓
4. reply 工具调用
    ↓
5. SendService 发送
    ↓
6. 返回结果给插件
```

## 配置系统

**配置文件**:
- `config/bot_config.toml`: 机器人配置
- `config/model_config.toml`: 模型配置
- 支持热加载和版本升级

**配置升级机制**:
- `src/config/config_upgrade.py`
- 自动迁移旧版本配置
- 保留用户自定义设置

## 开发建议

1. **添加新功能时**:
   - 优先考虑插件系统
   - 保持 Maisaka 核心简洁
   - 通过工具扩展能力

2. **修改响应逻辑**:
   - 调整 `heartflow_manager` 决策
   - 修改响应概率算法
   - 配置冷却参数

3. **优化性能**:
   - 使用异步 I/O
   - 合理使用缓存
   - 避免阻塞事件循环

4. **扩展记忆系统**:
   - 遵循 `A_memorix/MODIFICATION_POLICY.md`
   - 使用提供的 API
   - 不直接修改核心实现

## 常见问题

**Q: 为什么有时候不回复？**
A: 检查响应概率设置、冷却时间、以及是否被过滤

**Q: 如何让机器人更活跃？**
A: 调高响应概率、减少冷却时间、降低活跃度门槛

**Q: 如何添加新的对话能力？**
A: 通过插件系统或添加新的内建工具

**Q: 记忆系统如何工作？**
A: 自动检索相关历史，结合向量和关键词匹配

**Q: 如何调试推理过程？**
A: 查看日志中的 Thought/Action/Observation 循环

## 参考资源

- [插件开发指南](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/main/docs/guide.md)
- [插件提交规范](https://github.com/Mai-with-u/plugin-repo/blob/main/CONTRIBUTING.md)
- [A_memorix 修改政策](../A_memorix/MODIFICATION_POLICY.md)
- [贡献指南](CONTRIBUTE.md)
