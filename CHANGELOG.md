# Historique des Versions (Changelog)

## v0.11.34 (Prompt caching — la mémoire ne casse plus le cache)

### 🧊 Audit CacheAligner (#3 de la roadmap efficacité)
- **Cache-buster corrigé** : la **Core Memory** (faits mémorisés) et le **profil utilisateur** étaient ajoutés au `system_prompt` STABLE → chaque `memorize_fact` (parfois EN COURS de run via la mémoire proactive) changeait le préfixe et **invalidait le prompt cache** du gros system_prompt. Ils sont désormais émis en **VOLATILE** (après le point de cache, comme le timestamp et le RAG).
- Résultat : le gros préfixe système (persona + instructions + liste d'agents) **reste cacheable** même quand la mémoire évolue → moins de latence/coût (cache hits Anthropic, prefix caching serveur). Le coût de renvoi non-caché de la mémoire (petite) est négligeable.
- Audit : timestamp + RAG déjà correctement en volatile ✓. Reste identifié pour plus tard (gain supplémentaire, mais plus risqué) : mettre en cache aussi le PRÉFIXE D'HISTORIQUE des longues boucles agentiques (2ᵉ point de cache).
## v0.11.33 (Sélection par pertinence des skills/MCP — économie de tokens)

### 🎯 Disclosure progressive (#2 de la roadmap efficacité)
- Les outils **« extra » hors groupes** (skills auto-induites + outils MCP, souvent 20-50 par serveur) échappaient au filtre par mots-clés → **tous leurs schémas étaient injectés à chaque tour**. Désormais, au-delà de `TOOL_SEMANTIC_TOPN` (12 par défaut), on n'expose que les **top-N les plus pertinents** pour la requête (recouvrement nom+description, sans embedding → zéro coût/latence).
- S'applique à **tout agent** recevant des extras (orchestrateur ET Codeur), **sans jamais toucher** aux outils cœur (`AVAILABLE_TOOLS`) ni à la délégation.
- Comme le filtre keyword : on **masque le schéma, pas l'exécution** (l'outil reste appelable via `_secured_tools` ou `run_tool_script` qui expose toutes les skills) → **zéro perte de capacité**.
- Réglable : `TOOL_SEMANTIC_TOPN` (défaut 12), gouverné par `TOOL_FILTER_ENABLED`.
## v0.11.32 (Programmatic tool calling réellement actif)

### ⚡ Orchestration par script (économie de tokens)
- **Correctif majeur** : `run_tool_script` était mentionné dans le prompt de l'orchestrateur **mais absent de sa liste `tools:`** → l'agent ne pouvait jamais l'appeler. Le programmatic tool calling ne se déclenchait donc **jamais**. `run_tool_script` (+ `make_plan`/`update_plan_step`/`send_notification`, eux aussi mentionnés mais manquants) sont ajoutés aux outils d'Athena.
- **Couverture élargie** : le script peut maintenant appeler aussi les outils **read-only** d'inspection — `read_file`, `file_outline`, `search_code`, `find_definition`, `find_references`, `git_status/diff/log`, `query_graph`, `analyze_document`, `read_inbox`, `read_email` — en plus du web/mémoire/agenda. Un pipeline « lis 5 fichiers + agrège » devient **une seule inférence**.
- **Incitation renforcée** : le prompt de l'orchestrateur demande désormais explicitement de **préférer un seul `run_tool_script`** dès qu'une tâche enchaîne/agrège plusieurs appels d'outils (seule la sortie finale revient → grosse économie de contexte/tokens).
- Sûreté inchangée : validation AST, builtins restreints, pas d'écriture/shell/SSH/exec, timeout + budget d'instructions.
## v0.11.31 (install : pip dans le venv uv + libs système du vocal)

### 🐛 Correctifs d'installation
- **pip absent du venv** : `uv venv` n'installe pas pip → le wizard (`python -m pip`) et tout l'optionnel échouaient. Corrigé par **`uv venv --seed`** (pip/setuptools/wheel dans le venv) + filet `ensurepip` dans `setup_wizard.py` (robuste même sans `--seed`).
- **`requirements-voice.txt` qui échoue** : ajout de l'installation automatique des **libs système** requises avant le pip — **PortAudio** (sounddevice), **espeak-ng** (pyttsx3), **ffmpeg** (audio/whisper). `install_system_deps()` gère apt/dnf/pacman + root/sudo. Idem **ffmpeg** avant l'install de Whisper. Note ajoutée dans `requirements-voice.txt` pour l'install manuelle.
## v0.11.30 (install.sh viable sur système nu)

