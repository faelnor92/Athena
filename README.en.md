# 🎛️ Athena — Self-Hosted Multi-Agent Framework

![Version](https://img.shields.io/badge/version-0.13.1-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)
![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)

**Languages:** [Français](README.md) · English (this file) · [Español](README.es.md) · [Italiano](README.it.md) · [Deutsch](README.de.md) · [中文](README.zh.md) · [日本語](README.ja.md)

A "low-resource", ultra-modular AI orchestrator designed to run on lightweight servers or modest GPUs. Accessible via **Web UI**, **CLI**, **Telegram** and **local Voice**.

📖 **[Read the full User Guide](docs/USER_GUIDE.md)** to learn how to install, configure and use Athena step by step.

## ✨ Key Features

### 🔐 Pro Multi-Tenant & Collaboration
* **Security & SSO**: OIDC / OAuth2 authentication for the enterprise. Admin-managed invite-only registration.
* **Encryption at Rest**: Conversations and execution traces stored in the database (SQLite) are encrypted at rest via Fernet (AES-128-CBC + HMAC-SHA256). The key stays under your control (`.env` or external secret manager).
* **Cost Control (Quotas)**: Automatic spending caps on API usage via per-user daily token quotas.
* **Advanced Security**: Built-in anti-SSRF (DNS rebinding) protection for web browsing and automatic secret redaction in logs.
* **Absolute Isolation**: Each user has their own memory (RAG, Core Memory), calendar, lists and API budget.
* **Self-Service LLM**: Each user can override the global AI models with their own API keys (OpenAI, Anthropic, Gemini, Groq, etc.).
* **Shared Projects**: Collaborative workspaces with fine-grained roles (Reader / Editor) and anti-collision file locking.

### 🧠 Orchestration & LLM Engine
* **Multi-Model**: OpenAI, Anthropic, Gemini, Ollama, Groq, Mistral, Qwen, compatible local APIs.
* **Swarm**: Automatic routing between specialized agents (handoffs), concurrent execution, inter-agent debates.
* **Rigid Pipelines (Optional)**: Force a strict assembly line where agents run sequentially without deviation.
* **Modular Architecture**: FastAPI backend split by functional routers, backed by a robust, thread-safe **SQLite** database.
* **Task Isolation**: Per-run isolated state (ContextVars). Parallel requests never interfere.

### 🌐 Advanced Web UI
* **Virtual Office (3D Isometric)**: Visualize the swarm, highlighted active agents, delegation animations.
* **Cockpit & Telemetry**: Live tracking of consumption (tokens, financial cost per user), runs and errors.
* **Observability**: Full history and a real-time Logs panel in the UI to audit tool calls and the system.
* **Built-in mini-IDE**: Editable file explorer — multi-tab editing (CodeMirror), highlighting, autocomplete, Ctrl+S save (read-only for Readers), resizable panel, and **live-reload** when the agent edits an open file.
* **Integrated Tools**: Calendar, lists, terminal, and a gallery of generated media.
* **No-Code Settings**: Full behavior management (routines, memory, roles) via clear interfaces.

### 🧰 Tools & Extensibility (Skills)
* **MCP Servers (Model Context Protocol)**: Plug external servers in without coding. The Home Assistant MCP connector is vendored locally for maximum security.
* **Computer Use (RPA 2.0)**: Drive an interactive headless browser optimized for LLMs.
* **Git & Code Navigation**: Understand your code repositories (logs, branches, editing), run bash/python via a Docker sandbox.
* **On-the-fly Skill Creation**: The AI can literally *code its own tools* and save them permanently to extend its capabilities!
* **SSH Administration**: Manage your remote servers via SSH commands.
* **Creativity & Web**: Deep web search, image/video generation (Fal, Replicate), scraping.
* **Media & Meetings**: Summarize and transcribe audio files or entire meetings.

### 🎨 AthenaDesign Studio
* **AI design studio**: describe what you want and Athena generates and **previews live** **HTML/CSS/JS** interfaces, **React/JSX** components, **Mermaid** diagrams, and runs **Python** (PowerPoint presentations, Matplotlib/Plotly charts) in an isolated **Docker sandbox**.
* **Design System**: apply your brand (colors, typography) — by hand, by extracting from CSS, or by **importing from a site's URL**.
* **Imports & vision**: attach images/documents (PDF) or capture a web page as a reference; automatic vision routing (multimodal model if available, otherwise graceful degradation).
* **Iteration**: annotate the preview, **WYSIWYG sliders** (color/radius/font), versions, **auto-correction** of failing scripts, export to **PDF/PPTX/HTML** and **share by link** (read-only, sandboxed).
* **Unified projects**: an Athena project holds both **code** and **design**.

### 🔌 Plugins & Auto-correction
* **Plugins tab**: enable first-class extensions on top of MCP servers and skills.
* **Claude Code plugin**: delegate heavy coding to the **Claude Code** agent (CLI), scoped to the active project; automatically granted to the Coder when enabled.
* **Auto-correction (self-healing)**: both design (Python) and the **Coder** (Code-Test-Fix: `pytest`/`npm test`) automatically fix their errors in a bounded loop.

### 🏠 Home Automation & Automations
* **Native Home Automation (Home Assistant)**: Read state and run actions (lights, blinds, sensors) instantly.
* **Spatial Awareness**: Knows which room you're in to target actions on your physical environment.
* **Proactive Routines & Workflows**: Per-user CRON scheduling, webhook triggers, deep **n8n** integrations.
* **Calendar & Lists**: Two-way sync with Google Calendar, iCal and CalDAV. Manage todos and shopping lists.
* **Active Notifications**: Autonomous alerts from Athena to Telegram, Discord, Slack, Email and Webhooks.

### 💾 Memory & Learning
* **RAG Vector Database**: Automatic semantic indexing of documents via ChromaDB.
* **Knowledge Graph & Core Memory**: Store durable facts and model relationships as graphs.
* **Self-Improvement**: Persistent experience feedback after complex tasks to refine future behavior.
* **Backup & Restore**: Full state backup/restore (conversations, RAG, routines, configurations).

### 🎙️ Voice Assistant (STT/TTS)
* **100% Local & Smooth**: Very fast text-to-speech via **Kokoro TTS** (local Docker API) and transcription via optimized **Whisper STT**.
* **Wake Word Detection**: openWakeWord with "barge-in" support (interrupting the AI's speech).
* **ESP32-S3 Satellites**: Connect ESPHome voice satellites directly to the framework (S2S), bypassing Home Assistant.

## 🚀 Quick Install (1-Liner)

> [!NOTE]
> *If this repository is private, you need access rights (token or SSH key) for these commands to work, or you can clone the repo manually.*

**Linux / macOS**: Copy and paste this command into your terminal:
```bash
curl -sSL https://raw.githubusercontent.com/faelnor92/Athena/main/install.sh | bash
```

**Windows**: Run this command in PowerShell:
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/Athena/main/install.ps1 | iex
```

* **Docker Compose alternative**: `docker compose up -d --build`

**Start**: `athena start` or `python3 server.py`. Available at 👉 **http://localhost:8000/**.

### ⚙️ Multi-worker deployment (scaling)
Shared mutable state (accounts & quotas, auth sessions, routines, invites, shared projects, per-user config) is stored in a common SQLite database in WAL mode (`athena_state.sqlite3`) with atomic updates — so it is **consistent across multiple workers**:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```
> [!NOTE]
> **RAG in multi-worker mode.** In single-process mode the vector store is embedded (local ChromaDB). For multi-worker, set **`CHROMA_SERVER_HOST`** (+ `CHROMA_SERVER_PORT`): all workers then talk to the same ChromaDB server (safe concurrent writes). The provided `docker-compose.yml` already includes this `chroma` service and wiring. All other state is multi-worker-safe natively.

### 🔒 Production security
- **TLS required**: put Athena behind an HTTPS reverse proxy (Caddy, Nginx, Traefik). The server automatically emits **HSTS** when it detects HTTPS (`X-Forwarded-Proto: https`).
- **Encryption key outside `.env`**: to resist disk/backup theft, inject `DB_ENCRYPTION_KEY` via an environment variable / secret manager rather than leaving it in the `.env` file next to the databases.
- **Security headers** (CSP, X-Frame-Options, nosniff, Referrer/Permissions-Policy) active by default — `SECURITY_HEADERS=false` to disable, `CONTENT_SECURITY_POLICY` to customize.
- **Guardrails**: anti-brute-force throttle (`LOGIN_MAX_FAILS`/`LOGIN_WINDOW_SECONDS`), rate limiting (`RATE_LIMIT_PER_MIN`, default 300/IP/min), password policy (`MIN_PASSWORD_LENGTH`, default 8), **audit log** (`GET /api/audit`, admin), and **admin approval** of automations created by "user" accounts.
- **Per-tool RBAC**: `ADMIN_ONLY_TOOLS="execute_bash_command,run_ssh_command,..."` restricts code/command execution to admins.
- **Container**: the image runs as a **non-root** user with a `HEALTHCHECK`. Install audit: `bash scripts/security_scan.sh` (pip-audit + bandit + secrets).

### 📡 LLM Observability (optional — OpenInference / Phoenix)
On top of the built-in cockpit (traced runs, usage, audit), Athena can export **standardized LLM traces** (OpenInference / OpenTelemetry) to **Phoenix** (Arize), a self-hostable trace viewer with evaluations. Enable:
```bash
pip install -r requirements-observability.txt        # optional packages
docker compose --profile observability up -d         # starts Phoenix (UI: http://localhost:6006)
```
then in `.env`: `OPENINFERENCE_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:6006/v1/traces`. Disabled by default, with zero impact.

---

## 🛡️ Comparison: Athena vs the Market

> [!NOTE]
> **Methodology.** Compare like with like: **Athena**, **Hermes** and **OpenClaw** are *hosted apps/assistants*; **CrewAI** and **AutoGen** are *orchestration libraries* you integrate into your own code (security, auth or multi-tenancy are the responsibility of the app you build around them — hence the "N/A"). Athena's differentiator isn't "having a UI" (OpenClaw also has apps), but **multi-tenancy + enterprise-grade security + agentic coding + observability** combined in a single self-hosted product.

| Category | Criterion | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Interface & UX** | **Graphical UI** | **Full web dashboard (3D isometric, node graph, integrated terminal)** | No | Companion apps (macOS/iOS/Android) + Live Canvas | No (separate CrewAI Studio) | Basic (AutoGen Studio) |
| | **Interaction channels** | Web, Terminal UI, Telegram, Discord, Slack, Voice | CLI, Telegram, Slack, Discord | **15+ channels (WhatsApp, Telegram, Signal, iMessage, Slack, Discord…)** | Python code | CLI / code |
| | **IDE / local dev integration** | Web code console + Sandbox | No | Yes (local assistant) | Integrates into your code | Integrates into your code |
| **Orchestration** | **Multi-Agent Model** | **Swarm with automatic semantic routing** | Parallel isolated sub-agents | Multi-agent routing (per-workspace isolation) | Sequential / Hierarchical | Debates / Group chat |
| | **Group topologies** | Organic debates and handoffs | Isolated handoffs | Per-channel/agent routing | Sequential/hierarchical process | **Advanced group chat (Round Robin, etc.)** |
| | **Rigid pipelines** | Yes (optional assembly line) | Organic | — | **Native (strict assembly line)** | Linear or organic |
| | **Persistence (Memory)** | **Vector DB + encrypted cross-session history** | Yes (SQLite + FTS5) | Yes (persistent sessions) | Yes (short/long term + entities) | Limited (extensions/teachability) |
| | **Closed-loop learning** | **Auto-generated skills + experience RAG** | Yes (skill generation) | Extensible tools | No | No (beyond teachability) |
| | **Tools & MCP** | **Native tools + MCP + Home Assistant** | Yes (MCP) | Yes (browser, canvas, cron, MCP) | Yes (crewai-tools + MCP) | Yes (function calling, extensions) |
| **Global Security** | **Authentication** | **Password, tokens, SSO (OIDC)** | No (local) | Basic (local) | N/A (library) | N/A (library) |
| | **Access control (RBAC)** | **Yes (Reader/Editor roles, per-user permissions)** | No | No | N/A | N/A |
| | **Per-user quotas / costs** | **Yes (per-account daily token quota + budget alerts)** | No | No | N/A | N/A |
| **Execution & Network** | **Execution sandbox** | **Ephemeral Docker container (limited resources)** | Varies | Host | Via code interpreter | **Yes (Docker supported)** |
| | **Anti-SSRF shield** | **Yes (DNS rebinding, internal network/metadata blocking)** | No | No | N/A | N/A |
| **Data Protection** | **Secret redaction (logs)** | **Yes (API keys / passwords redacted)** | No | Partial | N/A | N/A |
| | **Encryption at rest** | **Yes (Fernet/AES-128 on conversations + traces)** | No | Depends on storage | N/A | N/A |
| | **Multi-tenant isolation** | **Yes (memory/calendar/budget isolated per user)** | No | Per workspace | N/A | N/A |
| | **Human approval (HITL)** | **Yes (sensitive actions intercepted in the UI)** | Yes (via chat) | Basic | Build it yourself | Build it yourself |

## 📄 License

Distributed under the **Apache 2.0** license — see [LICENSE](LICENSE). Free to use, modify and redistribute.
