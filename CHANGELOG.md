# Historique des Versions (Changelog)

## v0.9.37 (Multi-Worker & Workflows)
Montée en charge (déploiement multi-worker), nouveau mode d'orchestration déterministe, fiabilisation de la voix et **rectifications d'exactitude** dans la documentation.

### ⚙️ Multi-Worker (montée en charge)
- **État partagé en SQLite (WAL)** : comptes & quotas, sessions d'authentification, routines, invitations, projets partagés et config par-utilisateur passent d'un dict en mémoire + fichier JSON à une base SQLite commune (`athena_state.sqlite3`). L'application est désormais **cohérente avec plusieurs workers** (`uvicorn --workers N`).
- **Compteurs atomiques** : les quotas de tokens et l'usage-unique des invitations utilisent des transactions atomiques (plus de perte de mise à jour sous concurrence).
- **Sessions inter-workers** : un login sur un worker est reconnu par tous les autres.
- **Core Memory** : rechargement automatique sur changement (mtime) — un worker voit les faits ajoutés par un autre.
- **Migration non destructive** : import unique des anciens fichiers JSON (le fichier source est conservé en backup).
- **Caveat documenté** : la base vectorielle (ChromaDB) n'étant pas conçue pour des écritures multi-process, lancer ChromaDB en mode serveur (ou réserver l'indexation RAG à un worker) en multi-worker.

