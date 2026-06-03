# 🎛️ Athena — Framework Multi-Agent Auto-Hébergé

![Version](https://img.shields.io/badge/version-0.9.37-blue.svg)
![Architecture](https://img.shields.io/badge/architecture-Multi--Tenant-success.svg)

Orchestrateur IA "Low-Resource" ultra-modulaire, pensé pour fonctionner sur des serveurs légers ou avec des GPU modestes. Accessible via **Interface Web**, **CLI**, **Telegram** et **Vocal Local**.

📖 **[Lisez le Guide Utilisateur Complet](docs/USER_GUIDE.md)** pour apprendre comment installer, configurer et utiliser Athena pas à pas.

## ✨ Fonctionnalités Clés

### 🔐 Multi-Tenant Pro & Collaboration
* **Sécurité & SSO** : Support de l'authentification OIDC / OAuth2 pour l'entreprise. Système d'inscription par invitation géré par l'administrateur.
* **Chiffrement au Repos** : Les conversations et les traces d'exécution stockées en base (SQLite) sont chiffrées au repos via Fernet (AES-128-CBC + HMAC-SHA256). La clé reste sous votre contrôle (`.env` ou secret-manager externe).
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
curl -sSL https://raw.githubusercontent.com/faelnor92/Athena/main/install.sh | bash
```

**Windows** : Exécutez cette commande dans PowerShell :
```powershell
iwr -useb https://raw.githubusercontent.com/faelnor92/Athena/main/install.ps1 | iex
```

* **Alternative Docker Compose** : `docker compose up -d --build`

**Démarrage** : `athena start` ou `python3 server.py`. Accessible sur 👉 **http://localhost:8000/**.

### ⚙️ Déploiement multi-worker (montée en charge)
L'état mutable partagé (comptes & quotas, sessions d'auth, routines, invitations, projets partagés, config par-utilisateur) est stocké dans une base SQLite commune en mode WAL (`athena_state.sqlite3`), avec des mises à jour atomiques — donc **cohérent entre plusieurs workers** :
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
```
> [!NOTE]
> **Caveat RAG.** La base vectorielle (ChromaDB `PersistentClient`) n'est pas conçue pour des écritures multi-process concurrentes. En multi-worker, faites tourner **ChromaDB en mode serveur** (client/serveur) ou réservez l'indexation RAG à un worker dédié. Tout le reste de l'état est multi-worker-safe.

---

## 🛡️ Tableau Comparatif : Athena vs Marché

> [!NOTE]
> **Méthodologie.** Comparer ce qui est comparable : **Athena**, **Hermes** et **OpenClaw** sont des *applications/assistants hébergés* ; **CrewAI** et **AutoGen** sont des *librairies d'orchestration* que l'on intègre dans son propre code (la sécurité, l'auth ou le multi-tenant y relèvent de l'application qu'on bâtit autour — d'où les « N/A »). Le différenciateur d'Athena n'est pas « avoir une UI » (OpenClaw a aussi des apps), mais le **multi-tenant + sécurité de niveau entreprise + coding agentique + observabilité** réunis dans un seul produit auto-hébergé.

| Catégorie | Critère | 🦉 Athena | Hermes Agent | OpenClaw | CrewAI | AutoGen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Interface & UX** | **Interface Graphique (UI)** | **Dashboard web complet (3D isométrique, graphe nodal, terminal intégré)** | Non | Apps companion (macOS/iOS/Android) + Live Canvas | Non (CrewAI Studio séparé) | Basique (AutoGen Studio) |
| | **Canaux d'interaction** | Web, Terminal UI, Telegram, Discord, Slack, Voix | CLI, Telegram, Slack, Discord | **15+ canaux (WhatsApp, Telegram, Signal, iMessage, Slack, Discord…)** | Code Python | CLI / code |
| | **Intégration IDE / dev local** | Console de code web + Sandbox | Non | Oui (assistant local) | S'intègre dans votre code | S'intègre dans votre code |
| **Orchestration** | **Modèle Multi-Agents** | **Essaim (Swarm) à routage sémantique automatique** | Sous-agents isolés parallèles | Routage multi-agents (isolation par workspace) | Séquentiel / Hiérarchique | Débats / Chat de groupe |
| | **Topologies de groupe** | Débats et transferts organiques | Handoffs isolés | Routage par canal/agent | Process séquentiel/hiérarchique | **Group chat avancé (Round Robin, etc.)** |
| | **Pipelines rigides** | Oui (chaîne de montage optionnelle) | Organique | — | **Natif (assembly line stricte)** | Linéaire ou organique |
| | **Persistance (Mémoire)** | **Vector DB + historique chiffré inter-sessions** | Oui (SQLite + FTS5) | Oui (sessions persistantes) | Oui (court/long terme + entités) | Limité (extensions/teachability) |
| | **Apprentissage (closed-loop)**| **Skills auto-générés + RAG d'expérience** | Oui (génération de skills) | Outils extensibles | Non | Non (hors teachability) |
| | **Outils & MCP** | **Outils natifs + MCP + Home Assistant** | Oui (MCP) | Oui (browser, canvas, cron, MCP) | Oui (crewai-tools + MCP) | Oui (function calling, extensions) |
| **Sécurité Globale** | **Authentification** | **Mot de passe, tokens, SSO (OIDC)** | Non (local) | Basique (local) | N/A (librairie) | N/A (librairie) |
| | **Contrôle d'accès (RBAC)** | **Oui (rôles Lecteur/Éditeur, permissions par user)** | Non | Non | N/A | N/A |
| | **Quotas / coûts par user** | **Oui (quota tokens/jour par compte + alertes budget)** | Non | Non | N/A | N/A |
| **Exécution & Réseau**| **Sandbox d'exécution** | **Conteneur Docker éphémère (ressources limitées)** | Varie | Hôte | Via code interpreter | **Oui (Docker supporté)** |
| | **Bouclier anti-SSRF** | **Oui (DNS rebinding, blocage réseau interne/métadonnées)** | Non | Non | N/A | N/A |
| **Protection Données** | **Masquage des secrets (logs)** | **Oui (clés API / mots de passe redacted)** | Non | Partiel | N/A | N/A |
| | **Chiffrement au repos** | **Oui (Fernet/AES-128 sur conversations + traces)** | Non | Dépend du stockage | N/A | N/A |
| | **Isolation multi-locataires** | **Oui (mémoire/agenda/budget isolés par user)** | Non | Par workspace | N/A | N/A |
| | **Approbation humaine (HITL)** | **Oui (interception des actions sensibles dans l'UI)** | Oui (via chat) | Basique | À coder soi-même | À coder soi-même |
