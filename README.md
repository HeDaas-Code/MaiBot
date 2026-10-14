<a id="-双语--bilingual"></a>

<div align="center">

  <!-- Language Switcher -->
  <p>
    <a href="#-双语--bilingual"><picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/key-lang-bilingual-night.svg"><img src="depends-data/readme/key-lang-bilingual-day.svg" alt="双语 / Bilingual"></picture></a>
    <a href="docs/README_CN.md"><picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/key-lang-zh-night.svg"><img src="depends-data/readme/key-lang-zh-day.svg" alt="中文"></picture></a>
    <a href="docs/README_EN.md"><picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/key-lang-en-night.svg"><img src="depends-data/readme/key-lang-en-day.svg" alt="English"></picture></a>
  </p>

  <!-- Hero -->
  <picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/hero-night.svg"><img src="depends-data/readme/hero-day.svg" alt="麦麦 MaiBot：致力于了解你，用真人的方式聊天的数字生命" width="100%"></picture>

  <!-- Badges Row -->
  <p>
    <img src="https://img.shields.io/badge/Python-3.12+-8fd6a0?style=flat-square&labelColor=5a544a" alt="Python Version">
    <img src="https://img.shields.io/github/license/HeDaas-Code/MaiBot?label=License&color=8fd6a0&style=flat-square&labelColor=5a544a" alt="License">
    <img src="https://img.shields.io/badge/Fork-MaiM--with--u%2FMaiBot-f08a5d?style=flat-square&labelColor=5a544a" alt="Fork">
  </p>

</div>

<a id="english"></a>

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-intro-night.svg"><img src="depends-data/readme/sec-intro-day.svg" alt="简介 · INTRO" width="100%"></picture>

> **🔱 本项目为 [MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot) 的二次开发分支**
>
> 基于原项目进行研究和功能扩展，不会向上游提交 PR。所有改进和新功能都在本仓库维护。

麦麦 MaiSaka 是一个基于大语言模型的可交互智能体。  

MaiSaka 不仅仅是一个机器人，不仅仅是一个可以帮你完成任务的"有帮助的助手"，她还是一个致力于了解你，并以真实人类的风格进行交互的数字生命。她不追求完美，不追求高效，但追求亲切和真实。  
<sub><sup>MaiSaka is an interactive agent based on large language models. MaiSaka is more than just a bot, and more than a "helpful assistant" that completes tasks. She is a digital life form that tries to understand you and interact in a genuinely human style. She does not pursue perfection or efficiency above all else, but warmth and authenticity.</sup></sub>

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-features-night.svg"><img src="depends-data/readme/sec-features-day.svg" alt="特色功能 · FEATURES" width="100%"></picture>

### 原版功能

- **💬 多平台支持**  
  支持 QQ（NapCat）、Discord 等多个平台。  
  <sub><sup>Multi-platform: QQ (NapCat), Discord, etc.</sup></sub>

- **🧠 记忆系统**  
  三层记忆架构（工作记忆、情景记忆、语义记忆），让麦麦记住你。  
  <sub><sup>Three-tier memory (working, episodic, semantic) to remember you.</sup></sub>

- **📚 表达学习**  
  学习用户和机器人的表达风格，提供更自然的回复。  
  <sub><sup>Learns expression styles for more natural responses.</sup></sub>

- **🔌 插件系统**  
  灵活的插件架构，支持功能扩展。  
  <sub><sup>Flexible plugin system for feature extensions.</sup></sub>

- **🎨 WebUI 管理**  
  美观的 Web 界面，方便管理和监控。  
  <sub><sup>Beautiful web interface for management and monitoring.</sup></sub>

### 二开新增功能

- **📊 群聊事件跟踪器**  
  智能识别和跟踪群聊热点事件，自动分析事件起因、时间线和观点流派。分析期间保持中立，分析完成后确认立场并在事件活跃期间保持一致。事件结束后自动归档，不再主动注入立场。  
  <sub><sup>**Group Event Tracker**: Intelligently identifies and tracks hot topics in group chats, automatically analyzes root causes, timelines, and viewpoints. Maintains neutrality during analysis, confirms stance after completion, and keeps it consistent during active discussion. Auto-archives when the event ends.</sup></sub>

- **🎯 本地 Embedding 支持**  
  内嵌本地 GPU 推理的 Embedding 模型，降低 API 成本，提升隐私性。  
  <sub><sup>**Local Embedding**: Built-in local GPU inference for embedding models, reducing API costs and improving privacy.</sup></sub>

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-quick-start-night.svg"><img src="depends-data/readme/sec-quick-start-day.svg" alt="快速开始 · QUICK START" width="100%"></picture>

### 安装依赖

推荐使用 `uv` 管理依赖：

```bash
# 安装 uv（如果还没有）
pip install uv

# 安装项目依赖
uv pip install -r requirements.txt
```

### 配置

1. 复制配置模板：
```bash
cp config/bot_config.toml.template config/bot_config.toml
cp config/model_config.toml.template config/model_config.toml
```

2. 编辑 `config/bot_config.toml`，配置平台适配器

3. 编辑 `config/model_config.toml`，配置 LLM 模型

### 启动

```bash
# 启动机器人
python main.py

# 启动 WebUI（可选）
cd dashboard && npm run dev  # 开发模式
cd dashboard && npm run build && npm start  # 生产模式
```

