# 🎛️ Jarvis v2 — Assistant Multi-Agent Auto-hébergé & Bureau Virtuel Immersif

Jarvis v2 est un écosystème d'orchestration multi-agent auto-hébergé, doté d'une interface web cyberpunk-néon (glassmorphism) avec un bureau virtuel 3D isométrique (« Swarm Open Space »).

Moteur d'agents multi-fournisseurs (OpenAI, Anthropic, Gemini, Ollama, endpoints locaux vLLM/LM Studio…), accessible par **4 canaux** : **web**, **CLI**, **Telegram** et **assistant vocal local**. Pensé pour un usage **maison** (domotique, routines, notifications) comme **dev** (sandbox de code, MCP, web).

---

## 🌟 Interface Web

* **Swarm Open Space (3D isométrique)** : chaque agent a son bureau ; l'agent actif est **surligné** (halo coloré, agrandissement) et une **enveloppe « DÉLÉGATION »** vole d'un bureau à l'autre lors d'un transfert.
* **Cockpit de télémétrie** : tokens, coût €, quota d'agents, **compétences (skills) créées** (avec suppression), galerie d'images/vidéos générées.
* **Chat en streaming** : réponses et étapes de l'essaim affichées **au fil de l'eau** (SSE), bouton **Stop** qui annule le run côté serveur.
* **Explorateur de fichiers** (coloration PrismJS), **agenda**, **listes**, **arbre de conversations** non-linéaire.
* **Réglages no-code** (⚙️) — voir [Réglages depuis l'UI](#️-réglages-depuis-lui).

---

## 🧠 Moteur d'Orchestration

Basé sur [LiteLLM](https://github.com/BerriAI/litellm) (routage transparent vers n'importe quel LLM) :

* **Handoffs & sous-agents** : Jarvis route vers les spécialistes (transferts), les interroge via `query_agent`, ou lance un débat (`debate_between_agents`).
* **Exécution parallèle** : plusieurs outils/sous-agents d'un même tour s'exécutent **concurremment** (ordre préservé, handoffs séquentiels) — plafond `SWARM_MAX_PARALLEL`.
* **Garde-fous** : `max_turns`, budgets temps/tokens (`SWARM_MAX_SECONDS`/`SWARM_MAX_TOKENS`), retries LLM (`LLM_MAX_RETRIES`), validation/coercition des arguments d'outils selon le schéma JSON.
* **Human-in-the-loop** : les outils sensibles (shell, SSH, domotique, suppressions) exigent une confirmation, sauf canal de confiance.
* **État isolé par run** (ContextVar + registry) → web + Telegram + sous-agents parallèles ne s'écrasent plus.
* **Détection auto de l'OS** : Jarvis sait s'il tourne sur Linux/Windows/macOS (ou dans la sandbox Docker) et génère les bonnes commandes.

---

## 🧰 Capacités des agents (outils)

* **Internet** : `web_search` (DuckDuckGo) + `web_scrape` — exécutés côté serveur, donc utilisables même par de petits modèles (via tool-calls).
* **Code & commandes** : exécution **isolée en sandbox Docker** (cf. ci-dessous).
* **Images / vidéos** : génération (pollinations, Stability, Fal, Replicate, endpoints custom).
* **Domotique** : Home Assistant (`get_ha_state`, `call_ha_service`).
* **Agenda & listes** : événements, tâches, synchro CalDAV / iCal / Google.
* **Mémoire** : `memorize_fact`, `store_document`, `search_memory`, `ingest_file` (RAG).
* **Notifications** : `send_notification` → Discord/Slack/email/Telegram/webhook.
* **Compétences dynamiques (skills)** : les agents créent des outils Python persistants (`skills/*.py`), chargés à chaud et **gérables/supprimables depuis l'UI**.
* **MCP** : n'importe quel serveur MCP ajoute ses outils (voir ci-dessous).

## 🧩 Serveurs MCP (Model Context Protocol)

Branchez n'importe quel serveur MCP (filesystem, GitHub, Postgres, HTTP/SSE…) — ses outils deviennent disponibles pour les agents, **sans recoder**.

* Format compatible Claude Desktop (`mcp_servers.json`, cf. `.example`).
* **Gestion depuis l'UI** : ⚙️ Réglages → **🧩 Serveurs MCP** (éditeur JSON, état des serveurs/outils connectés, **reconnexion à chaud**).
* Robuste : un serveur en panne est ignoré sans crasher l'agent. Serveurs « sensibles » (FS/shell) non démarrés si aucun `ADMIN_PASSWORD`.

## 🛡️ Sandbox d'exécution

Code & commandes **isolés dans un conteneur Docker jetable** : réseau coupé, RAM/CPU/PID bornés, racine en lecture seule, sans privilèges, seul le workspace monté en écriture. Nécessite **Docker**.

* `SANDBOX_MODE=off` : repli local non isolé (à vos risques).
* `SANDBOX_ALLOW_NETWORK=true` : autorise le réseau **dans** la sandbox (pour du code qui doit sortir).
* Par défaut, l'espace de travail des agents est confiné au sous-dossier **`workspace/`** (le code source et le `.env` ne sont pas exposés).

## 🧠 Mémoire

* **RAG** vectoriel [ChromaDB](https://www.trychroma.com/) (recherche sémantique automatique).
* **Mémoire « core »** clé-valeur (faits/préférences).
* **Auto-amélioration** : après une tâche, un retour d'expérience est archivé et resservi (`SELF_IMPROVE`).
* **Compaction de contexte** : au-delà de `MEMORY_MAX_MESSAGES`, l'historique ancien est résumé (vue LLM seulement).

## 🔭 Observabilité

* **Runs persistés** en **SQLite** (`run_id`, étapes, tokens, coût, durée, statut) — réussis **et** ratés.
* **Rejeu & éval** : `POST /api/runs/{id}/replay`, CLI `eval_runner.py` (`evals/cases.json`).
* **Logging structuré** : niveaux + rotation (`logs/jarvis.log`, `LOG_LEVEL`).

---

## 📡 Canaux & Sessions

| Canal | Accès | Particularités |
|-------|-------|----------------|
| **Web** | `http://localhost:8000` | Cockpit, streaming, arbre de conversation |
| **CLI** | `python3 main.py` | Dialogue terminal, canal de confiance |
| **Telegram** | `TELEGRAM_BOT_TOKEN` | Shell/SSH désactivés par défaut |
| **Vocal** | `python3 voice_assistant.py` | STT/TTS local, wake word, barge-in, canal de confiance |

* **Sessions par canal** : chaque canal (`client_id`) a sa propre conversation isolée.
* **Permissions par canal** : `auto_approve` + allow/deny d'outils (`channel_policies.json`, cf. `.example`).
* **Streaming SSE** : `POST /api/chat/stream` (events `run`/`step`/`done`/`error`).
* **Annulation** : `POST /api/runs/{id}/cancel`.

## 🗓️ Routines proactives / planifiées

Déclenchez automatiquement une tâche d'agent (briefing matinal, veille web, rappels). Le résultat est persisté et **notifié** sur vos messageries.

* Déclencheurs : **quotidien** (HH:MM), **hebdomadaire** (jour + heure), **intervalle** (toutes les N min).
* Gestion depuis l'UI : ⚙️ Réglages → **🗓️ Routines** (créer, activer/désactiver, exécuter maintenant, supprimer).
* API : `GET/POST/DELETE /api/routines`, `POST /api/routines/{id}/run`.

## 📣 Notifications multi-canaux

Une couche unique diffuse vers tous les canaux configurés (via `.env`) :

* **Discord** / **Slack** (webhooks), **webhook générique** (POST JSON), **Telegram** (chat_id), **email** (SMTP).
* Utilisée par les routines, l'agenda, et l'outil agent `send_notification`.

## 🎙️ Assistant vocal local

Pipeline 100 % local : `voice/` — STT [faster-whisper], TTS [Piper] (repli pyttsx3), wake word [openWakeWord/Porcupine], VAD par énergie, **barge-in** (reprendre la parole interrompt Jarvis et annule le run).

```bash
pip install -r requirements-voice.txt   # + binaire Piper et un modèle .onnx
python3 server.py                        # serveur (un terminal)
python3 voice_assistant.py               # assistant vocal (un autre)
```
Configuration via les variables `VOICE_*` (voir `.env.example`).

---

## ⚙️ Réglages depuis l'UI

Bouton ⚙️ → modale à onglets :

* **👤 Agents** — créer/éditer/supprimer des agents.
* **🔑 Clés API & Connexions** — clés LLM, image/vidéo, Home Assistant, messageries.
* **🖥️ Terminal & Sécurité** — SSH, mot de passe admin.
* **📅 Agenda** — CalDAV / iCal / Google.
* **💰 Tarifs LLM** — coût €/M tokens par modèle (alimente le cockpit).
* **⚙️ Comportement & Sécurité** — sandbox, auto-amélioration, retries, parallélisme, budgets, auto-approbation des outils sensibles, HOST/PORT, dossier de travail, mémoire.
* **🧩 Serveurs MCP** — éditeur + reconnexion à chaud.
* **🗓️ Routines** — tâches planifiées.

> La sauvegarde met à jour le `.env` **à chaud en préservant les commentaires**.

---

## 🌍 Multi-plateforme

Fonctionne sur **Linux**, **macOS** et **Windows** :

* La sandbox Docker tourne sous Linux **quel que soit l'hôte** (commandes portables).
* En repli local (sans Docker), le shell est choisi selon l'OS (PowerShell sur Windows, bash/zsh sinon).
* `GET /api/platform` expose l'OS détecté.
* Scripts d'install dédiés : `install.sh` (Linux/macOS), `install.ps1` (Windows).

---

## 🔐 Sécurité & Configuration

* **Copiez `.env.example` → `.env`** et renseignez vos valeurs (`.env` est git-ignoré).
* **Exposition réseau** : sur `0.0.0.0` (défaut), `ADMIN_PASSWORD` devient **obligatoire** (sinon refus de démarrer). Usage local : `HOST=127.0.0.1`. Production : derrière un **reverse-proxy HTTPS**.
* **Secrets jamais committés** : `.env`, `mcp_servers.json`, `channel_policies.json`, `conversations*.json`, logs, `*.sqlite3` (couverts par `.gitignore`).
* **SSH** : vérification des clés d'hôte connues (anti-MITM) + échappement `shlex`.
* **Workspace confiné** à `workspace/` par défaut (le `.env`/source ne sont pas lisibles via l'explorateur).

Toutes les variables sont documentées dans **`.env.example`**.

---

## 🧪 API (extrait)

| Endpoint | Rôle |
|---|---|
| `POST /api/chat` · `POST /api/chat/stream` | Chat (bloquant / streaming SSE) |
| `GET /api/chat/status` | Étapes live d'un run |
| `GET /api/runs` · `GET /api/runs/{id}` | Observabilité |
| `POST /api/runs/{id}/cancel` · `/replay` | Annuler / rejouer |
| `GET/POST /api/config/mcp` | Config MCP + reconnexion |
| `GET/POST/DELETE /api/routines` · `/{id}/run` | Routines |
| `GET/POST /api/config/env` | Variables d'environnement |
| `GET /api/config/skills` · `DELETE …/{name}` | Compétences |
| `GET /api/platform` | OS détecté |

---

## 🛠️ Architecture & dépendances

* **Backend / API** : [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) (swarm exécuté dans des threads → concurrence réelle).
* **Agents** : [LiteLLM](https://github.com/BerriAI/litellm) + MCP.
* **Mémoire** : [ChromaDB](https://www.trychroma.com/). **Isolation** : Docker. **Vocal** : faster-whisper, Piper, openWakeWord, sounddevice.

```bash
pip install -r requirements.txt          # cœur applicatif (+ MCP)
pip install -r requirements-voice.txt    # optionnel : assistant vocal
# Docker requis pour la sandbox d'exécution de code/commande.
```

> Reprendre le dev sur un autre poste : voir **`SETUP.md`** (clone, deps, `.env`, état local non versionné).

### Tests
```bash
for t in tests/test_*.py; do python3 "$t"; done
# swarm, garde-fous, approbations, canaux, mémoire, éval, run_context, voice imports
```

---

## 🚀 Installation & démarrage

**Linux / macOS** : `chmod +x install.sh && ./install.sh` *(installe la commande `jarvis start|stop|status|logs`, lanceurs de bureau, service de fond, détecte Ollama).*

**Windows** : `.\install.ps1` *(raccourci Bureau, `run.bat`, scan Ollama).*

Puis renseignez votre clé LLM dans `.env`, et lancez :
* Web : `jarvis start` ou `python3 server.py` → 👉 **http://localhost:8000/**
* CLI : `python3 main.py` · Vocal : `python3 voice_assistant.py`

---

## 🏆 Quota d'agents

Le `8` du cockpit est une recommandation **ergonomique** (lisibilité de l'Open Space). Le backend n'impose **aucune limite** : configurez autant d'agents que voulu dans `agents.yaml`.
