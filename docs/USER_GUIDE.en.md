# 📖 Athena User Guide

🌍 **Languages**: [Français](USER_GUIDE.md) · English · [Español](USER_GUIDE.es.md) · [Italiano](USER_GUIDE.it.md) · [Deutsch](USER_GUIDE.de.md) · [中文](USER_GUIDE.zh.md) · [日本語](USER_GUIDE.ja.md)

Welcome! If you're reading this guide, you've just installed **Athena**, your multi-agent Artificial Intelligence conductor. This document is designed to help you get started with the tool.

---

## ✨ What's new in version 0.33.0

- **Nothing is lost on restart**: long operations (revising or translating a whole novel, big agent runs) now **resume where they left off** instead of starting over. Speech synthesis is cached too: regenerating an audiobook after fixing one chapter only re-synthesizes what changed.
- **The Coder has a safety net**: an automatic snapshot is taken before its edits; if tests stay broken despite its fixes, everything can be rolled back in one move (back to the previous state).
- **Fewer AI outages**: when a model provider is saturated (rate limit hit), Athena switches to a healthy fallback model **before** the call instead of waiting for the failure — your free quotas work as one pool.
- **Self-learned skills under supervision**: a new skill is tested first, then put on trial (a "canary" period) — adopted only after several successful real uses, evicted if it fails.
- **Cleaner memory**: facts that are never re-confirmed fade over time, and on contradiction (a move, a new job…) the most recent fact wins.
- **Cockpit → "🕒 Recent runs"**: click a past run to unfold its timeline (tools called, handoffs…) and **replay it in one click**.
- **Hardened security**: much stronger anti-XSS protection, sessions extended while you use them (no more logout mid-work) but never eternal, SSO token kept out of logs, automatic alerts on vulnerable dependencies.

---

## ✨ What's new in version 0.32.0

- **Briefing with departure times**: for each appointment with a location, Athena computes when to leave based on live traffic ("leave at 6:26pm for your 7pm meeting"). Set your home address (Settings) and a location on your events.
- **Smarter Watch (Vigie)**: on an incident (e.g. a stopped VM), it correlates events, proposes a fix and can run it after your one-tap approval (Telegram).
- **Routine suggestions**: Athena spots your habits (e.g. weather every morning) and offers to create an automatic routine.
- **More reliable coding**: the Coder reviews its own work (security/quality), keeps a per-project memory across sessions, and avoids looping.
- **More personality in Design**: with no design charter given, AthenaDesign commits to a real visual identity.

---

## ✨ What's new in version 0.31.0

- **AthenaDesign — faster, cheaper edits**: changing a design no longer rewrites all its code (only the changes are applied) → big token savings. New **⏹️ Stop** button to cancel a running generation. Pick the **model** right in the Design tab.
- **Reliable road traffic**: driving time with traffic jams (TomTom) is now computed via the dedicated tool, not guessed. (free TomTom key in Settings)
- *Public transit: not available — no reliable free source, especially for SNCF trains.*

---

## ✨ What's new in version 0.30.0

- **Pick the model in the Code console**: a **"🤖 Model"** menu in the terminal bar lets you choose the code LLM on the fly (e.g. a "coder" model), like in AthenaDesign. Empty = your default.

---

## ✨ What's new in version 0.29.0

- **Real-time public transport**: schedules, **delays** and disruptions (train, tram, bus) + journeys — "next tram at Homme de Fer?", "is my train delayed?". (free Navitia key to set in Settings)
- **OCR**: faithful **text extraction from an image or PDF** (even scanned) — "read this invoice".
- **Hyperlocal weather**: precise weather by coordinates (not just the city). Set your latitude/longitude in Settings for street-level accuracy.
- **Contextual recommendations**: "what do you suggest?" → Athena combines weather, calendar, tasks, disruptions and your preferences.
- **Road traffic**: **driving time with traffic jams** + incidents — "how long to work?". (free TomTom key to set)
- **Everything configurable in the UI**: new "External integrations" section in Settings (Navitia/TomTom keys, weather, OCR model).

---

## ✨ What's new in version 0.28.0