WebUI 默认在 `http://localhost:7999` 访问。

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-docs-night.svg"><img src="depends-data/readme/sec-docs-day.svg" alt="文档 · DOCS" width="100%"></picture>

### 技术文档

- **[项目架构分析](docs/technical/project-analysis.md)**: 深入理解 MaiBot 的核心架构和工作流程
- **[群聊事件跟踪器](docs/technical/group-event-tracker.md)**: 新功能的详细设计文档

### 原版文档

- **[部署教程](https://docs.mai-mai.org/manual/)**: 完整的部署指南
- **[官方文档](https://docs.mai-mai.org)**: 原版功能文档
- **[插件开发](https://github.com/Mai-with-u/maibot-plugin-sdk/blob/main/docs/guide.md)**: 插件开发指南
- **[贡献指南](docs/CONTRIBUTE.md)**: 如何参与贡献

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-related-night.svg"><img src="depends-data/readme/sec-related-day.svg" alt="相关项目 · Related Projects" width="100%"></picture>

### 上游项目

- **[MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot)**: 原始项目，由千石可乐和社区维护

### 原版衍生项目

- **[Amaidesu](https://github.com/MaiM-with-u/Amaidesu)**: 让麦麦在 B 站开播  
- **[MoFox_Bot](https://github.com/MoFox-Studio/MoFox-Core)**: 基于 MaiCore 0.10.0 的 Fork  
- **[MaiCraft](https://github.com/MaiM-with-u/Maicraft)**: 让麦麦陪你玩 Minecraft（暂停维护）

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-idea-night.svg"><img src="depends-data/readme/sec-idea-day.svg" alt="设计理念 · IDEA" width="100%"></picture>

> **千石可乐说：**  
> <sub><sup><strong>SengokuCola:</strong></sup></sub>
> - 这个项目最初只是为了给牛牛 bot 添加一点额外的功能，但是功能越写越多，最后决定重写。其目的是为了创造一个活跃在 QQ 群聊的"生命体"。目的并不是为了写一个功能齐全的机器人，而是一个尽可能让人感知到真实的类人存在。  
>   <sub><sup>This project originally started as a few extra features for the NiuNiu bot, but it kept growing until a full rewrite became inevitable. The goal was to create a "life form" active in QQ group chats, not a feature-complete bot, but something as human-like and real-feeling as possible.</sup></sub>
> - 程序的功能设计理念基于一个核心的原则："最像而不是好"。  
>   <sub><sup>The core design principle is: "more lifelike, not merely better."</sup></sub>
> - 如果人类真的需要一个 AI 来陪伴自己，并不是所有人都需要一个完美的，能解决所有问题的"helpful assistant"，而是一个会犯错的，拥有自己感知和想法的"生命形式"。  
>   <sub><sup>If people truly want AI companionship, not everyone needs a perfect "helpful assistant" that solves every problem. Some people may want a life form that can make mistakes and has its own perceptions and thoughts.</sup></sub>

### 二开理念

在保持原版"真实感"设计理念的基础上，我们致力于：

- **增强智能性**: 通过事件跟踪等功能，让麦麦更好地理解复杂的群聊场景
- **提升自主性**: 让麦麦能够自主识别和参与重要讨论，而不仅仅是被动响应
- **保持克制**: 分析期间保持中立，避免草率表态，体现理性和思考
- **注重隐私**: 支持本地模型推理，减少对外部 API 的依赖

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-contributors-night.svg"><img src="depends-data/readme/sec-contributors-day.svg" alt="致谢 · Acknowledgments" width="100%"></picture>

### 上游项目

感谢 [MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot) 项目及其所有贡献者。

### 开源项目友链

- **[AstrBot](https://github.com/AstrBotDevs/AstrBot)**: 优秀的LLM Agent项目  
- **[Pallas-Bot](https://github.com/PallasBot/Pallas-Bot)**: 以防你不知道牛牛又开始更新了

### 特别致谢

- **[萨卡班甲鱼](https://en.wikipedia.org/wiki/Sacabambaspis)**: 千石可乐很喜欢的生物  
- **[略nd](https://space.bilibili.com/1344099355)**: 为麦麦绘制早期的精美人设  
- **[NapCat](https://github.com/NapNeko/NapCatQQ)**: 现代化的基于 NTQQ 的 Bot 协议实现

<picture><source media="(prefers-color-scheme: dark)" srcset="depends-data/readme/sec-notice-night.svg"><img src="depends-data/readme/sec-notice-day.svg" alt="注意事项 &amp; License" width="100%"></picture>

> [!IMPORTANT]
> 使用前请阅读 [用户协议 (EULA)](EULA.md) 和 [隐私协议](PRIVACY.md)。AI 生成内容请仔细甄别。  
> <sub><sup>Please read the <a href="EULA.md">End User License Agreement (EULA)</a> and <a href="PRIVACY.md">Privacy Policy</a> before use. Please evaluate AI-generated content carefully.</sup></sub>

> [!NOTE]
> 本项目为二次开发分支，与上游项目独立维护。所有新功能和改进仅在本仓库发布。  
> <sub><sup>This is a fork with independent development. All new features and improvements are released only in this repository.</sup></sub>

**License**: GPL-3.0

---

<div align="center">
  <sub>基于 <a href="https://github.com/MaiM-with-u/MaiBot">MaiM-with-u/MaiBot</a> 的二次开发 · Fork of MaiM-with-u/MaiBot</sub>
</div>