### 📦 Installateur robuste (conteneur LXC/Debian nu)
- **Bootstrap des paquets de base** : `install.sh` installe désormais lui-même `sudo`, `git`, `curl`, `gnupg`, les outils de build et les en-têtes Python — tout ce qui n'est pas garanti sur une base Debian/conteneur. Plus d'échec « git introuvable ».
- **Privilèges** : détection root/sudo (`SUDO=""` si root) → fonctionne dans un **conteneur lancé en root sans sudo**.
- **Python 3.13 via `uv`** : Debian livre 3.11 (→ vieux chromadb) ; l'installeur provisionne **Python 3.13** avec `uv` et crée le venv dessus (`uv venv --python 3.13`), sans toucher au python système. Dépendances via `uv pip install`.
- **Docker en méthode OFFICIELLE** : remplacement de `docker.io` (distro, ancien) par le script officiel **`get.docker.com`** (docker-ce + containerd), avec activation du service et ajout au groupe `docker`.
- SETUP.md aligné (one-liner + voie manuelle `uv`).
## v0.11.29 (Réglages SSH : retrait du legacy mono-hôte)

### 🧹 Nettoyage
- Retrait du bloc legacy **« Intégration Terminal SSH »** (hôte unique `.env` : SSH_HOST/PORT/USERNAME/PASSWORD/KEY_PATH) — redondant avec le registre multi-hôtes **par utilisateur** et incohérent avec son isolation (cet hôte était global).
- Le **mot de passe admin** (`ADMIN_PASSWORD`) est conservé mais déplacé sous une rubrique claire **« 🔒 Sécurité du cockpit »** (c'est l'admin de secours + garde-fou d'exposition réseau, sans rapport avec le SSH).
- Réglages → SSH ne montre donc plus que : la sécurité du cockpit, puis le bouton **« ＋ Ajouter un hôte SSH »** et la liste des hôtes (avec leurs autorisations).
## v0.11.28 (Réglages SSH épurés)

### 🧹 UI SSH simplifiée
- Réglages → SSH : un seul bouton **« ＋ Ajouter un hôte SSH »** déplie le formulaire (replié par défaut, et se referme après ajout), et la **liste des hôtes s'affiche en dessous** (avec leurs autorisations). Plus de formulaire encombrant en permanence.
## v0.11.27 (UI de partage SSH dans les Réglages)

### 🖥️ Gestion des autorisations dans Réglages → SSH
- Chaque hôte SSH (qui t'appartient) affiche désormais sa ligne **« Autorisé pour : »** avec les utilisateurs autorisés (puces retirables d'un clic) et un menu **« Autoriser »** (liste des utilisateurs) pour partager l'hôte — typiquement avec le **compte des satellites vocaux**.
- Les hôtes **partagés avec toi** par un autre utilisateur s'affichent en lecture (« partagé par … ») sans contrôles de partage.
- Branché sur les endpoints `POST/DELETE /api/ssh/hosts/{id}/share` (admin-only).

## v0.11.26 (SSH : isolation par utilisateur + partage)

### 🔐 Hôtes SSH privés par utilisateur
- Le registre SSH (hôtes **ET identifiants**) est désormais **strictement scopé par utilisateur** : un compte ne voit/n'utilise que SES hôtes. Fini le registre global partagé (dangereux). Migration douce de l'ancien registre vers l'admin.
- Conséquence : le **chat reste par utilisateur** (chaque session connectée pilote SES serveurs), et les **satellites vocaux** opèrent sous **un seul compte** (celui du `auth_token` de l'assistant vocal) → ses propres hôtes.

### 🤝 Partage autorisé (ex. satellites)
- Un propriétaire (admin) peut **autoriser un autre utilisateur** à utiliser un de ses hôtes (champ `shared_with`) — typiquement partager Immich/HA avec le **compte des satellites**.
- Un utilisateur voit alors **ses hôtes + ceux explicitement partagés avec lui** ; un hôte d'autrui n'est résolu QUE s'il a été partagé.
- Endpoints : `POST /api/ssh/hosts/{id}/share` et `DELETE /api/ssh/hosts/{id}/share/{username}` (admin-only).

## v0.11.25 (Agents : ciblage des serveurs SSH par leur nom)

### 🖧 « Va sur Immich » → l'agent trouve la machine seul
- Les agents de code peuvent désormais **cibler un serveur SSH par son nom** dans la demande (ex. « mets à jour Immich », « redémarre Home Assistant ») au lieu de dépendre uniquement du sélecteur d'hôte de la console.
- Nouvel outil **`list_ssh_hosts()`** : l'agent découvre les hôtes enregistrés (labels) puis exécute via `execute_bash_command(cmd, host="Immich")`.
- Résolution d'hôte **tolérante** (`find`) : correspondance exacte (id/label) **ou sous-chaîne unique** (« immich » → « VM Immich » ; ambigu → refus).
- La console Code expose la **liste des serveurs disponibles** dans le préambule de l'agent → il sait quelles machines il peut piloter, et peut **enchaîner plusieurs hôtes** dans une même demande.
- Garde-fous inchangés : registre SSH admin-only, sudo encadré, approbations pour les opérations sensibles.

## v0.11.24 (Design : sortie multi-fichiers css/js séparés)

### 🧩 Structure multi-fichiers (#5)
- La sortie HTML de Design est désormais **éclatée en fichiers séparés** dans `design/` : `index.html` + `style.css` + `script.js`, au lieu d'un unique HTML autonome (CSS/JS en ligne). On retrouve une structure de projet classique côté Code.
- Extraction native des `<style>`/`<script>` inline → fichiers dédiés, page reliée par `<link>`/`<script src>`. Les scripts **externes** (CDN) et types spéciaux (importmap, `application/json`) restent inline. Les fichiers obsolètes sont nettoyés si une nouvelle version n'en produit plus. L'aperçu continue de fonctionner (références relatives servies depuis le workspace).

## v0.11.23 (Design part du code existant)

### 🎯 Génération basée sur le projet ouvert (#5)
- **Design part désormais du CODE EXISTANT du projet** au lieu d'inventer une page générique sans rapport. À l'ouverture d'un projet ayant déjà du code (ex. importé ou créé côté Code), une demande de « variante / modernisation / refonte » conserve la structure, le contenu et les fonctionnalités réels de la page et applique les modifications dessus.
- Le générateur reçoit la **page d'entrée racine + ses CSS/JS compagnons** (bornés en taille pour maîtriser les tokens) via un nouveau paramètre `base_code`, injecté dans le prompt système comme « point de départ obligatoire ».
- Vérifié : sur un projet « Compagnons - Animaux », la régénération conserve le thème et le contenu (chien/chat/adoption…) au lieu de produire une landing page générique.

## v0.11.22 (Design : bascule « Code de base / Design »)

### 🔀 Voir le code d'origine OU la sortie Design (#5)
- Quand un projet a **à la fois un code de base** (racine, intact) **et une sortie Design** (`design/`), Design affiche un **sélecteur « Code de base / Design »** dans la barre d'outils du canvas pour basculer l'aperçu entre les deux.
- Résout le cas signalé : après une génération, on pouvait voir la variante mais **plus l'ancien code**. On peut désormais revenir au code d'origine à tout moment (lecture seule, jamais écrasé).
- Nouvel endpoint **`GET …/projects/{id}/sources`** → `{base, design}`.

## v0.11.21 (Design → Code : sortie dans un dossier dédié)

### 🔁 Pont bidirectionnel Design ↔ Code (#5)
- **Ce que Design génère devient un vrai fichier du projet, visible côté Code** — écrit dans un **sous-dossier dédié `design/`** (`design/index.html` pour le web, `design/design.py` pour Python).
- **Non destructif** : le **code de base à la racine n'est JAMAIS touché** (ex. un `index.html` écrit à la main ou par la partie Code reste intact). Un marqueur `.athenadesign.json` repère la sortie Design et la privilégie pour l'aperçu.
- Combiné à v0.11.20 (Design affiche les fichiers du Code), Design et Code partagent désormais le **même projet dans les deux sens**, proprement isolés.

## v0.11.20 (Design : aperçu des projets Code)

### 👁️ Aperçu des fichiers du workspace (#5)
- **Ouvrir un projet créé/édité côté Code dans Design affiche désormais sa page.** Si un projet n'a pas de « version » Design mais contient une page web dans son workspace (ex. `index.html`), Design la **prévisualise directement** (assets relatifs CSS/JS/images résolus dans le dossier du projet) et charge le code dans l'éditeur.
- Nouveaux endpoints : **`GET …/projects/{id}/workspace-entry`** (détecte la page d'entrée) et **`GET …/projects/{id}/workspace/{path}`** (sert les fichiers du workspace, anti-traversée). Boutons « Recharger » / « Ouvrir » adaptés au mode workspace.

## v0.11.19 (Import de dossier dans Design)

### 📁 Import d'un dossier complet (#9)
- Nouveau bouton **« Importer un dossier »** dans le panneau PROJETS de Design : importe un **dossier entier avec ses sous-dossiers** (`<input webkitdirectory>`) dans le projet ouvert.
- Les fichiers atterrissent dans le **workspace du projet — PARTAGÉ avec la partie Code** (#5) : ce qui est importé dans Design est immédiatement visible et éditable côté Code.
- Endpoint **`POST /api/athenadesign/projects/{id}/upload`** (multipart : `files` + `paths`). Sécurité : anti-traversée (chemins assainis, jamais hors du dossier projet), filtres (max 2000 fichiers, 50 Mo/fichier, exclusion auto de `.git`/`node_modules`/`__pycache__`/`.venv`/`dist`/`build`/`.next`).

## v0.11.18 (Hotfix console bash)

### 🐛 Correctif
- **Console Code** : `UnboundLocalError: cannot access local variable 'get_coder_cwd'` lors d'une commande bash (`$`/`!`, ex. `/ls`). Cause : `get_coder_cwd`/`get_workspace_dir` étaient importés LOCALEMENT dans `terminal_coder`, ce qui les rendait locaux à toute la fonction (référence avant assignation sur le chemin bash). Désormais importés au niveau module.

## v0.11.17 (Persistance des sessions longues + liste Design partagée)

### 🔁 Reprise après rechargement (#11)
- **Une tâche longue ne s'arrête plus si on recharge la page.** Le run ET sa finalisation (sauvegarde de la conversation + télémétrie) s'exécutent désormais dans un thread d'arrière-plan qui **survit à la déconnexion du client** : le résultat est déposé dans le registre de runs.
- Nouvel endpoint **`GET /api/chat/reconnect?run_id=…`** : au rechargement, le frontend se **reconnecte** au run en cours (run_id mémorisé en `localStorage`), relaie les dernières étapes + la réponse finale, puis recharge l'historique canonique.
- *Limite connue :* un **redémarrage du serveur** pendant un run reste non récupérable (registre en mémoire) ; un simple rechargement de page, lui, est désormais transparent.

### 🔗 Liste Design ↔ Code (#5, partiel)
- La liste des projets de **Design** est partagée avec celle du **Code** : elle se **rafraîchit automatiquement** à l'ouverture de l'onglet Design (via `postMessage`), pour refléter les projets créés côté Code.
- *Reste à faire :* unification du **stockage des fichiers** (Design écrit des « versions » d'artefacts, Code une arborescence de fichiers) — refonte d'archi distincte.

## v0.11.16 (Console code-only + slash-commands)

### 🧭 Console Code
- **Console réservée au code/SSH** : les actions de GESTION globales (suppression de compétence, de fait mémorisé, réinitialisation de l'essaim, mise à jour de config, clés d'API…) passent maintenant en **notifications (toasts)** au lieu de polluer le terminal de la console Code. La console n'affiche plus que ce qui concerne le code.
- **Slash-commands (façon Claude Code)** : `/help`, `/clear` (côté client), `/ls`, `/tree`, `/status`, `/diff` (→ bash), `/test`, `/run`, `/commit [msg]`, `/fix` (→ instruction au Codeur). `/help` liste tout ; un `/…` inconnu reste une commande bash directe (comme `$`/`!`).

## v0.11.15 (Console Code : délégation au domaine code)

### 🔧 Console Code
- **Délégation restreinte au domaine code** : la console reste sur le Codeur (`locked`) mais peut désormais **déléguer aux agents liés au code** (auditeur sécurité, debugger, SSH/déploiement, DevOps…) — jamais vers un agent non-code (Auteur, CommunityManager…) ni l'orchestrateur (qui généraliserait). Nouveau paramètre `delegate_allowlist` dans `swarm.run` (filtre `delegate_to_`/`transfer_to_` par liste blanche). Corrige le verrouillage trop strict de v0.11.14.

## v0.11.14 (Console Code verrouillée)

### 🔧 Corrections
- **Console Code** : verrouillée en « feuille » sur le Codeur (`locked` **+ `lock_delegation`**) → elle reste **100 % code** et ne part plus vers un autre agent. Avant, le Codeur pouvait `delegate_to_` un autre métier (Auteur, CommunityManager…), d'où une console qui se comportait en « généraliste ».

## v0.11.13 (Suppression de projets dans Design)

### 🎨 Design
- **Suppression de projets** : chaque projet du studio Design a maintenant un bouton 🗑️ (avec confirmation) qui supprime le projet et ses fichiers via le **registre unifié** (`DELETE /api/athenadesign/projects/{id}` → `core.projects.delete`). Avant, aucun moyen de supprimer un projet depuis Design.

## v0.11.12 (Visibilité des fichiers générés)

### 🔧 Corrections
- **Onglet Code** : l'explorateur de fichiers se **rafraîchit automatiquement** après qu'un agent a écrit/édité des fichiers (`write_file`, `edit_file`, `apply_patch`). Avant, les fichiers créés (ex. par le Codeur lors d'un « crée un site ») restaient **invisibles** jusqu'à un clic manuel sur « Actualiser ». Complète le fix v0.11.9 (le Codeur peut écrire) — les fichiers apparaissent maintenant tout seuls.

## v0.11.11 (Doc d'installation)

### 📦 Installation
- **SETUP.md** : recommande explicitement un **venv isolé en Python 3.13** (`python3.13 -m venv .venv`) pour éviter tout conflit avec d'anciennes dépendances système (ex. un vieux chromadb 0.5.x qui casse la mémoire), et de **lancer avec le python du venv** (pas le `python3` système).
- Documente l'installation **optionnelle** de `openai-whisper` (transcription de réunion + dictée vocale du chat — distinct du `faster-whisper` de l'assistant Jarvis) dans `SETUP.md` et `requirements-voice.txt`. Sans elle, la transcription bascule sur un LLM cloud si une clé est configurée.

## v0.11.10 (Robustesse des appels d'outils)

### 🐛 Robustesse
- **Appels d'outils tolérants** : si le modèle invente un nom de paramètre (ex. `write_file(file=…)` au lieu de `path=…`) ou ajoute un argument hors-signature, on mappe les alias sûrs (`file`/`filename`/`filepath`/`file_path` → `path`) et on **ignore** les arguments inconnus au lieu de planter (« unexpected keyword argument »). Filet complémentaire à l'exposition des schémas (v0.11.9).

> ℹ️ **Déploiement** : pour bénéficier des correctifs de dépendances (chromadb 1.5.9 qui répare `search_memory`/`store_document`, Playwright, etc.), lancer le serveur sur le **venv 3.13** : `.venv/bin/python server.py` (et non le `python3` système qui garde les anciennes deps).

## v0.11.9 (Fix majeur : le Codeur retrouve ses outils)

### 🐛 Correctif d'orchestration majeur
- **Le filtre d'outils ne s'applique plus qu'à l'orchestrateur.** Avant, il s'appliquait à **tout** agent ayant >20 outils — y compris le **Codeur** — et lui **masquait ses propres outils métier** (`write_file`, `edit_file`, `execute_bash_command`…). Ne voyant pas leur **schéma**, le modèle **inventait** de mauvais paramètres (`write_file(file=…)` au lieu de `path=…`) ou des outils inexistants (`run_shell_command`) → **toutes les écritures de fichiers échouaient**, et l'agent se rabattait sur `store_document` (code stocké en mémoire au lieu d'écrire les fichiers).
- **Conséquence corrigée** : un spécialiste (Codeur…) garde désormais **tous ses outils exposés** → il peut réellement créer/éditer des fichiers. C'était la racine des échecs « créer un site » et de plusieurs symptômes annexes.

## v0.11.8 (Correctif store_document)

### 🔧 Corrections
- **store_document** : ne plante plus avec « object of type 'int' has no len() » quand le contenu (ou la source) passé par le LLM est un nombre ou `None` — coercition en chaîne avant l'indexation chromadb.

## v0.11.7 (Sélecteur de listes dynamique)

### 🔧 Corrections
- **Listes** : le sélecteur affiche désormais **toutes** les listes existantes (peuplé dynamiquement via `/api/lists/names`). Avant, il était figé sur « Tâches » et « Courses » → une liste créée par un agent (ex. « **todo** », le nom exact demandé) restait **invisible** dans l'UI, alors que les éléments étaient bien enregistrés côté serveur. Complète le rafraîchissement auto de v0.11.6.

## v0.11.6 (Logs résilients & rafraîchissement des listes)

### 🔧 Corrections
- **Logs résilients au crash** : le tampon du panneau de logs est **préchargé depuis `logs/athena.log`** au démarrage → l'historique récent survit à un redémarrage / crash du serveur (plus de panneau vide).
- **Listes (TODO / courses / tâches)** : la vue se **rafraîchit automatiquement** après une action d'un agent (ajout / coche / suppression). Avant, l'élément était bien enregistré côté serveur mais l'UI restait figée — d'où l'impression que « rien n'était écrit ».

## v0.11.5 (Lot de corrections — statut, MAJ, dictée, délégation)

### 🏢 Open Space
- Statut par défaut **« Au repos »** (gris) ; seul l'agent **actif** est « Actif » — plus de pastille verte permanente sur tous les agents.

### 🔧 Corrections
- **Vérification de mise à jour** : échec **silencieux** quand le dépôt est privé/hors-ligne (URL corrigée + plus d'« Erreur de vérification : HTTP 404 » alarmante).
- **Dictée vocale dans le chat** : bascule automatique sur le **STT serveur** (Whisper, nouvel endpoint léger `/api/voice/transcribe`) quand l'API navigateur (Web Speech) est absente — marche désormais comme la Réunion (Firefox, etc.).

### 🤖 Orchestration
- Athena **annonce** désormais explicitement quand elle délègue/transfère (« Je confie ça à… ») et reste **cohérente** : déléguer par défaut, transférer seulement pour basculer durablement dans un métier.

## v0.11.4 (Finitions interface)

### 🧭 Interface
- Panneau **« Mon usage »** : ajout de la **moyenne tokens/req** (entre les tokens et le coût).
- **Top bar** : retrait du compteur d'agents (« x/8 ») à côté du coût — redondant maintenant que l'Open Space affiche tout l'effectif.
- Le **nom/logo est cliquable** → retour à l'accueil (Open Space).

## v0.11.3 (Relais par intention & finitions dock)

### 🤖 Orchestration (swarm)
- **Relais « par intention » (LLM) au lieu de mots-clés** : quand le modèle exprime un transfert en texte sans appeler l'outil, un petit juge LLM décide — d'après le **SENS** — s'il y a vraiment passage de main et **à qui**. Déclencheur **dynamique** (le message cite un agent réel, liste vivante) → marche pour **tout nouvel agent** (rôle imprévu), sans liste codée en dur. Fini les faux relais sur un mot du domaine (« l'auteur » = le malfaiteur) et les transferts fantômes.
- **Joignabilité réelle** : un relais ne vise qu'un agent que l'agent courant a le **droit** de joindre (`current_agent.tools`) — corrige « transfère à Julie » (que le routeur avait bridé) tout en bloquant les relais non configurés (Juriste→Auteur).
- **Règle de PÉRIMÈTRE** : un spécialiste reste dans **son** métier ; l'historique et la mémoire sont du **contexte**, pas sa mission → il ne propose plus le travail d'un autre agent (ex. Julie, juriste, ne propose plus de visuel de campagne récupéré de la mémoire/historique).

### 🧭 Dock — finitions
- Bouton **Logs** déplacé dans le footer du dock (entre Réglages et la version) — il ne chevauche plus le bouton d'envoi des prompts.
- **Sélecteur de langue** déplacé sous la version.

## v0.11.2 (Fiabilité de l'orchestration & finitions Open Space)

### 🤖 Orchestration (swarm)
- **Relais sémantique fiabilisé** — le swarm ne devine plus un transfert à partir de mots présents dans une **réponse longue** (« logement **social** », « l'**auteur** » = le malfaiteur, « demande à »…), qui provoquaient des relais absurdes (Juriste→Auteur, Athena→CommunityManager produisant une fiction/campagne hors-sujet). Désormais : **aucun relais deviné sur un message > 400 caractères** (une réponse complète n'est pas une intention de transfert), et un relais court ne vise qu'un agent **réellement joignable** (outil `transfer_to_`/`delegate_to_` présent).
- **Spécialiste ciblé par `@mention` → ne délègue plus** : il répond lui-même au lieu de rebondir vers un autre agent (l'orchestrateur Athena garde, lui, son rôle d'aiguilleur).
- **Présentation seulement à l'accueil** : sur une vraie question, l'agent répond directement au lieu de se contenter de se présenter (la phrase d'accueil n'est forcée que sur un message d'accueil).

### 🏢 Open Space — finitions
- **Plaque de nom posée sur le bureau** et plus compacte (au lieu de flotter et d'être masquée par le poste voisin).
- **Plus de lift z-index** sur le poste actif/survolé : le bureau de l'agent actif ne masque plus la tête des agents situés devant (profondeur isométrique conservée).
- **Métier déduit du rôle de l'agent** (= son nom : Juriste, Secretaire, Comptable…) et non plus de l'`avatar_type` — n'importe quel métier s'affiche tel quel, **sans liste codée en dur**. L'avatar reste choisi librement.

## v0.11.1 (Open Space 2.0 & refonte du dock)

### 🏢 Open Space 2.0 — bureau isométrique
- Le **Bureau Virtuel** est reconstruit en code : chaque agent a un **vrai poste isométrique** (siège + agent assis + bureau + double écran reflétant son métier), au lieu d'avatars flottant au hasard sur une image de fond. Clic sur un poste = focus + chat. Délégations animées d'un poste à l'autre. S'adapte de 1 à N agents.
- Intégration drop-in (`static/office.css` + `static/office.js`) ; ancienne balade aléatoire (`startOfficeWandering`) désactivée.
- **Correctif d'intégration** : `office.js` lit désormais le vrai binding `agentsConfig`/`currentActiveAgent` (des `let` globaux d'app.js, donc absents de `window`) + bootstrap robuste qui rend dès que les agents (chargés en async) arrivent — sinon l'ancien fond restait visible, sans postes.

### 🧭 Refonte du dock
- **Haut** : 5 onglets principaux — Accueil, Code, Design, Tâches, Réunions.
- **Bas** : les vues secondaires (Cockpit, Branches, Mémoire, Console, Orchestrateur) regroupées dans un menu **« … »** juste au-dessus des Réglages (ouverture vers le haut, hauteur limitée + scroll). **Version** déplacée tout en bas.
- Bouton **« Réinitialiser l'essaim » (🔄) retiré** du dock (binding JS sécurisé).
- Vue **Graphe retirée** du dock (jugée inutile ; panneau conservé mais non accessible).

### 🛡️ Scan de sécurité
- `security_scan.sh` exclut désormais le code tiers vendoré `tools/mcp-servers/ha-mcp` du scan bandit : **17074 → ~184 findings** (le reste = code Athena réel). Les 2 findings HIGH (subprocess Windows filtré, Paramiko opt-in) sont annotés `# nosec` avec justification.

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

### 🛡️ Sécurité des dépendances
- **Stack web relevée** pour corriger les CVE starlette : **fastapi 0.111 → 0.136.3**, **starlette 0.37.2 → 1.2.1**, **sse-starlette 2.1.3 → 3.4.4** (mcp 1.27.2 reste compatible ; l'ancien conflit de pins disparaît). Corrige CVE-2024-47874, CVE-2025-54121, PYSEC-2026-161.
- **python-dotenv 1.0.1 → 1.2.2** (CVE-2026-28684), **requests 2.32.3 → 2.34.2** (CVE-2024-47081, CVE-2026-25645), **Pillow 11.0.0 → 12.2.0** (5 CVE).
- pip-audit : **13 vulnérabilités → 1 restante**. La restante (chromadb CVE-2026-45829 « ChromaToast ») est **non applicable** à Athena : elle touche le serveur HTTP FastAPI de chromadb, alors qu'Athena utilise le client embarqué `PersistentClient` (in-process, non exposé). Pas de correctif amont à ce jour.

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
