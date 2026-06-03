# 🎛️ Athena — Framework Multi-Agent Auto-Hébergé

![Version](https://img.shields.io/badge/version-0.9.36-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)

Orchestrateur IA "Low-Resource" ultra-modulaire, pensé pour fonctionner sur des serveurs légers ou avec des GPU modestes. Accessible via **Interface Web**, **CLI**, **Telegram** et **Vocal Local**.

📖 **[Lisez le Guide Utilisateur Complet](docs/USER_GUIDE.md)** pour apprendre comment installer, configurer et utiliser Athena pas à pas.

## ✨ Fonctionnalités Clés

### 🔐 Multi-Tenant Pro & Collaboration
* **Sécurité & SSO** : Support de l'authentification OIDC / OAuth2 pour l'entreprise. Système d'inscription par invitation géré par l'administrateur.
* **Chiffrement E2E au Repos** : Les conversations en base de données (SQLite) sont chiffrées de bout en bout via AES-256 (Fernet) pour une confidentialité totale.
* **Contrôle des Coûts (Quotas)** : Bridage automatique des dépenses API via un système de quotas de tokens journaliers configurable par utilisateur.
* **Sécurité Avancée** : Protection intégrée anti-SSRF (DNS rebinding) pour la navigation web et masquage automatique des secrets (Redaction) dans les logs.
* **Isolation Absolue** : Chaque utilisateur dispose de sa propre mémoire (RAG, Core Memory), de son propre agenda, de ses listes et de son budget API.
* **Self-Service LLM** : Chaque utilisateur peut surcharger les modèles IA globaux avec ses propres clés API (OpenAI, Anthropic, Gemini, Groq, etc.).
* **Projets Partagés** : Création d'espaces de travail (Workspaces) collaboratifs avec gestion fine des rôles (Lecteur / Éditeur) et verrouillage anti-collision des fichiers.

### 🧠 Moteur d'Orchestration & LLM
* **Multi-Modèles** : OpenAI, Anthropic, Gemini, Ollama, Groq, Mistral, Qwen, APIs locales compatibles.
* **Swarm (Essaim)** : Routage automatique entre agents spécialisés (handoffs), exécution concurrente, débats inter-agents.
* **Pipelines Rigides (Optionnel)** : Possibilité de forcer une chaîne de montage stricte où les agents s'enchaînent séquentiellement sans autonomie de déviation.
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
* **Navigation Git & Code** : Compréhension de vos dépôts de code (logs, branches, édition), exécution bash/python via Sandbox Docker.
* **Création de Skills à la Volée** : L'IA peut littéralement *coder ses propres outils* et les sauvegarder de façon permanente pour étendre ses capacités !
* **Administration SSH** : Gestion de vos serveurs distants via des commandes SSH.
* **Créativité & Web** : Recherche web approfondie, génération d'images/vidéos (Fal, Replicate), scraping.
* **Traitement Média & Réunions** : Capacité à résumer et transcrire des fichiers audios ou des réunions entières.

### 🏠 Domotique & Automatisations
* **Domotique Native (Home Assistant)** : Lecture d'état et exécution d'actions domotiques (lumières, volets, capteurs) de façon instantanée.
* **Conscience Spatiale** : Sait dans quelle pièce vous êtes pour diriger ses actions sur votre environnement physique.
* **Routines Proactives & Workflows** : Planification de tâches (CRON) isolées par utilisateur, déclenchements webhooks, intégrations poussées avec **n8n**.
* **Agenda & Listes** : Synchronisation bidirectionnelle Google Calendar, iCal et CalDAV. Gestion de vos Todos et listes de courses.
* **Notifications Actives** : Alertes autonomes de la part d'Athena vers Telegram, Discord, Slack, Email et Webhooks.

### 💾 Mémoire & Apprentissage
* **Base Vectorielle RAG** : Indexation sémantique automatique de documents via ChromaDB.
* **Knowledge Graph & Core Memory** : Archivage de faits durables et modélisation de relations en réseau (Graphes).
* **Auto-Amélioration** : Retour d'expérience persistant après une tâche complexe pour affiner le comportement futur.
* **Sauvegarde & Restauration** : Système complet de backup/restore de l'état (conversations, RAG, routines, configurations).

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

---

## 🛡️ Tableau Comparatif : Athena vs Marché

| Catégorie | Critère | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Interface & UX** | **Interface Graphique (UI)** | **Oui (Dashboard complet, 3D, Graphe Nodal)** | Non | Non | Non | Basique (AutoGen Studio) |
| | **Interaction** | Web, Terminal UI, Telegram, Discord, Voix | CLI, Telegram, Slack, Discord | CLI | Scripts Python purs | CLI |
| | **Intégration IDE** | Non (Bureau Virtuel unifié favorisé) | Non | **Oui (Native CLI/IDE)** | Non | Non |
| **Orchestration** | **Modèle Multi-Agents** | **Essaim (Swarm) avec routage sémantique automatique** | Sous-agents isolés parallèles | Multi-agents basique | Séquentiel / Hiérarchique strict | Débats / Chat de groupe |
| | **Topologies de Chat Groupé** | **Oui (Débats et transferts organiques)** | Handoffs isolés | Modèle standard | Pipelines stricts définis à l'avance | **Débats de groupe complexes, algorithmes (Round Robin, etc.)** |
| | **Exécution de scripts rigides** | **Oui (Outil optionnel de chaîne de montage)** | Organique | Linéaire basique | **Très robuste (Assembly line stricte native)** | Linéaire ou organique |
| | **Persistance (Mémoire)** | **Oui (Vector DB, historique, conservation inter-sessions)** | **Oui (SQLite + FTS5)** | Non (Fichiers locaux) | Non (Épisodique) | Non (Sauf implémentation manuelle) |
| | **Apprentissage (Closed-Loop)**| **Oui (Création de "Skills" à la volée + RAG Experience)** | **Oui (Génération de "Skills")** | Non | Non | Non |
| | **Support Outils & MCP** | **Oui (Outils natifs, MCP, intégration Home Assistant)** | Oui (MCP) | Oui | Partiel (Custom tools) | Partiel |
| **Sécurité Globale** | **Authentification** | **Mot de passe, Tokens Sécurisés, SSO (OIDC)** | Non (Exécution locale isolée) | Non | Non | Non |
| | **Contrôle d'Accès (RBAC)** | **Oui (Rôles Lecteur vs Éditeur, permissions par utilisateur)** | Non | Non | Non | Non |
| | **Limitation de Quotas / Coûts** | **Oui (Quota LLM strict par utilisateur, compaction mémoire)** | Non | Non | Non | Non |
| **Exécution & Réseau**| **Isolation du Code (Sandbox)**| **Oui (Conteneur Docker éphémère, ressources limitées)** | Varie selon déploiement | Non (Tourne sur la machine hôte) | Non | **Oui (Docker supporté)** |
| | **Bouclier Anti-SSRF (Réseau)**| **Oui (Protection contre DNS Rebinding et scans locaux)** | Non | Non | Non | Non |
| **Protection Données** | **Censure des Secrets (Logs)** | **Oui (Masque automatiquement les clés API et mots de passe)** | Non | Non | Non | Non |
| | **Chiffrement de bout en bout**| **Oui (AES-256 Fernet sur les bases de données)** | Non | N/A | N/A | N/A |
| | **Isolation Multi-Locataires** | **Oui (Conversations et mémoires isolées par utilisateur)** | Non | N/A | N/A | N/A |
| | **Approbation Humaine (HITL)** | **Oui (Interception des actions sensibles via l'UI web)** | Oui (Via terminaux de chat) | Non / Basique | Requiert du code spécifique | Requiert du code spécifique |
