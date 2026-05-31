# 🎛️ Jarvis — Assistant Multi-Agent Auto-hébergé

Orchestrateur multi-agent auto-hébergé, accessible par **4 canaux** : **web** (bureau virtuel des agents), **CLI**, **Telegram** et **assistant vocal local**.

Moteur multi-fournisseurs (OpenAI, Anthropic, Gemini, Ollama, endpoints locaux vLLM/LM Studio…). Pensé pour la **maison** (domotique, routines, notifications) comme pour le **dev** (sandbox de code, MCP, recherche web). Le nom affiché est personnalisable via `APP_NAME`.

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
* **Garde-fous** : `max_turns`, budgets temps/tokens, retries LLM, validation JSON-schema + coercition des arguments d'outils, **cache TTL** des outils idempotents, **auto-continuation** des réponses tronquées (`finish_reason=length`).
* **Planification explicite** : Jarvis peut afficher un plan d'action suivi en direct (`make_plan` / `update_plan_step`) pour les tâches complexes.
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

* Déclencheurs : **quotidien** (HH:MM), **hebdomadaire** (jour + heure), **intervalle** (toutes les N min), ou **webhook entrant** (événement externe).
* **Webhooks** : une routine « webhook » s'appelle via `POST /api/hooks/{id}?token=<secret>` (exempté de l'auth admin, protégé par un secret ; le payload est injecté dans le prompt). Idéal pour qu'un événement **Home Assistant** déclenche un raisonnement IA.
* Gestion depuis l'UI : ⚙️ Réglages → **🗓️ Routines** (créer, activer/désactiver, exécuter maintenant, supprimer).

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

### 🛰️ Satellites ESP32-S3 (ESPHome) — directement sur Jarvis (sans HA)

Jarvis peut jouer le rôle de backend vocal des satellites **ESPHome** via l'API
native (`aioesphomeapi`) — HA est retiré de la boucle vocale (Jarvis appelle HA
seulement via les outils domotiques). Latence minimale : un seul aller-retour,
et **TTS phrase-par-phrase** en streaming.

1. Flashe l'ESP32-S3 avec `docs/esphome-satellite.yaml` (déclenchement **au bouton**,
   pour éviter le microWakeWord souvent capricieux ; wake word serveur possible ensuite).
2. `pip install -r requirements-voice.txt` (faster-whisper, aioesphomeapi) + Piper.
3. Copie `satellites.json.example` → `satellites.json` (IP + clé API de chaque ESP).
4. Lance le serveur, puis : `python3 esphome_satellites.py`.

> ⚠️ Ce backend ESPHome n'a pas pu être testé sans matériel : le séquencement des
> events et le sample rate audio (`VOICE_OUT_SAMPLE_RATE`) sont à ajuster sur ton ESP.

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
* **🗓️ Routines** — tâches planifiées + webhooks.
* **📚 Connaissances** — base RAG : lister/supprimer les documents indexés, ingérer une URL ou du texte.

**Pièces jointes** : le 📎 du chat injecte le contenu extrait d'un fichier (texte/code/PDF, OCR/**vision** pour les images) dans le message.

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
* **Multi-utilisateur** : comptes du foyer avec rôles (admin/user), gérés dans ⚙️ Réglages → Utilisateurs. Dès qu'un compte existe, connexion par identifiant obligatoire ; chaque utilisateur a sa conversation. `ADMIN_PASSWORD` = admin de secours.
* **Sauvegarde/restauration** de tout l'état en .zip (⚙️ Comportement) ; **PWA** installable (mobile/desktop).

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

L'installeur demande quels **composants optionnels** installer (vocal, transcription…) et configure l'essentiel du `.env` (fournisseur LLM, mot de passe admin).

**Linux / macOS** : `chmod +x install.sh && ./install.sh` *(crée la commande `jarvis start|stop|status|logs`, un raccourci bureau, détecte Ollama).*

**Windows** : `.\install.ps1` *(crée `run.bat`, la commande `jarvis.bat start|stop|cli` et un raccourci Bureau).*

**🐳 Docker Compose** *(auto-hébergement reproductible)* :
```bash
cp .env.example .env   # définir ADMIN_PASSWORD, clés LLM, et JARVIS_DATA=/chemin/absolu
docker compose up -d --build
```
> Tout l'état persiste sous `JARVIS_DATA` (monté au même chemin hôte/conteneur pour que la sandbox fonctionne). Le socket Docker est monté pour exécuter la sandbox en conteneurs frères.

Démarrage (la commande ouvre aussi l'UI dans le navigateur) :
* **Web** : `jarvis start` (Linux/macOS) · `jarvis.bat start` ou `run.bat` (Windows) · ou `python server.py` → 👉 **http://localhost:8000/**
* **CLI** : `python main.py` (commandes `/help`, `/doctor`, `/agents`…) · **Vocal** : `python voice_assistant.py`

---

## 🏆 Quota d'agents

Le `8` du cockpit est une recommandation **ergonomique** (lisibilité de l'Open Space). Le backend n'impose **aucune limite** : configurez autant d'agents que voulu dans `agents.yaml`.
