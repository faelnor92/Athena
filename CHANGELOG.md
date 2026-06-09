# Historique des Versions (Changelog)

## v0.11.0 (Python 3.13, Apache 2.0 & CacheAligner natif)
Modernisation de la plateforme : passage à Python 3.13, mises à jour majeures des dépendances,
bascule en licence Apache 2.0, et une optimisation native du cache de prompt sans perte.

### 🐍 Python 3.13 & dépendances
- **Python 3.11 → 3.13** partout : image Docker de l'app, CI, et images par défaut de la sandbox d'exécution de code (`sandbox_runner`, `dev_container`, `athenadesign_runner`).
- **chromadb 0.5.0 → 1.5.9** : requis pour 3.13 (la 0.5.0 utilise `np.float_`, supprimé en numpy 2, et numpy<2 n'a pas de wheels 3.13). La 1.x ne dépend plus de fastapi → aucun conflit avec la stack web épinglée. Lecture transparente des bases `.chroma_db` existantes (aucune migration).
- **litellm 1.52.12 → 1.88.1** et **openai 1.55.3 → 2.41.0** (openai sans usage direct, transitif via litellm).

### 🔒 Sécurité CI
- **GitHub Actions sur Node 24** : `actions/checkout@v5`, `actions/setup-python@v6` (fin du support Node 20 en septembre 2026).

### ⚡ CacheAligner natif (efficacité tokens, sans perte)
- Le **timestamp** (`%H:%M`) et le **contexte RAG** étaient inclus dans le bloc système marqué `cache_control` : ils invalidaient le **prompt cache** du provider à chaque tour (le RAG dépend du message courant). Ils sont désormais émis dans un **message système volatile après l'historique**, hors du préfixe caché. Le bloc système stable redevient byte-identique d'un tour à l'autre → **cache HIT** sur les conversations multi-tours. Aucune perte d'information (contexte repositionné près de la requête).

### 📄 Licence
- **MIT → Apache 2.0** (`LICENSE` + badges/sections des 7 README). Le sous-outil tiers `tools/mcp-servers/ha-mcp` conserve sa licence MIT propre.

## v0.10.1 (Internationalisation)
Athena parle désormais la langue de l'utilisateur — interface **et** réponses des agents.

### 🌍 Multilingue (fr/en/es/it/de/zh/ja)
- **Réponses des agents dans la langue de l'UI** : la langue d'interface est transmise au serveur (en-tête `X-Athena-Lang`), portée par une ContextVar (`_current_lang`) et injectée dans le **préambule système** — les agents répondent dans la langue choisie, *sauf demande contraire* (noms d'outils/fichiers/code inchangés). En-tête envoyé par le wrapper `apiFetch` et par le studio AthenaDesign (iframe same-origin).
- **Infra i18n légère** (`static/i18n.js`, sans dépendance) : FR comme langue de base, traductions par dictionnaire, repli propre sur le FR, sélecteur de langue dans le dock, détection navigateur + persistance `localStorage`.
- **Couverture UI** : navigation (dock) + **onglets et groupes des Réglages** traduits dans les 6 langues.
- **Documentation traduite** : `README` et **guide utilisateur** (`docs/USER_GUIDE.*`) disponibles en anglais, espagnol, italien, allemand, chinois et japonais (sélecteur de langue en tête).

## v0.10.0 (AthenaDesign Studio, Plugins & Auto-correction)
Lot majeur : nouveau studio de design IA, projets unifiés code+design, plugins (Claude Code),
auto-correction (design + code), efficacité tokens, robustesse d'orchestration et audit sécurité.

### 🎨 AthenaDesign Studio (nouveau)
- **4 types d'artefacts** : web **HTML/CSS/JS**, **React/JSX** (rendu live React+Babel+Tailwind), **Mermaid** (diagrammes), et **Python** exécuté en **sandbox Docker** (PowerPoint via python-pptx, graphiques Matplotlib/Plotly).
- **Branché sur l'infra LLM d'Athena** (même choix de modèle/clés/fallback ; plus de chemin LLM séparé).
- **Design System** par projet (charte couleurs/typo) : saisie, extraction d'un CSS, ou **import depuis l'URL** d'un site (capture web).
- **Imports** : images/documents (PDF→texte via pypdf) + capture web ; **routage vision** (modèle multimodal → sinon pré-description → sinon note ; marche au max sans vision).
- **Itération** : annotations, **sliders WYSIWYG** (accent/arrondi/police), versions, **modèles de départ**.
- **Exports** : PDF (Chromium headless), PPTX, HTML ; **partage par lien** en lecture seule (iframe sandbox).
- **Anti-débordement pptx déterministe** (post-traitement : word_wrap + shrink-to-fit).
- **Sandbox durcie** : exécution du code généré via Docker (réseau coupé, cap-drop) ; repli local journalisé.

### 🗂️ Projets unifiés & multi-utilisateur
- Un **projet Athena = code + design** (même registre `core.projects`, même liste des deux côtés).
- AthenaDesign **multi-tenant** : projets isolés par utilisateur, fichiers générés servis **authentifiés** (ownership + anti path-traversal), jeton de session propagé au studio.

### 🔌 Plugins & auto-correction
- **Onglet Réglages > Plugins** + **plugin Claude Code** (`claude_code`) : délègue le code à l'agent Claude Code (CLI), scopé au projet actif, opt-in admin, **donné automatiquement au Codeur** quand activé.
- **Auto-correction** : scripts Python du studio (generate→run→fix) **et** Codeur **Code-Test-Fix** (`pytest`/`npm test` → corrige → revérifie, borné).

### ⚙️ Orchestration & efficacité tokens
- **Anti-boucle** : disjoncteur de répétition d'outils + rattrapage en fin de budget (réponse de synthèse) + `SWARM_MAX_TURNS` configurable.
- **Anti-hallucination d'outil** : parseur de tool-call écrit en texte + renfort de préambule.
- **Filtrage d'outils par pertinence** (n'expose que les schémas utiles) + **préambule compacté** → ~45 % de prompt en moins/tour. *L'optimisation ne retire jamais une capacité (résolution contre l'ensemble autorisé).*

