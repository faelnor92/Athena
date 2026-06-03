# 🎛️ Athena — Framework Multi-Agent Auto-Hébergé

![Version](https://img.shields.io/badge/version-0.9.35-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)

Orchestrateur IA "Low-Resource" ultra-modulaire, pensé pour fonctionner sur des serveurs légers ou avec des GPU modestes. Accessible via **Interface Web**, **CLI**, **Telegram** et **Vocal Local**.

## ✨ Fonctionnalités Clés

### 🔐 Multi-Tenant Pro & Collaboration
* **Sécurité & SSO** : Support de l'authentification OIDC / OAuth2 pour l'entreprise. Système d'inscription par invitation géré par l'administrateur.
* **Isolation Absolue** : Chaque utilisateur dispose de sa propre mémoire (RAG, Core Memory), de son propre agenda, de ses listes et de son budget API.
* **Self-Service LLM** : Chaque utilisateur peut surcharger les modèles IA globaux avec ses propres clés API (OpenAI, Anthropic, Gemini, Groq, etc.).
* **Projets Partagés** : Création d'espaces de travail (Workspaces) collaboratifs avec gestion fine des rôles (Lecteur / Éditeur) et verrouillage anti-collision des fichiers.

### 🧠 Moteur d'Orchestration & LLM
* **Multi-Modèles** : OpenAI, Anthropic, Gemini, Ollama, Groq, Mistral, Qwen, APIs locales compatibles.
* **Swarm (Essaim)** : Routage automatique entre agents spécialisés (handoffs), exécution concurrente, débats inter-agents.
* **Architecture Modulaire** : Backend FastAPI découpé par routeurs fonctionnels, soutenu par une base de données **SQLite** robuste et thread-safe.
* **Isolation des Tâches** : État isolé par exécution (ContextVars). Plusieurs requêtes parallèles n'interfèrent jamais.

### 🌐 Interface Web Avancée
* **Bureau Virtuel (3D Isométrique)** : Visualisation de l'essaim, agents actifs surlignés, animations de délégation.
* **Cockpit & Télémétrie** : Suivi en direct de la consommation (tokens, coûts financiers par utilisateur), exécutions et erreurs.
* **Observabilité** : Historique complet et panneau de Logs en temps réel dans l'UI pour auditer les appels d'outils et le système.
* **Outils Intégrés** : Explorateur de fichiers collaboratif, agenda, listes, terminal, et galerie de médias générés.
* **Réglages No-Code** : Gestion complète du comportement (routines, mémoire, rôles) via des interfaces claires.

### 🧰 Outils & Extensibilité (Skills)
* **Serveurs MCP (Model Context Protocol)** : Branchez des serveurs externes sans coder. Le connecteur Home Assistant MCP est vendorisé localement pour une sécurité absolue.
* **Computer Use (RPA 2.0)** : Pilotage d'un navigateur interactif headless optimisé pour les LLMs.
* **Outils Natifs & Sûrs** : Outils natifs rapides (`get_time`, `get_weather`) et isolation de l'exécution bash/python via Sandbox Docker. Mode lecture-seule optionnel.
* **Capacités Multiples** : Recherche web, scraping, génération d'images/vidéos (Fal, Replicate).

### 🏠 Domotique & Automatisations
* **Home Assistant** : Lecture d'état et exécution d'actions domotiques de manière asynchrone et rapide.
* **Routines Proactives** : Planification de tâches (CRON) isolées par utilisateur, déclenchements webhooks.
* **Agenda & Listes** : Synchronisation bidirectionnelle Google Calendar, iCal et CalDAV (par utilisateur).
* **Notifications** : Alertes autonomes vers Telegram, Discord, Slack, Email et Webhooks.

### 💾 Mémoire & Apprentissage
* **Base Vectorielle RAG** : Indexation sémantique automatique de documents via ChromaDB.
* **Mémoire Sémantique** : Archivage de faits durables (Core Memory).
* **Auto-Amélioration** : Retour d'expérience persistant après une tâche complexe pour affiner le comportement futur.

### 🎙️ Assistant Vocal (STT/TTS)
* **100% Local & Fluide** : Synthèse vocale très haute vitesse via **Kokoro TTS** (API Docker locale avec redémarrage UI) et transcription via **Whisper STT** optimisé.
* **Détection de Mot-Clé (Wake Word)** : openWakeWord avec support du "barge-in" (interruption de la parole IA).
* **Satellites ESP32-S3** : Connexion directe de satellites vocaux ESPHome au framework (S2S), sans passer par Home Assistant.

## 🚀 Installation Rapide (1-Liner)

> [!NOTE]
> *Si ce dépôt est privé, vous devez disposer des droits d'accès (token ou clé SSH) pour que ces commandes fonctionnent, ou vous pouvez cloner manuellement le dépôt.*

**Linux / macOS** : Copiez et collez cette commande dans votre terminal :
```bash
curl -sSL https://raw.githubusercontent.com/faelnor92/athena/main/install.sh | bash
```

**Windows** : Exécutez cette commande dans PowerShell :
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/athena/main/install.ps1 | iex
```

* **Alternative Docker Compose** : `docker compose up -d --build`

**Démarrage** : `athena start` ou `python3 server.py`. Accessible sur 👉 **http://localhost:8000/**.
