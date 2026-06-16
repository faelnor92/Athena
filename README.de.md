# 🎛️ Athena — Selbst-gehostetes Multi-Agenten-Framework

![Version](https://img.shields.io/badge/version-0.12.8-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)
![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)

**Sprachen:** [Français](README.md) · [English](README.en.md) · [Español](README.es.md) · [Italiano](README.it.md) · Deutsch (diese Datei) · [中文](README.zh.md) · [日本語](README.ja.md)

Ein „ressourcenschonender", hochmodularer KI-Orchestrator, ausgelegt für den Betrieb auf leichten Servern oder bescheidenen GPUs. Zugänglich über **Web-UI**, **CLI**, **Telegram** und **lokale Sprache**.

📖 **[Lies das vollständige Benutzerhandbuch](docs/USER_GUIDE.md)**, um Athena Schritt für Schritt zu installieren, zu konfigurieren und zu nutzen.

## ✨ Hauptfunktionen

### 🔐 Multi-Tenant Pro & Zusammenarbeit
* **Sicherheit & SSO**: OIDC-/OAuth2-Authentifizierung für Unternehmen. Vom Administrator verwaltete Registrierung per Einladung.
* **Verschlüsselung im Ruhezustand**: In der Datenbank (SQLite) gespeicherte Konversationen und Ausführungs-Traces werden im Ruhezustand mit Fernet (AES-128-CBC + HMAC-SHA256) verschlüsselt. Der Schlüssel bleibt unter deiner Kontrolle (`.env` oder externer Secret-Manager).
* **Kostenkontrolle (Quoten)**: automatische Begrenzung der API-Ausgaben über tägliche Token-Quoten pro Nutzer.
* **Erweiterte Sicherheit**: integrierter Anti-SSRF-Schutz (DNS-Rebinding) fürs Web-Browsing und automatische Maskierung von Geheimnissen in den Logs.
* **Absolute Isolation**: Jeder Nutzer hat seinen eigenen Speicher (RAG, Core Memory), Kalender, Listen und sein API-Budget.
* **Self-Service-LLM**: Jeder Nutzer kann die globalen Modelle mit eigenen API-Schlüsseln überschreiben (OpenAI, Anthropic, Gemini, Groq usw.).
* **Geteilte Projekte**: kollaborative Workspaces mit feingranularen Rollen (Leser / Editor) und kollisionssicherer Dateisperre.

### 🧠 Orchestrierungs- & LLM-Engine
* **Multi-Modell**: OpenAI, Anthropic, Gemini, Ollama, Groq, Mistral, Qwen, kompatible lokale APIs.
* **Swarm**: automatisches Routing zwischen spezialisierten Agenten (Handoffs), nebenläufige Ausführung, Debatten zwischen Agenten.
* **Starre Pipelines (optional)**: erzwingt eine strikte Fließband-Kette, in der Agenten ohne Abweichung nacheinander arbeiten.
* **Modulare Architektur**: FastAPI-Backend, nach funktionalen Routern aufgeteilt, gestützt auf eine robuste, thread-sichere **SQLite**-Datenbank.
* **Task-Isolation**: pro Ausführung isolierter Zustand (ContextVars). Parallele Anfragen stören sich nie.

### 🌐 Erweiterte Web-Oberfläche
* **Virtuelles Büro (3D-isometrisch)**: Visualisierung des Schwarms, hervorgehobene aktive Agenten, Delegations-Animationen.
* **Cockpit & Telemetrie**: Live-Verfolgung des Verbrauchs (Token, Kosten pro Nutzer), Ausführungen und Fehler.
* **Observability**: vollständige Historie und Echtzeit-Log-Panel zur Prüfung von Tool-Aufrufen und System.
* **Integriertes Mini-IDE**: **editierbarer** Datei-Explorer — Mehr-Tab-Bearbeitung (CodeMirror), Highlighting, Autovervollständigung, Speichern mit Strg+S (schreibgeschützt für Leser), größenveränderbares Panel und **Live-Reload**, wenn der Agent eine offene Datei ändert.
* **Integrierte Tools**: Kalender, Listen, Terminal und Galerie generierter Medien.
* **No-Code-Einstellungen**: vollständige Verwaltung des Verhaltens (Routinen, Speicher, Rollen) über klare Oberflächen.

### 🧰 Tools & Erweiterbarkeit (Skills)
* **MCP-Server (Model Context Protocol)**: externe Server ohne Programmierung anbinden. Der Home-Assistant-MCP-Connector ist lokal mitgeliefert für maximale Sicherheit.
* **Computer Use (RPA 2.0)**: Steuerung eines interaktiven Headless-Browsers, optimiert für LLMs.
* **Git- & Code-Navigation**: Verständnis deiner Repos (Logs, Branches, Bearbeitung), Bash-/Python-Ausführung über Docker-Sandbox.
* **Skill-Erstellung zur Laufzeit**: Die KI kann *eigene Tools programmieren* und dauerhaft speichern, um ihre Fähigkeiten zu erweitern!
* **SSH-Administration**: Verwalte deine Remote-Server per SSH-Befehlen.
* **Kreativität & Web**: tiefe Websuche, Bild-/Videogenerierung (Fal, Replicate), Scraping.
* **Medien & Meetings**: Zusammenfassen und Transkribieren von Audiodateien oder ganzen Meetings.

### 🎨 AthenaDesign Studio
* **KI-Design-Studio**: Beschreibe, was du willst, und Athena erzeugt und **zeigt live** **HTML/CSS/JS**-Oberflächen, **React/JSX**-Komponenten, **Mermaid**-Diagramme und führt **Python** aus (PowerPoint-Präsentationen, Matplotlib/Plotly-Grafiken) in einer isolierten **Docker-Sandbox**.
* **Design System**: wende deine Marke an (Farben, Typografie) — manuell, durch Extraktion aus CSS oder per **Import von der URL einer Website**.
* **Importe & Vision**: hänge Bilder/Dokumente (PDF) an oder erfasse eine Webseite als Referenz; automatisches Vision-Routing (multimodales Modell falls verfügbar, sonst sauberer Fallback).
* **Iteration**: Vorschau annotieren, **WYSIWYG-Schieberegler** (Farbe/Radius/Schrift), Versionen, **Auto-Korrektur** fehlerhafter Skripte, Export nach **PDF/PPTX/HTML** und **Teilen per Link** (schreibgeschützt, sandboxed).
* **Vereinheitlichte Projekte**: Ein Athena-Projekt enthält sowohl **Code** als auch **Design**.

### 🔌 Plugins & Auto-Korrektur
* **Plugins-Tab**: aktiviere First-Class-Erweiterungen zusätzlich zu MCP-Servern und Skills.
* **Claude-Code-Plugin**: delegiere aufwendiges Coding an den **Claude-Code**-Agenten (CLI), beschränkt auf das aktive Projekt; wird dem Coder bei Aktivierung automatisch zugewiesen.
* **Auto-Korrektur (Self-Healing)**: sowohl das Design (Python) als auch der **Coder** (Code-Test-Fix: `pytest`/`npm test`) korrigieren ihre Fehler automatisch in einer begrenzten Schleife.

### 🏠 Hausautomation & Automatisierungen
* **Native Hausautomation (Home Assistant)**: Zustand lesen und Aktionen ausführen (Licht, Rollläden, Sensoren) — sofort.
* **Räumliches Bewusstsein**: weiß, in welchem Raum du bist, um Aktionen auf deine physische Umgebung zu richten.
* **Proaktive Routinen & Workflows**: pro Nutzer isolierte CRON-Planung, Webhook-Trigger, tiefe **n8n**-Integrationen.
* **Kalender & Listen**: bidirektionale Synchronisation mit Google Calendar, iCal und CalDAV. Todos und Einkaufslisten verwalten.
* **Aktive Benachrichtigungen**: autonome Hinweise von Athena an Telegram, Discord, Slack, E-Mail und Webhooks.

### 💾 Speicher & Lernen
* **RAG-Vektordatenbank**: automatische semantische Indizierung von Dokumenten via ChromaDB.
* **Knowledge Graph & Core Memory**: Speichern dauerhafter Fakten und Modellierung von Beziehungen als Graphen.
* **Selbstverbesserung**: persistentes Erfahrungs-Feedback nach komplexen Aufgaben zur Verfeinerung des künftigen Verhaltens.
* **Backup & Restore**: vollständiges Sichern/Wiederherstellen des Zustands (Konversationen, RAG, Routinen, Konfigurationen).

### 🎙️ Sprachassistent (STT/TTS)
* **100% lokal & flüssig**: sehr schnelle Sprachsynthese via **Kokoro TTS** (lokale Docker-API) und Transkription via optimiertem **Whisper STT**.
* **Wake-Word-Erkennung**: openWakeWord mit „Barge-in"-Unterstützung (Unterbrechen der KI-Sprache).
* **ESP32-S3-Satelliten**: direkte Anbindung von ESPHome-Sprachsatelliten an das Framework (S2S), ohne Umweg über Home Assistant.

## 🚀 Schnellinstallation (1 Zeile)

> [!NOTE]
> *Wenn dieses Repository privat ist, brauchst du Zugriffsrechte (Token oder SSH-Schlüssel), damit diese Befehle funktionieren — oder du klonst es manuell.*

**Linux / macOS**: Kopiere diesen Befehl in dein Terminal:
```bash
curl -sSL https://raw.githubusercontent.com/faelnor92/Athena/main/install.sh | bash
```

**Windows**: Führe diesen Befehl in PowerShell aus:
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/Athena/main/install.ps1 | iex
```

* **Docker-Compose-Alternative**: `docker compose up -d --build`

**Start**: `athena start` oder `python3 server.py`. Erreichbar unter 👉 **http://localhost:8000/**.

### ⚙️ Multi-Worker-Deployment (Skalierung)
Der gemeinsame veränderliche Zustand (Konten & Quoten, Auth-Sitzungen, Routinen, Einladungen, geteilte Projekte, Konfig pro Nutzer) liegt in einer gemeinsamen SQLite-DB im WAL-Modus (`athena_state.sqlite3`) mit atomaren Updates — also **konsistent über mehrere Worker**:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```
> [!NOTE]
> **RAG im Multi-Worker.** Im Single-Process ist der Vektorspeicher eingebettet (lokales ChromaDB). Für Multi-Worker setze **`CHROMA_SERVER_HOST`** (+ `CHROMA_SERVER_PORT`): alle Worker sprechen denselben ChromaDB-Server an. Das mitgelieferte `docker-compose.yml` enthält bereits den `chroma`-Dienst. Der restliche Zustand ist nativ multi-worker-sicher.

### 🔒 Sicherheit in der Produktion
- **TLS verpflichtend**: betreibe Athena hinter einem HTTPS-Reverse-Proxy (Caddy, Nginx, Traefik). Der Server sendet automatisch **HSTS**, wenn HTTPS erkannt wird (`X-Forwarded-Proto: https`).
- **Verschlüsselungsschlüssel außerhalb von `.env`**: gegen Disk-/Backup-Diebstahl injiziere `DB_ENCRYPTION_KEY` über Umgebungsvariable / Secret-Manager.
- **Sicherheits-Header** (CSP, X-Frame-Options, nosniff, Referrer/Permissions-Policy) standardmäßig aktiv — `SECURITY_HEADERS=false` zum Deaktivieren, `CONTENT_SECURITY_POLICY` zum Anpassen.
- **Schutzmaßnahmen**: Anti-Brute-Force-Throttle (`LOGIN_MAX_FAILS`/`LOGIN_WINDOW_SECONDS`), Rate Limiting (`RATE_LIMIT_PER_MIN`, Standard 300/IP/min), Passwort-Policy (`MIN_PASSWORD_LENGTH`, Standard 8), **Audit-Log** (`GET /api/audit`, Admin) und **Admin-Freigabe** von Automatisierungen, die „user"-Konten erstellen.
- **Pro-Tool-RBAC**: `ADMIN_ONLY_TOOLS="execute_bash_command,run_ssh_command,..."` beschränkt Code-/Befehlsausführung auf Admins.
- **Container**: das Image läuft als **Non-Root**-Nutzer mit `HEALTHCHECK`. Installations-Audit: `bash scripts/security_scan.sh`.

### 📡 LLM-Observability (optional — OpenInference / Phoenix)
Zusätzlich zum integrierten Cockpit kann Athena **standardisierte LLM-Traces** (OpenInference / OpenTelemetry) an **Phoenix** (Arize) exportieren. Aktivierung:
```bash
pip install -r requirements-observability.txt
docker compose --profile observability up -d         # Phoenix (UI: http://localhost:6006)
```
dann in `.env`: `OPENINFERENCE_ENABLED=true` und `OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:6006/v1/traces`. Standardmäßig deaktiviert.

---

## 🛡️ Vergleich: Athena vs. der Markt

> [!NOTE]
> **Methodik.** Vergleichbares vergleichen: **Athena**, **Hermes** und **OpenClaw** sind *gehostete Apps/Assistenten*; **CrewAI** und **AutoGen** sind *Orchestrierungs-Bibliotheken*, die man in eigenen Code integriert (daher „N/V"). Athenas Differenzierung ist nicht „eine UI haben", sondern **Multi-Tenancy + Sicherheit auf Enterprise-Niveau + agentisches Coding + Observability** in einem einzigen selbst-gehosteten Produkt.

| Kategorie | Kriterium | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Oberfläche & UX** | **Grafische Oberfläche** | **Vollständiges Web-Dashboard (3D-isometrisch, Knotengraph, integriertes Terminal)** | Nein | Companion-Apps + Live Canvas | Nein (separates CrewAI Studio) | Basic (AutoGen Studio) |
| | **Interaktionskanäle** | Web, Terminal-UI, Telegram, Discord, Slack, Sprache | CLI, Telegram, Slack, Discord | **15+ Kanäle** | Python-Code | CLI / Code |
| | **IDE-/Lokal-Dev-Integration** | Web-Code-Konsole + Sandbox | Nein | Ja (lokaler Assistent) | In eigenen Code integriert | In eigenen Code integriert |
| **Orchestrierung** | **Multi-Agenten-Modell** | **Swarm mit automatischem semantischem Routing** | Parallele isolierte Sub-Agenten | Multi-Agenten-Routing | Sequenziell / Hierarchisch | Debatten / Group Chat |
| | **Gruppen-Topologien** | Organische Debatten und Handoffs | Isolierte Handoffs | Routing pro Kanal/Agent | Sequenzieller/hierarchischer Prozess | **Fortgeschrittener Group Chat** |
| | **Starre Pipelines** | Ja (optionales Fließband) | Organisch | — | **Nativ** | Linear oder organisch |
| | **Persistenz (Speicher)** | **Vektor-DB + verschlüsselte sitzungsübergreifende Historie** | Ja (SQLite + FTS5) | Ja (persistente Sitzungen) | Ja (Kurz-/Langzeit) | Begrenzt |
| | **Lernen (Closed-Loop)** | **Auto-generierte Skills + Erfahrungs-RAG** | Ja | Erweiterbare Tools | Nein | Nein |
| | **Tools & MCP** | **Nativ + MCP + Home Assistant** | Ja (MCP) | Ja (Browser, Canvas, Cron, MCP) | Ja (crewai-tools + MCP) | Ja (Function Calling) |
| **Globale Sicherheit** | **Authentifizierung** | **Passwort, Tokens, SSO (OIDC)** | Nein (lokal) | Basic (lokal) | N/V | N/V |
| | **Zugriffskontrolle (RBAC)** | **Ja (Rollen Leser/Editor)** | Nein | Nein | N/V | N/V |
| | **Quoten / Kosten pro Nutzer** | **Ja (Token-Quote/Tag + Alerts)** | Nein | Nein | N/V | N/V |
| **Ausführung & Netzwerk** | **Ausführungs-Sandbox** | **Kurzlebiger Docker-Container (begrenzte Ressourcen)** | Variiert | Host | Via Code-Interpreter | **Ja (Docker)** |
| | **Anti-SSRF-Schutz** | **Ja (DNS-Rebinding, internes Netz/Metadaten geblockt)** | Nein | Nein | N/V | N/V |
| **Datenschutz** | **Geheimnis-Maskierung (Logs)** | **Ja** | Nein | Teilweise | N/V | N/V |
| | **Verschlüsselung im Ruhezustand** | **Ja (Fernet/AES-128)** | Nein | Vom Speicher abhängig | N/V | N/V |
| | **Multi-Tenant-Isolation** | **Ja (Speicher/Kalender/Budget pro Nutzer)** | Nein | Pro Workspace | N/V | N/V |
| | **Menschliche Freigabe (HITL)** | **Ja (sensible Aktionen in der UI abgefangen)** | Ja (via Chat) | Basic | Selbst bauen | Selbst bauen |

## 📄 Lizenz

Vertrieben unter der **Apache 2.0**-Lizenz — siehe [LICENSE](LICENSE). Freie Nutzung, Änderung und Weiterverbreitung.
