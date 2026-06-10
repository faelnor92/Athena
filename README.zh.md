# 🎛️ Athena — 自托管多智能体框架

![Version](https://img.shields.io/badge/version-0.11.23-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)
![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)

**语言：** [Français](README.md) · [English](README.en.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Deutsch](README.de.md) · 中文（本文件） · [日本語](README.ja.md)

一个「低资源」、高度模块化的 AI 编排器，可在轻量服务器或普通 GPU 上运行。支持通过 **Web 界面**、**CLI**、**Telegram** 和**本地语音**访问。

📖 **[阅读完整用户指南](docs/USER_GUIDE.md)**，逐步学习安装、配置和使用 Athena。

## ✨ 核心功能

### 🔐 专业多租户与协作
* **安全与 SSO**：面向企业的 OIDC / OAuth2 认证；由管理员管理的邀请制注册。
* **静态加密**：存储在数据库（SQLite）中的对话与执行轨迹通过 Fernet（AES-128-CBC + HMAC-SHA256）静态加密。密钥始终由你掌控（`.env` 或外部密钥管理器）。
* **成本控制（配额）**：通过每用户每日 token 配额自动限制 API 支出。
* **高级安全**：内置防 SSRF（DNS 重绑定）保护用于网页浏览，并在日志中自动脱敏机密。
* **绝对隔离**：每个用户拥有独立的记忆（RAG、Core Memory）、日历、清单和 API 预算。
* **自助 LLM**：每个用户可用自己的 API 密钥覆盖全局模型（OpenAI、Anthropic、Gemini、Groq 等）。
* **共享项目**：协作工作区，支持细粒度角色（只读 / 编辑）和防冲突文件锁。

### 🧠 编排与 LLM 引擎
* **多模型**：OpenAI、Anthropic、Gemini、Ollama、Groq、Mistral、Qwen 及兼容的本地 API。
* **Swarm（蜂群）**：在专门智能体间自动路由（handoff）、并发执行、智能体间辩论。
* **刚性流水线（可选）**：强制严格的流水线，智能体顺序执行，不偏离。
* **模块化架构**：按功能路由拆分的 FastAPI 后端，基于稳健且线程安全的 **SQLite** 数据库。
* **任务隔离**：按执行隔离的状态（ContextVars）。并行请求互不干扰。

### 🌐 高级 Web 界面
* **虚拟办公室（3D 等距）**：可视化蜂群、高亮活跃智能体、委派动画。
* **驾驶舱与遥测**：实时跟踪消耗（token、每用户费用）、执行与错误。
* **可观测性**：完整历史记录和实时日志面板，用于审计工具调用与系统。
* **内置迷你 IDE**：**可编辑**的文件浏览器——多标签编辑（CodeMirror）、高亮、自动补全、Ctrl+S 保存（只读用户为只读）、可调整面板，以及当智能体修改已打开文件时的**实时重载**。
* **集成工具**：日历、清单、终端和生成媒体库。
* **无代码设置**：通过清晰界面全面管理行为（例程、记忆、角色）。

### 🧰 工具与可扩展性（Skills）
* **MCP 服务器（Model Context Protocol）**：无需编码即可接入外部服务器。Home Assistant MCP 连接器本地内置以确保最大安全。
* **Computer Use（RPA 2.0）**：驱动为 LLM 优化的交互式无头浏览器。
* **Git 与代码导航**：理解你的代码仓库（日志、分支、编辑），通过 Docker 沙箱执行 bash/python。
* **即时创建 Skills**：AI 可以*编写自己的工具*并永久保存以扩展能力！
* **SSH 管理**：通过 SSH 命令管理远程服务器。
* **创意与网络**：深度网页搜索、图像/视频生成（Fal、Replicate）、抓取。
* **媒体与会议**：总结和转写音频文件或整场会议。

### 🎨 AthenaDesign Studio
* **AI 设计工作室**：描述你的需求，Athena 即时生成并**实时预览** **HTML/CSS/JS** 界面、**React/JSX** 组件、**Mermaid** 图表，并在隔离的 **Docker 沙箱**中运行 **Python**（PowerPoint 演示、Matplotlib/Plotly 图表）。
* **Design System（设计系统）**：应用你的品牌（颜色、字体）——手动输入、从 CSS 提取，或**从网站 URL 导入**。
* **导入与视觉**：附加图片/文档（PDF）或抓取网页作为参考；自动视觉路由（有多模态模型则用，否则优雅降级）。
* **迭代**：在预览上批注、**所见即所得滑块**（颜色/圆角/字体）、版本管理、对出错脚本**自动纠错**、导出 **PDF/PPTX/HTML**，以及**通过链接分享**（只读、沙箱化）。
* **统一项目**：一个 Athena 项目同时承载**代码**与**设计**。

### 🔌 插件与自动纠错
* **插件标签页**：在 MCP 服务器和 skills 之外启用一流集成。
* **Claude Code 插件**：将繁重的编码委派给 **Claude Code** 智能体（CLI），限定在当前项目；启用后自动授予编码者。
* **自动纠错（自愈）**：设计（Python）和**编码者**（Code-Test-Fix：`pytest`/`npm test`）都会在有限循环内自动修复错误。

### 🏠 家庭自动化与自动化
* **原生家居自动化（Home Assistant）**：即时读取状态并执行操作（灯光、窗帘、传感器）。
* **空间感知**：知道你在哪个房间，从而将操作定向到你的物理环境。
* **主动例程与工作流**：按用户隔离的 CRON 调度、Webhook 触发、深度 **n8n** 集成。
* **日历与清单**：与 Google Calendar、iCal 和 CalDAV 双向同步。管理待办和购物清单。
* **主动通知**：Athena 主动向 Telegram、Discord、Slack、邮件和 Webhook 发送提醒。

### 💾 记忆与学习
* **RAG 向量数据库**：通过 ChromaDB 自动语义索引文档。
* **知识图谱与 Core Memory**：归档持久事实并以图的形式建模关系。
* **自我提升**：复杂任务后持久化经验反馈，以优化未来行为。
* **备份与恢复**：完整的状态备份/恢复（对话、RAG、例程、配置）。

### 🎙️ 语音助手（STT/TTS）
* **100% 本地且流畅**：通过 **Kokoro TTS**（本地 Docker API）实现极快的语音合成，并通过优化的 **Whisper STT** 转写。
* **唤醒词检测**：openWakeWord，支持「打断」（barge-in，打断 AI 说话）。
* **ESP32-S3 卫星**：将 ESPHome 语音卫星直接接入框架（S2S），无需经过 Home Assistant。

## 🚀 快速安装（一行命令）

> [!NOTE]
> *如果此仓库为私有，你需要访问权限（token 或 SSH 密钥）才能运行这些命令，或手动克隆仓库。*

**Linux / macOS**：将此命令复制粘贴到终端：
```bash
curl -sSL https://raw.githubusercontent.com/faelnor92/Athena/main/install.sh | bash
```

**Windows**：在 PowerShell 中运行：
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/Athena/main/install.ps1 | iex
```

* **Docker Compose 方案**：`docker compose up -d --build`

**启动**：`athena start` 或 `python3 server.py`。访问 👉 **http://localhost:8000/**。

### ⚙️ 多 worker 部署（扩展）
共享的可变状态（账户与配额、认证会话、例程、邀请、共享项目、每用户配置）存储在 WAL 模式的公共 SQLite 数据库（`athena_state.sqlite3`）中，采用原子更新——因此**在多个 worker 间保持一致**：
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```
> [!NOTE]
> **多 worker 下的 RAG。** 单进程下向量库为内嵌（本地 ChromaDB）。多 worker 时请设置 **`CHROMA_SERVER_HOST`**（+ `CHROMA_SERVER_PORT`）：所有 worker 连接同一 ChromaDB 服务器（并发写入安全）。随附的 `docker-compose.yml` 已包含 `chroma` 服务。其余状态原生支持多 worker。

### 🔒 生产环境安全
- **强制 TLS**：将 Athena 置于 HTTPS 反向代理之后（Caddy、Nginx、Traefik）。检测到 HTTPS（`X-Forwarded-Proto: https`）时服务器自动发送 **HSTS**。
- **加密密钥置于 `.env` 之外**：为抵御磁盘/备份被盗，通过环境变量/密钥管理器注入 `DB_ENCRYPTION_KEY`。
- **安全响应头**（CSP、X-Frame-Options、nosniff、Referrer/Permissions-Policy）默认启用——`SECURITY_HEADERS=false` 关闭，`CONTENT_SECURITY_POLICY` 自定义。
- **防护**：防暴力破解限流（`LOGIN_MAX_FAILS`/`LOGIN_WINDOW_SECONDS`）、速率限制（`RATE_LIMIT_PER_MIN`，默认 300/IP/分钟）、密码策略（`MIN_PASSWORD_LENGTH`，默认 8）、**审计日志**（`GET /api/audit`，管理员）以及对「user」账户所建自动化的**管理员审批**。
- **按工具 RBAC**：`ADMIN_ONLY_TOOLS="execute_bash_command,run_ssh_command,..."` 将代码/命令执行限定给管理员。
- **容器**：镜像以**非 root**用户运行并带 `HEALTHCHECK`。安装审计：`bash scripts/security_scan.sh`。

### 📡 LLM 可观测性（可选 — OpenInference / Phoenix）
除内置驾驶舱外，Athena 还可将**标准化 LLM 轨迹**（OpenInference / OpenTelemetry）导出到 **Phoenix**（Arize）。启用：
```bash
pip install -r requirements-observability.txt
docker compose --profile observability up -d         # Phoenix (UI: http://localhost:6006)
```
然后在 `.env` 中：`OPENINFERENCE_ENABLED=true` 与 `OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:6006/v1/traces`。默认关闭。

---

## 🛡️ 对比：Athena vs 市场

> [!NOTE]
> **方法论。** 对比可比之物：**Athena**、**Hermes** 和 **OpenClaw** 是*托管应用/助手*；**CrewAI** 和 **AutoGen** 是集成进自有代码的*编排库*（因此为「N/A」）。Athena 的差异化不在于「有 UI」，而是在单一自托管产品中融合了**多租户 + 企业级安全 + 智能体编码 + 可观测性**。

| 类别 | 标准 | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **界面与 UX** | **图形界面** | **完整 Web 仪表盘（3D 等距、节点图、集成终端）** | 无 | 配套应用 + Live Canvas | 无（独立 CrewAI Studio） | 基础（AutoGen Studio） |
| | **交互渠道** | Web、终端 UI、Telegram、Discord、Slack、语音 | CLI、Telegram、Slack、Discord | **15+ 渠道** | Python 代码 | CLI / 代码 |
| | **IDE / 本地开发集成** | Web 代码控制台 + 沙箱 | 无 | 是（本地助手） | 集成进你的代码 | 集成进你的代码 |
| **编排** | **多智能体模型** | **带自动语义路由的 Swarm** | 并行隔离子智能体 | 多智能体路由 | 顺序 / 分层 | 辩论 / 群聊 |
| | **群组拓扑** | 有机辩论与 handoff | 隔离 handoff | 按渠道/智能体路由 | 顺序/分层流程 | **高级群聊** |
| | **刚性流水线** | 是（可选流水线） | 有机 | — | **原生** | 线性或有机 |
| | **持久化（记忆）** | **向量库 + 跨会话加密历史** | 是（SQLite + FTS5） | 是（持久会话） | 是（短/长期） | 有限 |
| | **闭环学习** | **自生成 skills + 经验 RAG** | 是 | 可扩展工具 | 无 | 无 |
| | **工具与 MCP** | **原生 + MCP + Home Assistant** | 是（MCP） | 是（浏览器、canvas、cron、MCP） | 是（crewai-tools + MCP） | 是（function calling） |
| **整体安全** | **认证** | **密码、token、SSO (OIDC)** | 无（本地） | 基础（本地） | N/A | N/A |
| | **访问控制 (RBAC)** | **是（只读/编辑角色）** | 无 | 无 | N/A | N/A |
| | **每用户配额/成本** | **是（每日 token 配额 + 预算告警）** | 无 | 无 | N/A | N/A |
| **执行与网络** | **执行沙箱** | **临时 Docker 容器（资源受限）** | 视情况 | 主机 | 经代码解释器 | **是（Docker）** |
| | **防 SSRF 屏障** | **是（DNS 重绑定、内网/元数据拦截）** | 无 | 无 | N/A | N/A |
| **数据保护** | **机密脱敏（日志）** | **是** | 无 | 部分 | N/A | N/A |
| | **静态加密** | **是（Fernet/AES-128）** | 无 | 取决于存储 | N/A | N/A |
| | **多租户隔离** | **是（按用户隔离记忆/日历/预算）** | 无 | 按工作区 | N/A | N/A |
| | **人工审批 (HITL)** | **是（UI 中拦截敏感操作）** | 是（经聊天） | 基础 | 需自行实现 | 需自行实现 |

## 📄 许可证

基于 **Apache 2.0** 许可证发布——见 [LICENSE](LICENSE)。可自由使用、修改与再分发。
