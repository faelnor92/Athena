# 🎛️ Jarvis — Framework Multi-Agent Auto-Hébergé

Orchestrateur IA "Low-Resource" ultra-modulaire, pensé pour fonctionner sur des serveurs légers ou avec des GPU modestes. Accessible via **Interface Web**, **CLI**, **Telegram** et **Vocal Local**.

## ✨ Fonctionnalités Clés

### 🧠 Moteur d'Orchestration & LLM
* **Multi-Modèles** : OpenAI, Anthropic, Gemini, Ollama, Groq, Mistral, Qwen, API locales compatibles.
* **Swarm (Essaim)** : Routage automatique entre agents spécialisés (handoffs), exécution concurrente, débats inter-agents.
* **Architecture Modulaire** : Backend FastAPI découpé par routeurs fonctionnels, soutenu par une base de données **SQLite** robuste et thread-safe.
* **Isolation Parfaite** : État isolé par exécution (ContextVars). Plusieurs requêtes parallèles ou Telegram n'interfèrent pas.

### 🌐 Interface Web Avancée
* **Bureau Virtuel (3D Isométrique)** : Visualisation de l'essaim, agents actifs surlignés, animations de délégation.
* **Cockpit & Télémétrie** : Suivi en direct des tokens, coûts financiers, exécutions et erreurs.
* **Outils Intégrés** : Explorateur de fichiers, agenda, listes, terminal, et galerie de médias générés.
* **Réglages No-Code** : Gestion complète des agents, du profil, des clés API et de la sécurité directement via l'interface.

### 🧰 Outils & Extensibilité (Skills)
* **Serveurs MCP (Model Context Protocol)** : Branchez des serveurs externes (GitHub, Postgres, FS) sans coder. Reconnexion à chaud.
* **Computer Use (RPA 2.0)** : Pilotage d'un navigateur interactif headless (Playwright) optimisé pour les LLMs (DOM allégé).
* **Maintenance Autonome (Nightly)** : Un agent nocturne hardcodé et gratuit (Ollama) nettoie et vérifie (AST) le code des compétences automatiquement.
* **Sandbox Docker** : Exécution de code et commandes shell confinées, sûres, jetables et bridées (CPU/RAM).
* **Capacités Natives** : Recherche web, scraping, génération d'images/vidéos (Fal, Replicate).

### 🏠 Domotique & Automatisations
* **Home Assistant** : Lecture d'état et exécution d'actions domotiques (lumières, volets, scénarios).
* **Routines Proactives** : Planification de tâches (CRON) ou déclenchement par webhooks (briefings matinaux, veille).
* **Agenda & Listes** : Synchronisation bidirectionnelle Google Calendar, iCal et CalDAV.
* **Notifications** : Alertes autonomes vers Telegram, Discord, Slack, Email et Webhooks.

### 💾 Mémoire & Apprentissage
* **Base Vectorielle RAG** : Indexation sémantique automatique de documents via ChromaDB.
* **Mémoire Sémantique** : Archivage de faits durables et des préférences utilisateur (Core Memory).
* **Auto-Amélioration** : Retour d'expérience persistant après une tâche complexe pour affiner le comportement futur.

### 🎙️ Assistant Vocal (STT/TTS)
* **100% Local** : Whisper (STT) et Piper (TTS) exécutés localement, sans dépendance cloud.
* **Détection de Mot-Clé (Wake Word)** : openWakeWord avec support du "barge-in" (interruption de la parole IA par l'utilisateur).
* **Satellites ESP32-S3** : Connexion directe de satellites vocaux ESPHome au framework, sans passer par Home Assistant.

### 🔐 Sécurité & Multi-Utilisateurs
* **Comptes Foyer** : Multi-utilisateurs avec rôles (Admin/User). Les actions sensibles sont réservées aux admins.
* **Protection Active** : Anti-Bruteforce (Throttling IP) sur la connexion. Mots de passe hashés PBKDF2.
* **Workspace Confiné** : Le code source et le `.env` sont strictement inaccessibles à l'IA explorant les fichiers.

## 🚀 Installation Rapide

* **Linux / macOS** : `chmod +x install.sh && ./install.sh`
* **Windows** : `.\install.ps1`
* **Docker Compose** : `docker compose up -d --build`

**Démarrage** : `jarvis start` ou `python3 server.py`. Accessible sur 👉 **http://localhost:8000/**.