### 🔒 Sécurité & install
- Corrigés : **SSRF** capture web (fail-closed), **vol de jeton** via lien partagé (iframe sandbox sans same-origin), toggle de plugin réservé **admin**.
- **Install** : `install.sh`/`install.ps1` installent désormais **Docker + un navigateur headless** (requis pour la sandbox et l'export PDF). `requirements.txt` à jour (python-pptx, httpx).

## v0.9.41 (Codeur utilisable & IDE en fenêtre)
Refonte de l'expérience de code (console + IDE) et correctifs majeurs remontés à l'usage.

### 🤖 Code agentique — enfin opérationnel
- **Outils fichiers donnés aux agents** : la cause racine de « le codeur ne crée rien » était qu'AUCUN agent n'avait d'outil d'écriture. Le Codeur dispose désormais de `read/write/edit_file`, `apply_patch`, `search_code`, `file_outline`, `find_definition/references` et `git_*` (configs par défaut/exemple incluses). Prompt réallégé (rôle + « projet actif, chemins relatifs ») — les outils cochés sont exposés au modèle via leur schéma.
- **Handoffs réparés** (`Jarvis` → `Athena`).
- **Verbosité réduite** : le Codeur annonce, agit via les outils, et conclut court.
- **Sandbox = projet actif** : bash/python/tests s'exécutent dans le projet sélectionné (montage en écriture → les fichiers produits y persistent), et non plus dans un ancien dossier global.

### 🖥️ Console codeur & IDE
- **Console isolée du chat** : mémoire dédiée (par utilisateur et par projet) ; la console ne pollue plus le chat principal et garde son contexte. `max_turns` relevé (défaut 30).
- **Projet propre à la console** : un sélecteur permet de coder dans la console sur un projet **différent** de celui du chat/vocal (override de contexte).
- **Vue console repensée** : chat principal masqué (grille pleine largeur, plus de zone vide) ; **arborescence du projet** avec auto-refresh (on voit les fichiers créés par l'agent apparaître).
- **IDE en VRAIE fenêtre** (`window.open`) : déplaçable sur un 2ᵉ écran, avec **onglets**, arbre, sauvegarde Ctrl+S et auto-refresh. L'IDE intégré (vue Fichiers) reste éditable (multi-onglets, aperçu PDF/images, live-reload).

### 🔒 Sécurité (audit injections/intrusion)
- **Anti-SSRF** sur les flux agenda **iCal/CalDAV** (URL fournie par l'utilisateur, fetch côté serveur → réseau interne/métadonnées cloud bloqués).
- **Sandbox `tool_script` durcie** : fermeture de l'évasion `"{0.__class__}".format()` (dunders en chaîne littérale).
- Vérifiés sûrs : SQL paramétré, upload (basename+limite), exécution code (Docker + AST + terminal admin-only), authz centralisée.

### 🩹 Correctifs UI
- **Artefact (aperçu)** : ne s'ouvrait pas sous CSP (srcdoc héritait) → passage en iframe `blob:` (contexte propre, toujours sandbox isolé), React inclus.
- **Bouton « Parcourir »** invisible : un `<div>` non fermé du formulaire d'agent imbriquait la modale dans la modale Réglages (cachée) → HTML rééquilibré.

### 📡 Observabilité (optionnelle)
- **OpenInference** (traçage LLM → Phoenix) intégrable en option (`OPENINFERENCE_ENABLED`, `requirements-observability.txt`, service compose).

---

## v0.9.40 (Éditeur intégré & collaboration)
L'explorateur de fichiers devient un mini-IDE éditable, avec une première couche collaborative.

### 📝 Mini-IDE
- **Explorateur éditable** : édition des fichiers directement dans l'UI, **multi-onglets** (CodeMirror), coloration syntaxique, **autocomplétion** basique (Ctrl+Espace + au fil de la frappe), parenthèses auto, indicateur « ● modifié ».
- **Sauvegarde** (💾 / Ctrl+S) → `POST /api/workspace/file`, avec garde de rôle **`can_write`** (un *Lecteur* de projet partagé est en lecture seule, comme pour les outils de l'agent).
- **Panneau redimensionnable** : poignée draggable + bouton replier pour agrandir l'éditeur.

### 👥 Collaboration (niveau 1 + soupçon de niveau 2)
- **Live-reload** : quand l'agent (ou un autre process) modifie un fichier ouvert, la vue se rafraîchit automatiquement ; si vous avez des modifications locales non enregistrées, un avertissement remplace l'écrasement.
- **Présence** : affichage des autres personnes consultant le même fichier (`POST /api/workspace/presence`, via le store partagé). `GET /api/workspace/file` renvoie désormais le `mtime` ; `GET /api/workspace/file/meta` pour le polling léger.

---

## v0.9.39 (Qualité & multi-worker)
Fiabilisation (tests/CI), finalisation du multi-worker et compléments d'UI.

### ✅ Qualité
- **Tests d'intégration HTTP** (TestClient) couvrant les vrais flux : en-têtes de sécurité, exigence d'authentification, login, **RBAC** (user → 403 sur endpoint admin), déconnexion qui invalide le jeton, politique de mot de passe.
- **CI GitHub Actions** : toute la suite (unit + intégration + smoke) à chaque push/PR, + job de scan de sécurité (pip-audit/bandit) informatif.

### ⚙️ Multi-worker (finalisation)
- **Listes** par-utilisateur déplacées vers le store SQLite partagé (mutations atomiques) + migration douce.
- **Agenda** : écritures atomiques (temp + `os.replace`) → plus de fichier corrompu en multi-worker.
- **RAG / ChromaDB en mode serveur** optionnel (`CHROMA_SERVER_HOST`) : tous les workers partagent la même base vectorielle. `docker-compose.yml` : service `chroma` câblé + `STATE_DB_PATH` persistant sur le volume.

### 🖥️ UI
- **Routines** : sélecteur de **workflow** (une routine planifiée/webhook peut déclencher un pipeline déterministe).
- **Admin** : vue « usage de tous les comptes » (30 j) et bouton de **réinitialisation 2FA** par compte (récupération appareil perdu).

---

## v0.9.38 (Sécurité durcie)
Durcissement de sécurité « béton » : surface d'authentification, en-têtes HTTP, audit,
limitation de débit, RBAC par outil, 2FA, et corrections.

### 🔑 Authentification & sessions
- **Throttle anti-brute-force partagé** entre workers (store SQLite) au lieu d'un compteur par-process.
- **Révocation de sessions** : un changement/reset de mot de passe (et la suppression d'un compte) invalide les sessions concernées ; un token volé ne survit plus. Endpoint **`POST /api/logout`** + purge des sessions expirées.
- **Politique de mot de passe** : `MIN_PASSWORD_LENGTH` (défaut **8**, au lieu de 4).
- **2FA / TOTP optionnelle** (RFC 6238, Python pur, compatible Google Authenticator/Authy/FreeOTP) : secret stocké chiffré, enrôlement self-service + champ code à la connexion, réinitialisation par un admin. Aucun impact pour les comptes sans 2FA.

### 🛡️ Surface HTTP & abus
- **En-têtes de sécurité** : CSP, X-Frame-Options=DENY (anti-clickjacking), X-Content-Type-Options, Referrer-Policy, Permissions-Policy, HSTS (en HTTPS). Configurables (`SECURITY_HEADERS`, `CONTENT_SECURITY_POLICY`).
- **Rate-limiting** général par IP (`RATE_LIMIT_PER_MIN`, défaut 300/min, 429 au dépassement).

### 🔒 Autorisation & traçabilité
- **Validation admin des automatisations** : pipelines/routines créés par un compte « user » restent en attente jusqu'à validation par un admin (UI + API). Auto-validé en mode local/foyer.
- **RBAC par outil** : `ADMIN_ONLY_TOOLS` réserve certains outils (bash/python/SSH…) aux admins.
- **Journal d'audit** : trace append-only des événements sensibles (connexions, mots de passe, comptes, invitations, validations, 2FA), masquage des secrets, `GET /api/audit` (admin).

### 🚀 Déploiement & outillage
- **Image Docker** non-root + `HEALTHCHECK`.
- **`scripts/security_scan.sh`** : pip-audit + bandit (si installés) + détection de secrets versionnés.
- **README** : section « Sécurité en production » (TLS/HSTS, clé hors `.env`, garde-fous).

### 🐛 Correctifs
- **Sauvegarde** : la base d'état partagé `athena_state.sqlite3` (comptes/quotas/routines/projets/config) et les données par-utilisateur sont désormais incluses dans le backup (régression de la migration multi-worker corrigée).

---

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