### 🛠️ Workflows — pipelines déterministes (type CrewAI)
- Nouveau mode **optionnel** : des pipelines nommés (suite ordonnée d'étapes = agent + instruction + sortie attendue) exécutés séquentiellement et **directement** (pas via le routage organique du Swarm), où aucun agent ne peut dévier de la chaîne (`locked` + nouveau `lock_delegation`).
- **Exécution & déclenchement** : onglet UI no-code « Workflows », API `GET/POST/DELETE /api/pipelines` + `POST /api/pipelines/{id}/run` (n8n/webhook), et déclenchement par routine planifiée (`pipeline_id`).
- **Observabilité** : chaque étape est un run tracé distinct.
- Le Swarm organique reste le comportement par défaut.

### 🎙️ Voix (S2S) — fiabilité & latence
- Correction d'une **fuite de connexion** (réponse TTS en streaming désormais fermée) et d'un **bug d'alignement int16** (octet impair reporté au lieu d'être paddé sur place, qui corrompait l'audio).
- **Barge-in immédiat** (`stream.abort()` au lieu de `stop()` qui vidait le buffer), en-tête WAV robuste (localisation du sous-chunk `data`), `OutputStream(latency='low')`.

### 🔐 Sécurité & confidentialité
- **Chiffrement au repos étendu aux traces** : `runs.sqlite3` (messages, réponses, étapes) est désormais chiffré, comme les conversations.
- **Rectification de terminologie** : le chiffrement est **« au repos »** via **Fernet (AES-128-CBC + HMAC-SHA256)** avec clé sous contrôle de l'utilisateur — et **non** « E2EE / de bout en bout / AES-256 » comme annoncé par erreur en v0.9.36. La protection couvre conversations + traces.

### 📊 Usage & UI
- **Suivi d'usage par utilisateur** (requêtes, tokens, coût €) : panneau « Mon usage » (self) + vue admin agrégée (`/api/usage`).

### 📚 Documentation
- Tableau comparatif refondu et honnête (OpenClaw : apps companion + Live Canvas + 15+ canaux ; CrewAI : mémoire intégrée + MCP ; distinction application hébergée vs librairie pour les critères de sécurité).
- USER_GUIDE : sections Projets/Workspaces partagés + rôles, « Mon usage », déploiement multi-worker.
- Correction de l'URL d'installation (`faelnor92/Athena`, sensible à la casse).

### 🧹 Divers
- Pipeline rigide : `delegate_to_` n'est plus retiré par `locked` (mode CLI/console inchangé) ; seul le flag dédié `lock_delegation` (pipeline) le retire.
- Suppression du bruit de télémétrie ChromaDB dans les logs. Signature du briefing utilisant le nom d'appli configurable.

---

## v0.9.36 (Sécurité & Optimisation)
> ⚠️ **Rectification (v0.9.37)** : le chiffrement décrit ci-dessous est en réalité **au repos** (clé serveur dans `.env`) et utilise **Fernet/AES-128**, non « E2EE / de bout en bout / AES-256 ». Voir v0.9.37.

Cette mise à jour mineure se concentre sur le durcissement de la sécurité des données et la protection des budgets API.

### 🔐 Sécurité & E2EE
- **Chiffrement au repos (E2EE)** : Les historiques de conversations stockés dans SQLite sont désormais chiffrés de bout en bout en AES-256 (Fernet). Une clé secrète est auto-générée dans le `.env`.
- **Rétrocompatibilité** : Migration douce automatique des anciens historiques non chiffrés.
- **Backup** : Ajout explicite de `conversations.sqlite3` et `users.json` à la boucle de sauvegarde (sans inclure le `.env`).

### 🪙 Quotas & Contrôle des Coûts
- **Limites Utilisateurs** : Introduction d'un quota strict de tokens LLM journalier par utilisateur, administrable via `users.json`.
- **Interception Active** : Suivi rigoureux de la consommation (prompt+completion) via `response.usage` ou estimation heuristique.
- **Plafonnement** : Réduction automatique de la taille du contexte envoyé à l'API (`_maybe_compact` rendu plus agressif à 15 messages) et plafonnement matériel à 4000 tokens maximum en réponse.

### ⚙️ Orchestration
- **Pipeline Rigide** : Ajout d'un nouvel outil expérimental `run_rigid_pipeline` permettant de forcer un travail à la chaîne séquentiel (ex: Agent A -> Agent B -> Agent C) en ignorant les transferts naturels du Swarm.

---

## v0.9.35 (Dernière version majeure)
*Nom de code officiel : Athena*

Cette version apporte une refonte structurelle massive du cœur de l'application pour passer d'un assistant local mono-utilisateur à une plateforme multi-agent robuste de niveau entreprise (multi-tenant).

### 🚀 Nouveautés Majeures

#### 1. Architecture Multi-Tenant & Sécurité (Pro)
- **Isolation Totale** : La mémoire, les listes, les bases vectorielles (RAG), l'agenda et la configuration des modèles sont désormais strictement isolés par utilisateur.
- **SSO OIDC / OAuth2** : Support de l'authentification unifiée d'entreprise.
- **Gestion des Invitations** : Inscription verrouillée par défaut, gérée par liens d'invitation générés par l'admin.
- **Self-Service & Quotas** : Chaque utilisateur gère ses propres clés d'API LLM et son budget. L'admin a accès à un suivi détaillé de la consommation (requêtes, tokens, coûts) par utilisateur.

#### 2. Espace de Travail & Collaboration
- **Projets Partagés** : Les workspaces peuvent désormais être partagés entre utilisateurs avec une gestion fine des droits (Viewer ou Éditeur).
- **Verrouillage** : Les fichiers d'un projet partagé supportent un verrouillage d'édition pour éviter les conflits d'écriture lors du pair-programming avec les agents.

#### 3. Voix & Satellites
- **Intégration Kokoro TTS** : Support natif et streaming fluide de la synthèse vocale ultra-rapide Kokoro (API locale Docker). Redémarrage du conteneur via l'interface.
- **Satellites ESPHome** : Connectivité en lecture/écriture directe (S2S) pour les ESP32-S3 (sans nécessiter Home Assistant comme intermédiaire).
- **Whisper STT** : Amélioration de la fiabilité et réduction de la latence du streaming.

#### 4. Outils & Swarm
- **Outils Natifs Indépendants** : `get_time` et `get_weather` ajoutés pour éviter le recours excessif au briefing complet. Le Swarm devient plus intelligent dans le routage de ses outils.
- **MCP Home Assistant** : Vendorisation locale sécurisée du connecteur HA-MCP.
- **Lecture Seule** : Possibilité d'exécuter des outils en lecture seule sécurisée.
- **Observabilité** : Historique complet et centralisé de l'exécution des outils (durée, échecs, succès) via un panneau de Logs UI en temps réel.

#### 5. Renommage Global
- **De Jarvis à Athena** : Le code source, l'interface graphique, le CLI système et la documentation ont été globalement purgés de "Jarvis" pour le nom officiel "Athena". Les applications restent agnostiques (utilisation de variables d'environnement `APP_NAME`).

---

## v0.9.0
- Sortie initiale de la base Swarm v2 avec interface web basique.
- Script de migration SQLite PRAGMA.
