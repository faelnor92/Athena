# 🎛️ Athena — Framework Multi-Agente Self-Hosted

![Version](https://img.shields.io/badge/version-0.11.25-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)
![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)

**Lingue:** [Français](README.md) · [English](README.en.md) · [Español](README.es.md) · Italiano (questo file) · [Deutsch](README.de.md) · [中文](README.zh.md) · [日本語](README.ja.md)

Orchestratore IA "low-resource", ultra-modulare, progettato per girare su server leggeri o GPU modeste. Accessibile via **interfaccia web**, **CLI**, **Telegram** e **voce locale**.

📖 **[Leggi la Guida Utente completa](docs/USER_GUIDE.md)** per imparare a installare, configurare e usare Athena passo dopo passo.

## ✨ Funzionalità principali

### 🔐 Multi-Tenant Pro e Collaborazione
* **Sicurezza e SSO**: autenticazione OIDC / OAuth2 per le aziende. Registrazione su invito gestita dall'amministratore.
* **Cifratura a riposo**: conversazioni e tracce di esecuzione su database (SQLite) cifrate a riposo con Fernet (AES-128-CBC + HMAC-SHA256). La chiave resta sotto il tuo controllo (`.env` o secret manager esterno).
* **Controllo dei costi (quote)**: limite automatico della spesa API tramite quote giornaliere di token per utente.
* **Sicurezza avanzata**: protezione anti-SSRF (DNS rebinding) integrata per la navigazione web e mascheramento automatico dei segreti nei log.
* **Isolamento assoluto**: ogni utente ha la propria memoria (RAG, Core Memory), calendario, liste e budget API.
* **LLM self-service**: ogni utente può sovrascrivere i modelli globali con le proprie chiavi API (OpenAI, Anthropic, Gemini, Groq, ecc.).
* **Progetti condivisi**: spazi di lavoro collaborativi con ruoli granulari (Lettore / Editor) e blocco file anti-collisione.

### 🧠 Motore di orchestrazione e LLM
* **Multi-modello**: OpenAI, Anthropic, Gemini, Ollama, Groq, Mistral, Qwen, API locali compatibili.
* **Swarm (sciame)**: instradamento automatico tra agenti specializzati (handoff), esecuzione concorrente, dibattiti tra agenti.
* **Pipeline rigide (opzionale)**: forzare una catena di montaggio stretta in cui gli agenti si succedono in sequenza senza deviare.
* **Architettura modulare**: backend FastAPI suddiviso per router funzionali, basato su un database **SQLite** robusto e thread-safe.
* **Isolamento dei task**: stato isolato per esecuzione (ContextVars). Le richieste parallele non interferiscono mai.

### 🌐 Interfaccia web avanzata
* **Ufficio virtuale (isometrico 3D)**: visualizzazione dello sciame, agenti attivi evidenziati, animazioni di delega.
* **Cockpit e telemetria**: monitoraggio in tempo reale dei consumi (token, costi per utente), esecuzioni ed errori.
* **Osservabilità**: cronologia completa e pannello dei log in tempo reale per verificare le chiamate agli strumenti e il sistema.
* **Mini-IDE integrato**: esplora file **modificabile** — editing multi-scheda (CodeMirror), evidenziazione, autocompletamento, salvataggio Ctrl+S (sola lettura per i Lettori), pannello ridimensionabile e **live-reload** quando l'agente modifica un file aperto.
* **Strumenti integrati**: calendario, liste, terminale e galleria dei media generati.
* **Impostazioni no-code**: gestione completa del comportamento (routine, memoria, ruoli) tramite interfacce chiare.

### 🧰 Strumenti ed estensibilità (Skills)
* **Server MCP (Model Context Protocol)**: collega server esterni senza programmare. Il connettore Home Assistant MCP è incluso localmente per la massima sicurezza.
* **Computer Use (RPA 2.0)**: controllo di un browser headless interattivo ottimizzato per gli LLM.
* **Navigazione Git e codice**: comprensione dei tuoi repository (log, branch, editing), esecuzione bash/python via sandbox Docker.
* **Creazione di Skills al volo**: l'IA può *programmare i propri strumenti* e salvarli in modo permanente per ampliare le sue capacità!
* **Amministrazione SSH**: gestisci i tuoi server remoti tramite comandi SSH.
* **Creatività e web**: ricerca web approfondita, generazione di immagini/video (Fal, Replicate), scraping.
* **Media e riunioni**: riassunto e trascrizione di file audio o intere riunioni.

### 🎨 AthenaDesign Studio
* **Studio di design IA**: descrivi ciò che vuoi e Athena genera e **mostra l'anteprima in tempo reale** di interfacce **HTML/CSS/JS**, componenti **React/JSX**, diagrammi **Mermaid**, ed esegue **Python** (presentazioni PowerPoint, grafici Matplotlib/Plotly) in una **sandbox Docker** isolata.
* **Design System**: applica la tua identità (colori, tipografia) — manualmente, estraendo da un CSS, o **importando dall'URL di un sito**.
* **Import e visione**: allega immagini/documenti (PDF) o cattura una pagina web come riferimento; instradamento visione automatico (modello multimodale se disponibile, altrimenti degradazione elegante).
* **Iterazione**: annota l'anteprima, **slider WYSIWYG** (colore/raggio/font), versioni, **autocorrezione** degli script in errore, esportazione in **PDF/PPTX/HTML** e **condivisione tramite link** (sola lettura, in sandbox).
* **Progetti unificati**: un progetto Athena contiene sia il **codice** sia il **design**.

### 🔌 Plugin e autocorrezione
* **Scheda Plugin**: attiva estensioni first-class oltre ai server MCP e alle skill.
* **Plugin Claude Code**: delega la programmazione complessa all'agente **Claude Code** (CLI), limitato al progetto attivo; concesso automaticamente al Programmatore quando attivato.
* **Autocorrezione (self-healing)**: sia il design (Python) sia il **Programmatore** (Code-Test-Fix: `pytest`/`npm test`) correggono automaticamente i propri errori in un ciclo limitato.

### 🏠 Domotica e automazioni
* **Domotica nativa (Home Assistant)**: lettura dello stato ed esecuzione di azioni (luci, tapparelle, sensori) all'istante.
* **Consapevolezza spaziale**: sa in quale stanza ti trovi per indirizzare le azioni sul tuo ambiente fisico.
* **Routine proattive e workflow**: pianificazione CRON isolata per utente, trigger webhook, integrazioni avanzate con **n8n**.
* **Calendario e liste**: sincronizzazione bidirezionale con Google Calendar, iCal e CalDAV. Gestione di todo e liste della spesa.
* **Notifiche attive**: avvisi autonomi da Athena verso Telegram, Discord, Slack, email e webhook.

### 💾 Memoria e apprendimento
* **Database vettoriale RAG**: indicizzazione semantica automatica dei documenti via ChromaDB.
* **Knowledge Graph e Core Memory**: archiviazione di fatti duraturi e modellazione delle relazioni come grafi.
* **Auto-miglioramento**: feedback d'esperienza persistente dopo task complessi per affinare il comportamento futuro.
* **Backup e ripristino**: backup/restore completo dello stato (conversazioni, RAG, routine, configurazioni).

### 🎙️ Assistente vocale (STT/TTS)
* **100% locale e fluido**: sintesi vocale molto rapida con **Kokoro TTS** (API Docker locale) e trascrizione con **Whisper STT** ottimizzato.
* **Rilevamento parola di attivazione**: openWakeWord con supporto "barge-in" (interruzione della voce dell'IA).
* **Satelliti ESP32-S3**: connessione diretta di satelliti vocali ESPHome al framework (S2S), senza passare da Home Assistant.

## 🚀 Installazione rapida (1 riga)

> [!NOTE]
> *Se questo repository è privato, servono i diritti di accesso (token o chiave SSH) perché questi comandi funzionino, oppure puoi clonarlo manualmente.*

**Linux / macOS**: copia e incolla questo comando nel terminale:
```bash
curl -sSL https://raw.githubusercontent.com/faelnor92/Athena/main/install.sh | bash
```

**Windows**: esegui questo comando in PowerShell:
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/Athena/main/install.ps1 | iex
```

* **Alternativa Docker Compose**: `docker compose up -d --build`

**Avvio**: `athena start` o `python3 server.py`. Disponibile su 👉 **http://localhost:8000/**.

### ⚙️ Deployment multi-worker (scalabilità)
Lo stato mutabile condiviso (account e quote, sessioni auth, routine, inviti, progetti condivisi, config per utente) è salvato in un database SQLite comune in modalità WAL (`athena_state.sqlite3`) con aggiornamenti atomici — quindi **coerente tra più worker**:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```
> [!NOTE]
> **RAG in multi-worker.** In single-process il vector store è incorporato (ChromaDB locale). Per il multi-worker, imposta **`CHROMA_SERVER_HOST`** (+ `CHROMA_SERVER_PORT`): tutti i worker parlano con lo stesso server ChromaDB. Il `docker-compose.yml` incluso contiene già il servizio `chroma`. Il resto dello stato è multi-worker-safe in modo nativo.

### 🔒 Sicurezza in produzione
- **TLS obbligatorio**: metti Athena dietro un reverse proxy HTTPS (Caddy, Nginx, Traefik). Il server emette **HSTS** automaticamente quando rileva HTTPS (`X-Forwarded-Proto: https`).
- **Chiave di cifratura fuori da `.env`**: per resistere al furto di disco/backup, inietta `DB_ENCRYPTION_KEY` tramite variabile d'ambiente / secret manager.
- **Header di sicurezza** (CSP, X-Frame-Options, nosniff, Referrer/Permissions-Policy) attivi di default — `SECURITY_HEADERS=false` per disattivare, `CONTENT_SECURITY_POLICY` per personalizzare.
- **Salvaguardie**: throttle anti-brute-force (`LOGIN_MAX_FAILS`/`LOGIN_WINDOW_SECONDS`), rate limiting (`RATE_LIMIT_PER_MIN`, default 300/IP/min), policy password (`MIN_PASSWORD_LENGTH`, default 8), **audit log** (`GET /api/audit`, admin) e **approvazione admin** delle automazioni create da account "user".
- **RBAC per strumento**: `ADMIN_ONLY_TOOLS="execute_bash_command,run_ssh_command,..."` riserva l'esecuzione di codice/comandi agli admin.
- **Container**: l'immagine gira come utente **non-root** con `HEALTHCHECK`. Audit dell'installazione: `bash scripts/security_scan.sh`.

### 📡 Osservabilità LLM (opzionale — OpenInference / Phoenix)
Oltre al cockpit integrato, Athena può esportare **tracce LLM standardizzate** (OpenInference / OpenTelemetry) verso **Phoenix** (Arize). Attivazione:
```bash
pip install -r requirements-observability.txt
docker compose --profile observability up -d         # Phoenix (UI: http://localhost:6006)
```
poi in `.env`: `OPENINFERENCE_ENABLED=true` e `OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:6006/v1/traces`. Disattivato di default.

---

## 🛡️ Confronto: Athena vs il mercato

> [!NOTE]
> **Metodologia.** Confrontare il confrontabile: **Athena**, **Hermes** e **OpenClaw** sono *app/assistenti ospitati*; **CrewAI** e **AutoGen** sono *librerie di orchestrazione* da integrare nel proprio codice (da cui i "N/D"). Il differenziatore di Athena non è "avere una UI", ma **multi-tenancy + sicurezza enterprise + coding agentico + osservabilità** in un unico prodotto self-hosted.

| Categoria | Criterio | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Interfaccia e UX** | **Interfaccia grafica** | **Dashboard web completa (isometrica 3D, grafo nodale, terminale integrato)** | No | App companion + Live Canvas | No (CrewAI Studio a parte) | Base (AutoGen Studio) |
| | **Canali di interazione** | Web, Terminal UI, Telegram, Discord, Slack, Voce | CLI, Telegram, Slack, Discord | **15+ canali** | Codice Python | CLI / codice |
| | **Integrazione IDE / dev locale** | Console di codice web + Sandbox | No | Sì (assistente locale) | Si integra nel tuo codice | Si integra nel tuo codice |
| **Orchestrazione** | **Modello multi-agente** | **Swarm con routing semantico automatico** | Sub-agenti isolati paralleli | Routing multi-agente | Sequenziale / Gerarchico | Dibattiti / Group chat |
| | **Topologie di gruppo** | Dibattiti e handoff organici | Handoff isolati | Routing per canale/agente | Processo sequenziale/gerarchico | **Group chat avanzato** |
| | **Pipeline rigide** | Sì (catena di montaggio opzionale) | Organico | — | **Nativo** | Lineare o organico |
| | **Persistenza (memoria)** | **Vector DB + cronologia cifrata cross-sessione** | Sì (SQLite + FTS5) | Sì (sessioni persistenti) | Sì (breve/lungo termine) | Limitato |
| | **Apprendimento (closed-loop)** | **Skill auto-generate + RAG d'esperienza** | Sì | Strumenti estensibili | No | No |
| | **Strumenti e MCP** | **Nativi + MCP + Home Assistant** | Sì (MCP) | Sì (browser, canvas, cron, MCP) | Sì (crewai-tools + MCP) | Sì (function calling) |
| **Sicurezza globale** | **Autenticazione** | **Password, token, SSO (OIDC)** | No (locale) | Base (locale) | N/D | N/D |
| | **Controllo accessi (RBAC)** | **Sì (ruoli Lettore/Editor)** | No | No | N/D | N/D |
| | **Quote / costi per utente** | **Sì (quota token/giorno + avvisi)** | No | No | N/D | N/D |
| **Esecuzione e rete** | **Sandbox di esecuzione** | **Container Docker effimero (risorse limitate)** | Varia | Host | Via code interpreter | **Sì (Docker)** |
| | **Scudo anti-SSRF** | **Sì (DNS rebinding, blocco rete interna/metadati)** | No | No | N/D | N/D |
| **Protezione dati** | **Mascheramento segreti (log)** | **Sì** | No | Parziale | N/D | N/D |
| | **Cifratura a riposo** | **Sì (Fernet/AES-128)** | No | Dipende dallo storage | N/D | N/D |
| | **Isolamento multi-tenant** | **Sì (memoria/agenda/budget per utente)** | No | Per workspace | N/D | N/D |
| | **Approvazione umana (HITL)** | **Sì (azioni sensibili intercettate nella UI)** | Sì (via chat) | Base | Da implementare | Da implementare |

## 📄 Licenza

Distribuito con licenza **Apache 2.0** — vedi [LICENSE](LICENSE). Libero uso, modifica e ridistribuzione.
