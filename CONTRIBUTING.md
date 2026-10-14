# 贡献指南

感谢你对 MaiBot Fork 项目的关注！

## ⚠️ 重要声明

**本项目是 [MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot) 的独立开发分支。**

- ✅ 欢迎向本仓库 (`HeDaas-Code/MaiBot`) 提交 PR
- ❌ 本项目**不向上游**提交 PR
- 🔄 本项目会选择性同步上游的重要更新

如果你想向原项目贡献，请访问：
https://github.com/MaiM-with-u/MaiBot

## 如何贡献

### 1. Fork 本仓库

**注意：Fork 的是 `HeDaas-Code/MaiBot`，不是上游！**

```bash
# 克隆你的 Fork
git clone https://github.com/YOUR_USERNAME/MaiBot.git
cd MaiBot

# 添加本仓库为 origin（如果还没有）
git remote add origin https://github.com/YOUR_USERNAME/MaiBot.git

# 添加本项目主仓库为 upstream
git remote add upstream https://github.com/HeDaas-Code/MaiBot.git
```

### 2. 创建功能分支

```bash
# 从最新的 main 分支创建
git checkout -b feature/your-feature-name

# 或从研究分支创建
git checkout -b feature/your-feature-name research/group-event-tracker
```

### 3. 提交改动

遵循提交信息规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 类型：**
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `refactor`: 代码重构
- `perf`: 性能优化
- `test`: 测试
- `chore`: 构建/工具

**示例：**
```bash
git commit -m "feat(routine): 实现日常日程模块核心服务

- 添加 DailyRoutineService
- 实现生物节律系统
- 集成到心流管理器
- 添加情绪状态管理"
```

### 4. 推送分支

```bash
# 推送到你的 Fork
git push origin feature/your-feature-name
```

### 5. 创建 Pull Request

**关键：确保 PR 的目标仓库是 `HeDaas-Code/MaiBot`！**

在 GitHub 上：
1. 访问你的 Fork 仓库
2. 点击 "Pull Request"
3. **确认 base repository 是 `HeDaas-Code/MaiBot`**
4. **不要选择 `MaiM-with-u/MaiBot`！**
5. 填写 PR 描述
6. 提交

### 6. 等待 Review

我们会尽快 review 你的 PR。可能会：
- 提出修改建议
- 请求补充测试
- 要求更新文档

## 开发规范

### 代码规范

遵循 [AGENTS.md](AGENTS.md) 中的规范：

1. **Import 顺序**：标准库 → 第三方库 → 本地模块
2. **注释**：保留原有注释，复杂逻辑添加注释
3. **类型注解**：保留原有注解，复杂函数添加注解
4. **变量使用**：明确类型后避免不必要的 fallback
5. **避免 getattr/setattr**：尽量直接访问属性

### 测试要求

1. 新功能必须有测试覆盖
2. Bug 修复应添加回归测试
3. 测试应放在 `pytests/` 目录

```bash
# 运行测试
pytest

# 运行特定测试
pytest pytests/test_your_module.py

# 覆盖率
pytest --cov=src
```

### 文档要求

1. 新功能需要更新相关文档
2. 技术设计应添加到 `docs/technical/`
3. 重要改动更新 `CHANGELOG_FORK.md`

### WebUI 开发

1. 小改动不需要立即 build
2. 完成较大功能后再 `npm run build`
3. 开发服务器固定在 7999 端口

## 项目结构

```
MaiBot/
├── src/                      # 源代码
│   ├── chat/                 # 聊天核心
│   ├── maisaka/              # Maisaka 核心
│   ├── services/             # 服务层
│   ├── A_memorix/            # 记忆系统
│   ├── llm_models/           # 模型编排
│   └── webui/                # WebUI 后端
├── dashboard/                # WebUI 前端
├── docs/                     # 文档
│   └── technical/            # 技术文档
├── pytests/                  # 测试
└── config/                   # 配置
```

## 贡献方向

欢迎在以下方向贡献：

### 🎯 核心功能
- 群聊事件跟踪器优化
- 本地 Embedding 性能提升
- 日常日程模块实现
- 新的人格化功能

### 🐛 Bug 修复
- 修复已知问题
- 提升稳定性
- 性能优化

### 📚 文档
- 完善技术文档
- 添加使用示例
- 翻译文档

### 🧪 测试
- 增加测试覆盖
- 完善测试用例
- 集成测试

### 🎨 WebUI
- 改进用户界面
- 添加新页面
- 优化交互体验

## 不建议的贡献

以下改动可能不被接受：

❌ 与本项目理念不符的功能  
❌ 过度复杂化的设计  
❌ 破坏现有功能的重构  
❌ 未经讨论的大规模改动  
❌ 向上游提交的 PR（请直接向上游提交）

## 行为准则

1. **尊重他人**：友善、专业的交流
2. **建设性反馈**：提供具体的改进建议
3. **开放态度**：愿意接受不同观点
4. **责任心**：对自己的代码负责

## 许可证

本项目采用 GPL-3.0 许可证。提交贡献即表示你同意你的代码在此许可证下发布。

## 联系方式

- **GitHub Issues**: [提交问题](https://github.com/HeDaas-Code/MaiBot/issues)
- **GitHub Discussions**: [讨论区](https://github.com/HeDaas-Code/MaiBot/discussions)

## 常见问题

### Q: 我应该向哪个仓库提交 PR？

**A**: 向 `HeDaas-Code/MaiBot`（本仓库）提交。不要向 `MaiM-with-u/MaiBot`（上游）提交。

### Q: 如何同步上游更新？

**A**: 
```bash
git fetch upstream
git merge upstream/main
# 解决冲突后提交
```

### Q: 我的改动会被合并到上游吗？

**A**: 不会。本项目独立维护，不向上游提交 PR。

### Q: 我可以同时向两个仓库贡献吗？

**A**: 可以。如果某个功能适合上游，你可以分别向两个仓库提交独立的 PR。

### Q: 为什么不向上游提交？

**A**: 本项目是研究和功能扩展项目，有独立的开发方向和理念。某些改动可能不适合上游的定位。

---

<div align="center">
  <p><strong>感谢你的贡献！</strong></p>
  <p><sub>让麦麦变得更好 🎉</sub></p>
</div>
