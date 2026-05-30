# 🎛️ Jarvis v2 - Dashboard Multi-Agent & Bureau Virtuel Immersif

Jarvis v2 est un écosystème d'orchestration multi-agent intelligent, doté d'une interface web cyberpunk-neon dépolie (glassmorphism) et d'un bureau virtuel en 3D isométrique ("Swarm Open Space").

Ce projet associe la puissance d'un moteur d'agents autonome multi-fournisseurs (OpenAI, Anthropic, Gemini, Ollama, endpoints locaux type vLLM/LM Studio, etc.) à une interface utilisateur haut de gamme, et il est accessible par **trois canaux** : interface **web**, **CLI**, **Telegram** et **assistant vocal local**.

---

## 🌟 Fonctionnalités Majeures (Interface)

### 1. 💬 Swarm Open Space (Bureau Virtuel 3D Isométrique)
*   **Visualisation Temps Réel** : Tous les agents actifs de votre essaim disposent de leur propre bureau physique modélisé en perspective isométrique.
*   **Sprites Cyber-Néon Haute Fidélité** : Des personnages vectoriels détaillés avec des attributs uniques (Jarvis le robot écran, Robert le développeur à lunettes matricielles, Émilie l'auteur avec son chevalet de peinture, Sofia la traductrice, Marc le correcteur, et Lucas le community manager).
*   **Mouvements & Animations Réactives** : Les agents se déplacent de bureau en bureau pour interagir.
*   **Animations de Délégation** : Lorsqu'un agent délègue son travail à un autre (ex: `Jarvis` ➔ `Codeur`), une enveloppe vole en temps réel entre leurs bureaux.

### 2. 📊 Cockpit de Télémétrie Cyberpunk
*   **Indicateurs Live** : Jetons consommés, estimation du coût en Euros, quota d'agents, compteurs d'états dynamiques.
*   **Galerie Médias Premium** : Images et vidéos générées par les agents, avec téléchargement rapide.

### 3. 📁 Explorateur de Fichiers & Coloration Syntaxique (PrismJS)
### 4. 📋 Liste de Tâches & Agenda Connecté
### 5. 🌿 Arbre de Conversations Branché (historique non-linéaire, multi-branching)

---

## 🧠 Moteur d'Orchestration (Core)

Moteur multi-agent basé sur [LiteLLM](https://github.com/BerriAI/litellm) (routage transparent vers n'importe quel LLM), avec :

*   **Handoffs & sous-agents** : `Jarvis` route vers les spécialistes (transferts) ou les interroge via `query_agent` / organise des débats (`debate_between_agents`).
*   **Exécution parallèle** : plusieurs `query_agent` d'un même tour s'exécutent **concurremment** (ordre des résultats préservé, handoffs séquentiels). Plafond `SWARM_MAX_PARALLEL`.
*   **Garde-fous** : limite de tours (`max_turns`), budgets temps/tokens par run (`SWARM_MAX_SECONDS`, `SWARM_MAX_TOKENS`), retries LLM (`LLM_MAX_RETRIES`), validation/coercition des arguments d'outils selon le schéma JSON.
*   **Human-in-the-loop** : les outils sensibles (shell, SSH, domotique, suppressions) exigent une confirmation utilisateur, sauf sur un canal de confiance (cf. permissions par canal).
*   **Outils via schémas typés** : `function_to_schema` déduit les types JSON des annotations Python.

## 🧩 Support MCP (Model Context Protocol)

Les agents peuvent utiliser n'importe quel serveur MCP (filesystem, GitHub, Postgres, HTTP/SSE…) sans recoder d'outils.

1.  `pip install "mcp[cli]"` (déjà dans `requirements.txt`).
2.  Copiez `mcp_servers.json.example` → `mcp_servers.json` (format compatible Claude Desktop).
3.  Au démarrage, les serveurs sont connectés et leurs outils injectés dans l'essaim. Un serveur en panne est ignoré sans crasher l'agent. Les serveurs « sensibles » (filesystem/shell) ne démarrent pas si `ADMIN_PASSWORD` est vide.

## 🛡️ Sandbox d'exécution

L'exécution de code/commande est **isolée dans un conteneur Docker jetable** (réseau coupé, RAM/CPU/PID bornés, racine en lecture seule, sans privilèges, seul le workspace monté en écriture). Nécessite **Docker**. Repli local explicite via `SANDBOX_MODE=off` (non isolé — à vos risques).

## 🧠 Mémoire

*   **RAG** : mémoire vectorielle [ChromaDB](https://www.trychroma.com/) (recherche sémantique automatique en arrière-plan).
*   **Mémoire « core »** : faits/préférences clé-valeur (`memorize_fact`).
*   **Auto-amélioration** : après une tâche non triviale, un retour d'expérience est archivé et resservi via le RAG (`SELF_IMPROVE`).
*   **Compaction de contexte** : au-delà de `MEMORY_MAX_MESSAGES`, l'historique ancien est résumé (vue LLM uniquement).

## 🔭 Observabilité

*   **Runs persistés** : chaque requête reçoit un `run_id` sauvegardé en **SQLite** (étapes, tokens, coût, durée, statut). Endpoints `GET /api/runs`, `GET /api/runs/{id}`.
*   **Rejeu & éval** : `POST /api/runs/{id}/replay` et harnais `eval_runner.py` (cas dans `evals/cases.json`).
*   **Logging structuré** : niveaux + rotation (`logs/jarvis.log`, `LOG_LEVEL`).

---

## 📡 Canaux & Sessions

| Canal | Accès | Particularités |
|-------|-------|----------------|
| **Web** | `http://localhost:8000` | Cockpit complet, streaming, arbre de conversation |
| **CLI** | `python3 main.py` | Dialogue terminal, canal de confiance |
| **Telegram** | `TELEGRAM_BOT_TOKEN` | Shell/SSH désactivés par défaut |
| **Vocal** | `python3 voice_assistant.py` | STT/TTS local, wake word, canal de confiance |

*   **Sessions par canal** : chaque canal a sa propre conversation isolée (`client_id`).
*   **Permissions par canal** : politique `auto_approve` + listes allow/deny d'outils, configurables (`channel_policies.json`, cf. `channel_policies.example.json`).
*   **Streaming SSE** : `POST /api/chat/stream` diffuse les étapes au fil de l'eau (events `run`/`step`/`done`/`error`) — idéal pour le vocal (TTS progressif) et l'UI.
*   **Annulation** : `POST /api/runs/{id}/cancel` (barge-in / bouton stop).

### 🎙️ Assistant vocal local

Pipeline 100 % local : `voice/` (STT [faster-whisper], TTS [Piper] avec repli pyttsx3, wake word [openWakeWord/Porcupine], VAD par énergie).

```bash
pip install -r requirements-voice.txt   # + binaire Piper et un modèle .onnx
python3 server.py                        # serveur (dans un terminal)
python3 voice_assistant.py               # assistant vocal (dans un autre)
```

Configuration via les variables `VOICE_*` (voir `.env.example`).

---

## 🔐 Sécurité & Configuration

*   **Copiez `.env.example` → `.env`** et renseignez vos clés. Le fichier `.env` est ignoré par git.
*   **Exposition réseau** : si le serveur écoute sur `0.0.0.0` (défaut), `ADMIN_PASSWORD` devient **obligatoire** (le serveur refuse sinon de démarrer). Pour un usage local : `HOST=127.0.0.1`. En production, placez-le derrière un **reverse-proxy HTTPS**.
*   **Secrets** : ne committez jamais `.env`, `mcp_servers.json`, `conversations*.json`, logs, `*.sqlite3` (déjà couverts par `.gitignore`).
*   **SSH** : vérification des clés d'hôte connues (anti-MITM) ; commandes échappées (`shlex`).

Toutes les variables disponibles (LLM, sécurité, sandbox, garde-fous, mémoire, canaux, vocal…) sont documentées dans **`.env.example`**.

---

## 🛠️ Architecture & Technologies

*   **Backend / API** : [FastAPI](https://fastapi.tiangolo.com/) & [Uvicorn](https://www.uvicorn.org/), exécution asynchrone (swarm dans des threads → concurrence).
*   **Moteur d'Agents** : [LiteLLM](https://github.com/BerriAI/litellm) (multi-fournisseurs) + support MCP.
*   **Mémoire vectorielle** : [ChromaDB](https://www.trychroma.com/).
*   **Isolation** : Docker (sandbox de code/commande).
*   **Vocal** : faster-whisper, Piper, openWakeWord, sounddevice.

### Dépendances

```bash
pip install -r requirements.txt          # cœur applicatif (+ MCP)
pip install -r requirements-voice.txt    # optionnel : assistant vocal
# Docker requis pour la sandbox d'exécution de code/commande.
```

### Tests

```bash
python3 tests/test_swarm.py        # orchestration, max_turns, parallélisme, annulation
python3 tests/test_guardrails.py   # retries, budgets, coercition
python3 tests/test_approvals.py    # human-in-the-loop
python3 tests/test_channels.py     # permissions par canal
python3 tests/test_memory.py       # compaction de contexte
python3 tests/test_eval.py         # éval / rejeu
python3 tests/test_run_context.py  # isolation des runs concurrents
python3 tests/test_voice_imports.py
```

---

## 🚀 Installation & Déploiement Multi-Plateforme

Des scripts d'installation automatisés sont fournis.

### 🐧 Linux & 🍏 macOS

```bash
chmod +x install.sh
./install.sh
```
*Prépare l'environnement, déploie `.env`, installe la commande CLI `jarvis` (`start|stop|status|logs`), des lanceurs de bureau et un service d'arrière-plan. Détecte Ollama.*

### 🪟 Windows (PowerShell)

```powershell
.\install.ps1
```
*Crée un raccourci Bureau, des scripts `run.bat` / `launch.vbs`, et scanne les modèles Ollama.*

Renseignez ensuite votre clé API LLM dans le `.env` généré.

---

## 💻 Démarrage

*   **Linux/Mac (CLI)** : `jarvis start` *(arrêt : `jarvis stop`, logs : `jarvis logs`)* — ou directement `python3 server.py`.
*   **Windows** : double-cliquez sur `run.bat` ou le raccourci **Jarvis**.
*   **CLI interactif** : `python3 main.py`
*   **Vocal** : `python3 voice_assistant.py`

Interface web : 👉 **[http://localhost:8000/](http://localhost:8000/)**

---

## 🏆 Quota d'Agents

La valeur `8` dans le cockpit est une recommandation **ergonomique** du frontend (lisibilité de l'Open Space). Le backend n'impose **aucune limite** : configurez autant d'agents que voulu dans `agents.yaml`.
