# MaiBot Fork Changelog

本文档记录此分支相对于上游项目的所有改动。

## [Unreleased]

### 新增功能

#### 群聊事件跟踪器
- 智能识别群聊热点事件，基于活跃度门槛和语义聚类
- 跨群事件关联（同平台、同账号、同路由作用域）
- 事件生命周期管理：候选→信息积累→待确认→立场活跃→复核→归档
- 分析期间保持中立，自动审核回复中立性
- 分析完成后由 Planner 确认立场，事件活跃期间保持一致
- 事件归档后不再主动注入立场
- 支持事件根因、时间线、观点流派的自动分析
- WebUI 只读事件档案页面

#### 本地 Embedding 支持
- 内嵌本地 GPU Embedding 推理
- 支持 BGE-M3 等开源模型
- 降低 API 成本，提升隐私性
- 透明集成，无需修改现有代码
- 自动降级到远程 API（失败时）

### 改进

#### 配置系统
- 新增 `event_analysis` 模型任务配置
- 模型配置版本升级：v11 → v12
- 支持本地 Embedding 模型配置
- `maibot_local_embedding` 客户端类型注册

#### 数据库
- 数据库版本升级：v43 → v44
- 新增 `events` 表存储事件档案
- 新增 `event_messages` 表存储事件消息快照
- 支持事件时间线、观点流派等结构化数据

#### WebUI
- 新增群聊事件管理页面
- 事件列表、详情、时间线可视化
- 观点流派对比展示
- 来源消息引用查看

### 修复

#### Embedding 服务
- 修复 `maibot_local_embedding` 客户端未注册问题
- 修复表达向量索引历史补建失败
- 完善 Embedding 指纹验证流程
- 改进 Embedding 降级机制

#### 群聊事件
- 修复事件检测不启用问题
- 完善事件状态流转逻辑
- 修复跨群事件去重和合并
- 改进事件时间线显示

#### 前端构建
- 同步前端依赖更新
- 修复 WebUI 构建警告
- 优化开发服务器配置

### 文档

#### 新增文档
- [项目架构分析](docs/technical/project-analysis.md)
- [群聊事件跟踪器设计](docs/technical/group-event-tracker.md)
- [本地 Embedding 插件](docs/technical/local-embedding-plugin.md)
- [分支 Changelog](CHANGELOG_FORK.md)

#### 更新文档
- README: 标注分支状态，说明新功能
- AGENTS.md: 更新开发规范和工作流程

### 开发工具

#### 依赖管理
- 推荐使用 `uv` 管理依赖
- 同步更新 `requirements.txt`
- 新增本地 Embedding 相关依赖

#### 测试
- 新增群聊事件跟踪器测试
- 新增本地 Embedding 集成测试
- 完善 CI/CD 配置

---

## 版本约定

本分支采用独立的版本号，不与上游版本号冲突：

- 格式：`v{major}.{minor}.{patch}-fork`
- 示例：`v1.0.0-fork`

首个正式版本将基于当前实现发布。

---

## 关于上游同步

本分支为研究和功能扩展项目，**不会向上游提交 PR**。所有改进和新功能都在本仓库独立维护。

如需同步上游更新：
```bash
git fetch upstream
git merge upstream/main
# 解决冲突后提交
```

---

## 贡献指南

欢迎对本分支提交 PR，请遵循以下规范：

1. Fork 本仓库（HeDaas-Code/MaiBot）
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交改动：`git commit -m "描述你的改动"`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request 到本仓库

详见 [贡献指南](docs/CONTRIBUTE.md)。

---

<div align="center">
  <sub>基于 <a href="https://github.com/MaiM-with-u/MaiBot">MaiM-with-u/MaiBot</a> 的独立开发分支</sub>
</div>