- **Dedicated model for Design and Code**: in **Settings → My LLM model & keys**, pick a specific model for **AthenaDesign** (🎨) and for the **Code console** (🧩), different from the chat model (e.g. a "coder" model for code, another for conversation). The lists only show models that are **actually reachable** (your endpoint + providers whose key is set).
- **Real-time token counter**: **incoming (↓) and outgoing (↑)** usage is shown live during generation (chat, design, code). A **global total** sits in the top bar — **persistent** (kept across restarts) with a **↺** button to reset it.
- **Live Code console**: the agent's steps and token usage stream **in real time**, like the chat, without waiting for completion.
- **AthenaDesign improvements**: an edit now starts from the **version you are viewing** (no longer always the latest); more **modern** designs; auto-fix also detects **blank screens** caused by CSS.

---

## 1. 🌟 First Launch and Login

Once Athena is installed and started on your machine, the graphical interface (UI) is only accessible through your web browser.

1. Open your browser and go to: **`http://localhost:8000`** (or your server's IP address if you installed it on another machine).
2. On the very first launch, you'll be asked to create an account with an email address and a password.
3. Once logged in, you land on the **virtual Desktop**.

---

## 2. 💬 Chatting with the AI

There are **two ways** to interact with Athena: the Web Interface and the Terminal (CLI).

### A. From the Web Interface (UI)
This is the most visual and simplest method.
- **The 3D view**: On the main page, you'll see a visual representation of Athena and its "Agents" (the Coder, the Researcher, etc.). When Athena thinks or delegates a task, you'll see glowing animations showing you which agent is working.
- **The automatic Orchestrator**: In the chat bar at the bottom, simply type your request. In the Web Interface, **you always talk to the Orchestrator**. It is smart enough to understand your request and automatically assign it to the right agent (e.g., it will hand off to the Coder Agent if you ask for a script).
- **Artifacts in the chat**: when the AI produces previewable code (HTML, **React**, SVG, **Mermaid**, **Markdown**), an **"👁️ Preview"** button opens a **docked preview panel** on the right — run in an isolated sandbox. You **navigate between the versions** generated through the conversation, **copy/download** the code, or click **"🎨 Open in AthenaDesign"** to continue in the studio.
- **The file Explorer (Workspaces)**: On the left is a panel containing your files. You can drag and drop documents (PDF, Markdown, source code) so the AI can analyze them.
- **The built-in Editor (mini-IDE)**: click a file to **edit** it directly in the browser — several open files as **tabs**, syntax highlighting, autocompletion (Ctrl+Space), and **saving** with **Ctrl+S** (💾). A *Viewer* of a shared project stays read-only. You can **shrink or collapse the explorer** (center handle or the "◀ Collapse" button) to enlarge the editor, and when the **agent modifies an open file**, your view **refreshes live** (along with the presence of other viewers).
- **The Coder Console (interactive terminal)**: a real terminal where you talk to the **Coder** agent to develop. Specifics:
  - **Independent target project**: a selector lets you code on a project that is **different** from the chat/voice one (your voice commands and home automation keep their own context).
  - **Project tree** on the right (the chat is hidden there as it's unnecessary): it **refreshes automatically** — you see the files created by the agent appear.
  - **IDE in a separate window**: the **"⧉ IDE"** button (or a click on a file in the tree) opens the editor in a **real movable window** (ideal on a 2nd screen), with tabs, highlighting, autocompletion and **Ctrl+S**. *(On first use, allow pop-ups for the site.)*
  - Commands prefixed with `$` or `!` run directly as shell; otherwise the Coder agent handles your request and **writes the files into the project** (Docker sandbox mounted on the project).

### C. Projects & Collaboration (shared Workspaces)
A **project** is a dedicated working folder. When you select a project in the project bar (at the top of the explorer), **everything the AI does (reading, code editing, terminal, git) is confined to that folder** — handy for isolating a code repository or a client folder.
- **Create / switch project**: `＋ Project` button then select from the list. Each user has their own projects, invisible to others.
- **Share a project** (`👥 Share` button): as the **owner**, you invite other users and choose their role:
  - **Viewer**: can browse and chat with the AI about the project, but **cannot modify ANYTHING** — even by asking the agent (the lock is enforced server-side, on every write tool: file editing, git, bash, Python). Impossible to bypass.
  - **Editor**: can modify files, run code, commit.
- Only the owner can share, change roles, or delete the project.

### B. From the Interactive Console (CLI)
If you prefer the terminal to the graphical interface, you can start a pure text conversation.
Go to the Athena folder and type:
`python3 athena_cli.py`

> [!TIP]
> **Force a specific agent (Console only)**: Unlike the web interface where the Orchestrator handles everything, the console lets you bypass the conductor and talk directly to a specialist agent. To do so, use:
> `python3 athena_cli.py --agent Codeur`

---

## 3. 🛠️ What can Athena do? (The Super-Powers)

Athena is not just a "ChatGPT". It's a framework of **autonomous artificial intelligence agents** that integrate dozens of tools ("Skills") capable of acting on your machine and on the web.

### 💻 Agentic Code (Software Engineering)
This is the heart of the system. Athena can replace a system administrator or a developer:
- **Python & Bash Execution (Sandbox)**: The AI writes code and runs it autonomously in a secure Docker sandbox.
- **On-the-fly Skill Creation**: A unique feature — the AI can code new "tools" to improve itself, and save them permanently into its base source code!
- **SSH Administration**: The AI can connect to your other remote servers via SSH for maintenance.
- **Computer Use (RPA 2.0)**: The AI can open a real hidden web browser, click buttons, fill in forms and scrape sites.
- **Git & Code Navigation**: The AI can read your Git repositories, understand your existing source code and edit it live (file/`glob`/content search, file outline, references).
- **Diagnostics after each edit (feedback loop)**: on every file change, Athena re-reads the **errors/warnings** it introduced (the **basedpyright** LSP server for Python, built-in fallback otherwise) and **fixes them immediately**. These diagnostics also appear in the **Code** tab ("🔍 Analyze" button).
- **Session task list**: for multi-step work, the agent keeps a **checklist** (📋 Tasks) visible in `athena_cli` and the Code tab, updated in real time.
- **Plan mode (read-only)**: the **"🧭 Plan mode"** button (or `/plan` / `/build` in the CLI) — the agent **proposes a plan without modifying anything**; switch back to normal mode to execute.
- **Project instructions**: drop a `CLAUDE.md`, `ATHENA.md` or `AGENTS.md` at your project root (conventions, commands) — Athena loads them automatically, cascading up to the git root.
- **Autonomous Maintenance**: A nightly agent can check and repair the source code automatically.

### 🎨 AthenaDesign Studio (AI Design)
A built-in design studio (the **🎨 Design** tab). Describe what you want to create, Athena generates it and **displays it live**:
- **Types**: web pages (HTML/CSS/JS), interactive **React apps**, **Mermaid diagrams**, and **Python** scripts (**PowerPoint** presentations, charts). **Starter templates** (Landing, Pitch deck, Dashboard…) pre-fill a prompt.
- **Your brand (Design System)**: the "Design System" panel to provide your colors/font — by hand, by pasting CSS, via **"🌐 From a URL"**, or by **generating it automatically**: **"🧩 From the code"** (inferred from the project: Tailwind/CSS), **"🖼️ From an image"** (palette/typography from a screenshot), **"✨ From a description"** (starter brand for an empty project).
- **References**: attach an image/document (📎) or a web page (🔗) as inspiration.
- **Refine**: annotate the preview, adjust live (color/radius/font sliders), browse versions. If a Python script fails, Athena **fixes itself**.
- **Share / export**: **Share** button (read-only link), **PDF Export**, and `.pptx` download.
- *Tip*: an Athena project brings together **code and design** — you manage both in the same place.

### 🔌 Plugins (including Claude Code)
In **Settings > 🔌 Plugins**, enable extensions. The **Claude Code plugin** calls the **Claude Code** coding agent (you need the `claude` CLI installed and logged in): once enabled, your **Coder** can delegate complex coding tasks to it, directly in the active project. *(Uses your Claude subscription/key.)*

### 🏠 Home Automation, Context & Daily Life
- **Native Home Automation (Home Assistant)**: The AI connects directly to your home automation. Ask it *"Turn off the living room light"* or *"Close the blinds"* and it does so instantly.
- **MCP Extensions (Advanced)**: Athena supports the MCP protocol. This lets it plug in complex plugins (such as deep access to the Home Assistant database to create automations, or any other existing MCP server).
- **Spatial Awareness**: The AI can know which room you're in (if you have sensors) to adapt its actions (e.g., *"Turn on the light"* will turn on the one in the room you're in).
- **Weather & Time**: Multi-day weather forecasts and time synchronization.
- **Lists & Shopping**: Ask it to add milk to your shopping list or to create a to-do list.

### 📅 Productivity & Communication
- **Calendar & Planning**: Synchronization with your calendars (iCal, CalDAV) to read and create events.
- **Meeting Summaries**: Ability to transcribe and summarize meetings or audio files.
- **Notifications**: Athena can send you messages on its own initiative via Telegram, Discord or Slack.
- **Media Generation**: Image creation (via Fal/Replicate API) and file manipulation (PDF, documents).
- **Workflows (n8n)**: Triggering complex scenarios via n8n webhooks.

### ⏰ Proactive Routines
Athena doesn't wait for you to talk to it. Ask it: *"Give me a summary of my day every morning at 7:30"*. It will wake up on its own, analyze your calendar, the weather, the state of your home, and may even start the coffee maker!

---

## 4. ⚙️ Understanding the Interface Settings

By clicking the gear icon (⚙️) in the sidebar, you access your profile settings. **Each setting is strictly isolated to your user.**

### "🔑 API Keys" Tab (My Model & LLM Keys)
- **AI Provider (e.g., OpenAI, Anthropic, Ollama)** and **Model Name**: Choose the version of the AI you want to use.
- **Personal API Key**: If this field is filled in, Athena will use YOUR key to operate, and you will be billed on your own developer account. This lets you override the server's default model.
- **📊 My usage**: just below your keys, a summary of your personal consumption (requests, tokens, cost €) for today, the last 30 days and in total — to track your spending at a glance. (An administrator, for their part, sees the consumption of all accounts.)

### 🔐 Securing my account ("Users" tab)
- **My password**: change it whenever you want (min. 8 characters). For security, changing your password **logs out your other sessions**.
- **Two-factor authentication (2FA)**: click **Enable 2FA**, add the account to your authenticator app (Google Authenticator, Authy, FreeOTP…) by scanning/entering the displayed secret, then enter a code to confirm. At each login, a **temporary code** will then be required in addition to the password. You can disable it at any time (a code is required to confirm).
  - *Lost device?* An administrator can reset your 2FA to give you back access.

### "Calendar & Todo" Tab
- **Main Calendar (URL)**: Paste the address of an iCal feed (Google Calendar). The AI will then be able to read your schedule.
- **CalDAV Server (URL, User, Password)**: If you use an advanced calendar (Nextcloud, Synology), the AI will be able to *create* and *modify* events directly.

### "Behavior & Security" Tab (Athena's Brain)
This is the most important section for adjusting the machine's overall behavior and safeguards. It is divided into several subsections:

#### 1. Execution & safeguards
- `Code/command execution sandbox`: Choose **Docker** (recommended) so the AI runs its scripts in a secure sandbox, or **Local** if you want it to act directly on your operating system.
- `Self-improvement`: Allows the AI to learn from its failures to create future behavior rules.
- `Budgets (Time and Tokens)`: Financial safeguards. Lets you cap the maximum number of seconds (0 = infinite) or the maximum number of tokens the AI is allowed to consume per task.
- `Daily cost alert`: If daily spending exceeds this threshold in euros, you'll receive a notification.

#### 2. Security
- `Auto-approve sensitive tools`: By default (unchecked), the AI will always ask you for confirmation before using a tool marked as "sensitive" (e.g., writing to a system file). If you check it, the AI becomes fully autonomous (at your own risk).
- `Admin password / CORS origins`: Securing the web server to prevent unwanted external connections.
- `Session validity duration`: Time (in hours) before being logged out of the interface (default: 168h, i.e., one week).
- `Quotas and Limits`: The system protects your finances. An administrator can set a daily token consumption limit in the users database.
- `Encryption at rest`: Conversations and execution traces are encrypted in the database (SQLite) via Fernet (AES-128-CBC + HMAC). The key is stored in your installation's `.env` — **don't lose it** (otherwise the encrypted history becomes unreadable), and for real protection against disk theft, keep it outside the folder (injected environment variable / secret manager).
- `Built-in protections (invisible)`: Athena automatically masks your API keys and secrets in the logs (Redaction) and includes anti-SSRF protection blocking web requests to your internal network or your Cloud metadata.

#### 3. Orchestration & agents (advanced)
- `LLM routing (Delegation Router)`: The Orchestrator reads your message and chooses the right agent.
- `Fast model`: You can force a very fast model (e.g., `gpt-4o-mini` or `haiku`) just for routing decisions, making the AI snappier.
- `Fallback models`: If your main AI's API crashes, Athena will try to use these backup models.
- `Prompt cache`: Technology that saves money and time on long conversations.
- `Self-critique`: If enabled, the AI re-reads and checks its own answer before sending it to you.

#### 4. Memory
- `Fact base (Core Memory)`: Lists everything Athena has permanently learned about you (your tastes, your job). You can delete items there.
- `Knowledge Graph`: In addition to simple facts, the AI builds a network of relationships ("Graph") between entities to better understand your context.
- `Compaction beyond N messages`: To avoid blowing up the bill, Athena automatically summarizes the old parts of the conversation after N messages (40 by default).
- `Recent messages kept verbatim`: Athena always keeps the last N strict exchanges in short-term memory (12 by default).

#### 5. Expressive voice
- `Vocal emotions`: The LLM inserts `[laugh]`, `[sad]` tags into its texts, and the voice engine adapts its tone!
- `Expressive TTS server & Voice`: If you use a third-party voice engine (such as XTTS), enter its IP address here.

#### 6. Spatial Awareness (Presence / follow-me)
- `Current-room HA entity`: If you have presence detectors on Home Assistant, indicate the entity here (e.g., `sensor.current_room`). The AI will then know which room you're in to turn on the right light or adapt its behavior.

#### 7. Automation (n8n)
- `Allowed workflows`: You can connect Athena to complex n8n automations by giving it access to web addresses (Webhooks).

### The other Tabs of the Settings Panel
In addition to "Behavior", the settings sidebar gives you access to other specialized menus:

* **"Knowledge (RAG)" tab**: This is where you can ask the AI to analyze (or purge) the documents you placed in the file Explorer.
* **"Routines" tab**: Lets you schedule automatic tasks (e.g., "Summarize the house every day at 7:00"). You can also retrieve the "Webhooks" addresses of these routines, or have a routine **trigger a deterministic Workflow** (the form's "Workflow" field) instead of a simple task.
* **"Voice Satellites" tab**: Lets you configure the ESP32 speakers connected to Athena.
* **"MCP Extensions" tab**: Lets you plug standard external plugins (e.g., GitHub connector, Home Assistant connector) into the AI.
* **"Diagnostics & System" tab**: Checks the health of the installation (database, STT, TTS). This is where the emergency **Restart the Voice engine (Kokoro)** button is located in case of audio bugs, as well as the **Backup & Restore** options for your entire environment.
* **"Workflows" tab**: Creates **deterministic pipelines** (chain of agents, "assembly line" type) as an alternative to autonomous mode — useful when you want a reproducible and auditable flow. See the dedicated section further below.
* **"Users" tab (Admin)**: If you are an administrator, you can here invite new people, manage their rights and their token quotas. You also **validate the automations** (workflows/routines) created by "user" accounts before they can run, you can **reset a 2FA** of an account (lost device), and consult the **audit log** (logins, password changes, validations…) via `GET /api/audit`.

---

## 5. 💻 Managing the Server (Administration Commands)

If you are the administrator of the machine hosting Athena, you have powerful system commands to manage the server lifecycle.

### 🍎 Linux & macOS
Open your Terminal. The main command is called `athena`.
- `athena start`: Powers up the AI in the background (SystemD / LaunchAgent process).
- `athena stop`: Shuts down the server cleanly.
- `athena restart`: Fully restarts the application.
- `athena status`: Checks whether the server is online.
- `athena logs`: Displays the server's technical log in real time. (Press `Ctrl+C` to quit).

**Update the software:**
Go to the source code folder and run: `./update.sh`

### 🪟 Windows (PowerShell)
Open PowerShell. The administration command ends with `.ps1`.
- `athena.ps1 start`: Starts the server in the background.
- `athena.ps1 stop`: Stops the server.
- `athena.ps1 restart`: Restarts the process.
- `athena.ps1 status`: Displays the status.
- `athena.ps1 logs`: Displays the orchestrator's technical console.

**Update the software:**
Go to the source code folder and run: `.\update.ps1`
