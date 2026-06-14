# Historique des Versions (Changelog)

## v0.11.64 (Modèles Gemini listés en direct + diagnostic)

### 🔮 Liste Gemini DYNAMIQUE (corrige « modèle sélectionné mais ne fonctionne pas »)
- La liste des modèles Gemini était **statique** (3 noms codés en dur) : si ta clé n'autorisait
  pas ces noms précis (ex. `gemini-2.5-pro`), le modèle choisi renvoyait 404. Désormais
  `/api/config/models` interroge **l'API Google AI Studio** et propose les modèles RÉELLEMENT
  disponibles pour ta clé (comme OpenAI/Anthropic/OpenRouter).
- Ajout d'un script de diagnostic : `scripts/diag_gemini.py` (clé, modèles dispo, test litellm).


## v0.11.63 (Fix 500 à l'enregistrement d'un serveur MCP)

### 🐛 Fix : « Erreur » (500) en enregistrant un serveur MCP (dont Home Assistant)
- **Cause** : si `MCP_CONFIG_PATH` est **définie mais vide** dans l'environnement (ex. ligne
  `MCP_CONFIG_PATH=` dans `.env`), `os.getenv("MCP_CONFIG_PATH", "mcp_servers.json")` renvoyait
  une **chaîne vide** (et non le défaut) → `open('', 'w')` → `FileNotFoundError: ... ''` → 500.
- **Correctif** : `mcp_manager` retombe explicitement sur `mcp_servers.json` quand la variable
  est vide (helper `_resolve_config_path`, appliqué à l'init, au singleton et au restart).
- **Robustesse** : l'enregistrement d'un serveur MCP **reconnecte désormais en arrière-plan**
  (un serveur lent à joindre — ha-mcp/HA, npx absent — ne fait plus expirer la requête HTTP) et
  l'écriture de la config est protégée (message clair au lieu d'un 500 opaque).
- Test : `tests/test_mcp_and_agenda.py::test_config_path_never_empty`.


## v0.11.62 (Home Assistant : réparation auto de l'entrée périmée)

### 🏠 Fix : l'entrée HA gardait une URL `127.0.0.1:8099` qui faisait échouer la connexion
- Sur les installs existantes, l'entrée `home-assistant` du `mcp_servers.json` conservait un
  `"url": "http://127.0.0.1:8099/mcp"` (repli HTTP d'avant le build de ha-mcp). Or un `url`
  **prime** sur le STDIO → Athena se connectait dans le vide → « Erreur ».
- **Correctif** : `install.sh` et `update.sh` **réparent** désormais l'entrée HA (les 2 noms
  `home-assistant`/`homeassistant`) → forcent le **STDIO** (chemin du binaire ha-mcp), **retirent
  l'`url`/`transport`** périmés, et **conservent** `env` (HOMEASSISTANT_URL/TOKEN) + `disabled`.
- Pré-validation HA corrigée pour reconnaître aussi le nom `home-assistant` (avec tiret).
- ⟹ Après `./update.sh`, Home Assistant fonctionne en STDIO sans action manuelle.

## v0.11.61 (Home Assistant : construction automatique de ha-mcp)

### 🏠 Fix : Home Assistant tombait en repli HTTP (127.0.0.1) et ne marchait pas
- **Cause** : le serveur MCP intégré `ha-mcp` a besoin d'un binaire (`.venv/bin/ha-mcp`), mais ce
  `.venv` est un **artefact de build gitignoré** → absent d'un clone frais → Athena ne le trouvait
  pas et basculait sur un repli HTTP `http://127.0.0.1:8099/mcp` (service inexistant) → erreur de
  connexion.
- **Correctif** : `install.sh` ET `update.sh` **construisent désormais `ha-mcp`** s'il manque
  (venv dédié via `uv`, deps isolées d'Athena). Après mise à jour, l'entrée « Home Assistant
  (ha-mcp) — local » fonctionne en **STDIO** (URL + token longue durée), sans repli HTTP.
- **Note** : sur une install existante, relance `./update.sh` (ou `./install.sh`) pour déclencher
  la construction. Supprime puis ré-ajoute l'entrée Home Assistant si elle pointait encore sur
  `127.0.0.1`.

## v0.11.60 (Bot Telegram entrant)

### ✈️ Telegram : le bot répond enfin (entrant)
- Jusqu'ici, seules les **notifications sortantes** existaient : aucun listener ne lisait tes
  messages → le bot ne pouvait pas répondre. Ajout d'un **bot entrant** (`core/telegram_bot.py`) :
  long-polling natif (`getUpdates`, zéro dépendance), démarré automatiquement quand
  `TELEGRAM_BOT_TOKEN` est défini.
- **Sécurité** : appairage des contacts (un inconnu reçoit un code à approuver dans l'UI ou via
  `/approve <code>` depuis un chat autorisé ; les `TELEGRAM_CHAT_ID` sont autorisés d'office ;
  le 1er contact est auto-approuvé). Canal `telegram:<chat_id>` → shell/SSH déjà interdits.
- **Conversation** : contexte mémorisé par chat (borné). Commandes `/start`, `/help`,
  `/approve <code>`, `/reset`. Réponses découpées à la limite Telegram (4096).
- Statut du bot dans Réglages → Messageries (`GET /api/telegram/bot`). ⚠️ **redémarrage du
  serveur nécessaire** après avoir saisi le token.

## v0.11.59 (Intégration Nextcloud + OAuth/Gemini affinés)

### ☁️ Nextcloud (auto-hébergé) — Fichiers, Tâches, Contacts
- **Fichiers (WebDAV)** : `nextcloud_list_files` / `nextcloud_read_file` / `nextcloud_write_file` / `nextcloud_delete_file` (natif `requests`, anti-traversal, `can_write`).
- **Tâches (CalDAV VTODO)** : `nextcloud_list_tasks`. **Contacts (CardDAV)** : `nextcloud_search_contacts`.
- Config unifiée par utilisateur (URL + utilisateur + mot de passe d'application → URLs DAV dérivées) : `core/nextcloud.py`, router `routers/config_nextcloud.py` (`/api/config/nextcloud` + `/test`), section UI dans Réglages → Agenda. Donnés à la Secrétaire.
- **Allowlist anti-SSRF** (`NET_GUARD_ALLOW_HOSTS`) : autorise les services internes de confiance (Nextcloud/Home Assistant en IP privée), **éditable dans l'UI**. La métadonnée cloud reste toujours bloquée.

### 🔧 Affinages
- **Gemini** : un nom de modèle **nu** (`gemini-2.5-pro` sans préfixe `gemini/`) n'est plus routé par erreur vers l'endpoint custom quand la clé Gemini est présente.
- **OAuth Google** : le bloc « Connecter Google » est **toujours visible** avec des **champs pour saisir Client ID / secret / URI de redirection** directement dans l'UI (plus besoin d'éditer le `.env` à la main).

### ✅ Tests
- `tests/test_nextcloud.py`.

## v0.11.58 (OAuth Google + fiabilisation outils/MCP/agenda)

### ✨ OAuth Google (Calendar + Gmail), par utilisateur
- Connecte **ton** compte Google (consentement OAuth) pour que l'agent lise/écrive dans **ton** Google Calendar et lise **tes** mails Gmail — **sans partage de calendrier ni clé de compte de service**. Implémentation **native** (`requests` seul, zéro lib Google) : `core/google_oauth.py` (flux auth-code offline, refresh_token **par utilisateur**, state CSRF anti-rejeu, cache d'access_token).
- Endpoints `/api/oauth/google/status|start|callback|disconnect` (callback public, utilisateur résolu via le `state`). Bouton **« Connecter Google »** dans Réglages → Agenda.
- Agenda : token OAuth **prioritaire** (calendrier `primary` par défaut, aucun partage requis) avec repli sur le compte de service. Gmail **lecture seule** (`read_gmail`/`read_gmail_message`) câblé à la Secrétaire.
- Guide de mise en place : `docs/SETUP_GOOGLE_OAUTH.md` (⚠️ Google refuse une IP nue ; via domaine/Cloudflare Tunnel ou consentement unique en localhost).

### 🐛 Corrections (remontées à l'usage)
- **`get_time`** : réécrit avec `zoneinfo` (stdlib) au lieu de `pytz` (absent du venv → l'outil plantait). Ajout de `tzdata` aux requirements (images slim / venvs minimaux sans données IANA).
- **Sélection de modèles** : le préfixe UI `custom/` est retiré automatiquement (→ `openai/<modèle>`) ; un modèle à **préfixe provider explicite** (`gemini/`, `mistral/`, `groq/`, `openrouter/`…) reste en natif litellm et ne part **plus par erreur vers l'endpoint custom**. Corrige « Gemini sélectionné mais inutilisable » et l'obligation de retirer `custom/` à la main.
- **MCP Home Assistant** : les erreurs de connexion sont désormais **capturées par serveur** et exposées (incl. le **stderr** du sous-process → la vraie cause remonte, ex. « Missing HOMEASSISTANT_URL/TOKEN »). Pré-validation HA (message clair) + remontée de l'échec réel dans l'UI au lieu d'un faux « enregistré ✅ ».
- **Agenda Google** : la **suppression** d'événement ne renvoie plus 404 (l'id Google complet est conservé via `external_id` ; le handle local était tronqué à 16 caractères).

### ✅ Tests
- `tests/test_google_oauth.py`, `tests/test_mcp_and_agenda.py`.

## v0.11.57 (Vrai marketplace MCP — recherche en ligne)

### 🌐 Marketplace MCP dynamique (registre officiel)
- Jusqu'ici le marketplace n'affichait qu'un **catalogue local codé en dur**. Ajout d'une **recherche en ligne** dans le **registre MCP officiel** (`registry.modelcontextprotocol.io`) : tape un terme (notion, postgres, brave…) → la liste des serveurs publiés s'affiche, prête à installer.
- **Mapping automatique** vers une commande lançable : `npm`→`npx -y`, `pypi`→`uvx`, `oci`→`docker run`, ou serveur **distant** (`remotes` http/sse) avec URL + transport pré-remplis. Les variables d'environnement requises sont injectées dans le formulaire.
- Filtrage sur les serveurs **actifs / dernière version**. Host fixe de confiance (pas d'URL arbitraire → pas de SSRF), GET only, configurable via `MCP_REGISTRY_URL`.
- Le bouton « Installer » d'un résultat distant porte désormais bien **url + transport** (corrige aussi l'install des presets HTTP/SSE).
## v0.11.56 (Home Assistant en STDIO — géré par Athena, sans Docker)

### 🏠 ha-mcp piloté par Athena (auto-start / auto-restart)
- ha-mcp expose **le même jeu d'outils (84+) en STDIO** (`ha-mcp` = entrypoint stdio). On bascule donc l'intégration HA en **STDIO** : Athena le lance comme sous-process → il **démarre et se relance automatiquement avec Athena**, **plus besoin de Docker** ni de service HTTP séparé.
- **Marketplace dynamique** : l'entrée Home Assistant remplit automatiquement le chemin absolu du console-script `tools/mcp-servers/ha-mcp/.venv/bin/ha-mcp` s'il est installé (repli HTTP sinon). Il ne reste qu'à saisir `HOMEASSISTANT_URL` + un token longue durée.
- **install.sh** : injecte ce chemin absolu dans l'entrée `home-assistant` de `mcp_servers.json` (stdio, `disabled` tant que les identifiants ne sont pas remplis). `mcp_servers.json.example` passé en stdio.
- Rappel : `StdioServerParameters` n'a pas de `cwd` → on utilise le chemin **absolu** du console-script (shebang auto-suffisant vers son venv).
## v0.11.55 (Mise à jour depuis l'UI — fiabilisée)

### 🔁 Fix : « Mettre à jour » depuis l'interface
- `update.sh` est maintenant **systemd-aware** : si le service `athena-swarm` pilote Athena, on fait un `systemctl restart` propre (ou kill + `Restart=always` si pas de droits root) — **fini le conflit** entre le `nohup` du script et le redémarrage systemd qui se battaient sur le port 8000.
- La sortie de la mise à jour est journalisée dans **`update.log`** (l'endpoint répond avant la fin du script ; sans ce log, un échec de `git pull`/`pip`/restart était invisible côté UI).
## v0.11.54 (Liste des modèles agents — corrigée)

### 🐛 Fix : liste des modèles vide dans la config des agents
- **Cause racine** : l'endpoint `/api/config/models` lisait `.env` en chemin **relatif au cwd**. Lancé depuis un autre dossier (wrapper `athena`, nohup, ancien service), le `.env` n'était pas trouvé → aucune clé/endpoint détecté → liste vide. → Désormais `.env` est résolu aussi par **chemin absolu** (racine projet), + lecture de l'environnement live.
- **Endpoint custom plus robuste** : on tente plusieurs chemins (`/v1/models`, `/models`, `/api/models`, `/api/tags`) et plusieurs formats (`data`/`models`, `id`/`name`/`model`) → compatible vLLM / LM Studio / Open WebUI / LiteLLM / Ollama.
- **Jamais vide** : si rien n'est détecté au moment de l'appel, un court groupe « ⚡ Courants » de raccourcis est proposé (le champ reste en saisie libre).
## v0.11.53 (Démarrage auto au boot — Athena + MCP locaux)

### 🔁 Service systemd auto-configuré
- L'install **génère et active** (sur demande, défaut oui) le service systemd **`athena-swarm`** avec les **chemins/utilisateur réels** + `Restart=always` → **Athena démarre au boot et se relance en cas de crash**.
- Conséquence directe : les **serveurs MCP LOCAUX (stdio)** sont des **sous-process d'Athena** → ils **redémarrent aussi automatiquement** après un reboot, **sans rien lancer à la main**. (Avant : le service était suggéré mais codé en dur avec des chemins de dev.)
- Le service force `RELOAD=false` (pas de surveillant de fichiers → CPU/RAM au repos). Gestion : `systemctl {start,stop,status} athena-swarm`.
- Les MCP **distants (HTTP/SSE)** comme ha-mcp restent des services à part : lance-les via Docker `--restart unless-stopped` ou leur propre unité systemd pour le démarrage auto.
## v0.11.52 (MCP : ajout de serveurs HTTP/SSE par l'UI + Home Assistant corrigé)

### 🔌 Formulaire MCP : support url/transport
- **On ne pouvait ajouter que des MCP locaux (command/args/env)** via l'UI — pas de serveur **distant HTTP/SSE**. Le formulaire a désormais des champs **URL + Transport (http/sse)**, et l'endpoint `POST /api/config/mcp/servers` accepte `url`/`transport` (un serveur est soit local soit distant). Les presets/édition gèrent aussi ces champs.
- **Preset Home Assistant corrigé** : il pointait sur `uv run … ha-mcp` (= `ha_mcp.__main__:main`, qui lance un serveur **HTTP/OAuth**, pas du stdio → ne marchait pas en local). Il est désormais une entrée **HTTP** (URL `http://127.0.0.1:8099/mcp`) avec une note : lancer d'abord le service ha-mcp (uv/Docker/add-on HA, avec HOMEASSISTANT_URL+TOKEN), puis renseigner son URL.
## v0.11.51 (update.sh : bon venv, plus d'erreur externally-managed)

### 🔄 Correctif du script de mise à jour
- `update.sh` activait **`venv/bin/activate`** alors que le venv est **`.venv`** → l'activation échouait, `pip` tombait sur le **python système** → erreur **`externally-managed-environment`** (Debian/PEP 668). Désormais on utilise directement **`.venv/bin/python -m pip`** (jamais le python système).
- Le fallback de relance manuelle utilise aussi **`.venv/bin/python server.py`** (et non `python3` système, qui n'a pas fastapi).
## v0.11.50 (Diagnostic : « Vérification… » figé + bouton de mise à jour toujours dispo)

### 🔄 Mise à jour débloquée
- **« Vérification de la version » restait figé** : si `/api/system/update_check` renvoyait un non-200 (ex. 401 **avant login**), le front ne mettait jamais à jour le statut. Corrigé : (1) l'endpoint est rendu **public** (comme la version), (2) le front affiche désormais un statut **final dans TOUS les cas** (à jour / indisponible / erreur).
- **Bouton « Forcer la mise à jour » toujours disponible** dans le Diagnostic (il était caché quand aucune mise à jour n'était détectée → impossible de forcer). Tu peux maintenant lancer `git pull origin main` + redémarrage à tout moment.
## v0.11.49 (Liste de modèles : endpoint custom + fin de la liste inutile)

### 🧩 `/api/config/models` revu
- **Modèles de l'endpoint CUSTOM enfin listés** : interrogation robuste de `CUSTOM_LLM_API_BASE` (essaie `/v1/models` ET `/models`, timeout 5 s, gère les formats `{data:[…]}` ou liste brute) → tes modèles apparaissent en tête (« ⭐ Serveur Custom »). (Corrige aussi un bug où les 2 branches d'URL étaient identiques.)
- **Fin de la longue liste inutile** : le catalogue statique d'un fournisseur cloud (OpenAI/Anthropic/Gemini/Groq/Mistral/OpenRouter) n'est désormais affiché **que si sa clé API est configurée**. Avec seulement ton endpoint custom → tu ne vois **que tes modèles**. Listes live (OpenAI/Anthropic/OpenRouter) seulement si clé ; Ollama seulement si joignable.
## v0.11.48 (Installs fraîches : version affichée + config MCP/Home Assistant)

### 🔧 Correctifs « nouvelle install »
- **Version bloquée à « v0.0.0 »** : `/api/system/version` était derrière l'auth → sur une install avec mot de passe, le front l'appelait AVANT login (401) et n'affichait jamais la vraie version. L'endpoint (non sensible) est désormais **public** → la version s'affiche, y compris sur l'écran de connexion.
- **Aucun serveur MCP sur une install fraîche** (dont Home Assistant) : `mcp_servers.json` est gitignoré et n'était pas créé. L'install le **génère maintenant depuis `mcp_servers.json.example`**, qui inclut une **entrée `home-assistant`** (désactivée, documentée). Les serveurs sont `disabled` par défaut → à activer dans Réglages → MCP.
- ℹ️ Le MCP Home Assistant (`tools/mcp-servers/ha-mcp`) est un **service HTTP à lancer séparément** (Docker / add-on HA / uvx, avec `HOMEASSISTANT_URL`+`TOKEN`) ; une fois lancé, renseigne son URL et passe `disabled` à false.
## v0.11.47 (Serveur : reload désactivé par défaut — fin du CPU à vide)

### 🐌→⚡ CPU élevé au repos corrigé
- `server.py` lançait uvicorn avec **`reload=True` codé en dur** : le surveillant de fichiers scanne tout l'arbre (`.venv`, `.chroma_db`, `athena_projects`…) → **CPU saturé EN PERMANENCE**, même serveur au repos.
- `reload` est désormais **gouverné par `RELOAD`** (défaut **false**, sain pour un déploiement). En dev, `RELOAD=true` réactive le rechargement auto — limité aux dossiers de code (`core/routers/tools/voice`, `*.py`) pour ne pas pomper le CPU.
## v0.11.46 (Install vocale : resemblyzer optionnel)

### 🔧 Correctif
- **L'install vocale bloquait sur `webrtcvad`** : c'est une dépendance de **`resemblyzer`** (reconnaissance du locuteur), un module C qui doit se **compiler** → long/bloquant sur petite machine (LXC) sans build tools, et resemblyzer tire en plus **PyTorch** (lourd). Or il ne sert qu'à *identifier qui parle*, **pas** au wake word / STT / TTS. → **`resemblyzer` est désormais commenté (optionnel)** dans `requirements-voice.txt`, avec la note pour l'activer (build-essential + python3-dev). L'install vocale de base passe sans compilation.
## v0.11.45 (Entraînement d'un wake word openWakeWord « athena »)

### 🏋️ Pipeline d'entraînement `athena.onnx`
- Ajout de `tools/train_wakeword/` : config (`athena.yaml`), script (`train_athena_wakeword.sh`) et README pour entraîner un **modèle openWakeWord custom « athena »** — la voie efficace/always-on (alternative au mode `stt` par transcription), utile pour les satellites multi-flux.
- Suit le **pipeline officiel openWakeWord** : positifs synthétiques (Piper) + bruit/réverbération + négatifs pré-calculés → DNN → `athena.onnx`. README avec 2 voies (Colab officiel, ou script local GPU) + déploiement dans Athena (`VOICE_WAKE_ENGINE=openwakeword` + `VOICE_WAKE_WORD=athena`).
- ⚠️ Nécessite un GPU (Colab) ; honnêtement non testé sans GPU/datasets — le notebook officiel reste la référence.
## v0.11.44 (Satellites ESP : wake word côté serveur par défaut)

### 🛰️ Wake word serveur pour les satellites ESP
- Le générateur de config ESPHome passe en **`mode: server` par défaut** (au lieu de `embedded`/micro_wake_word) : l'ESP **streame en continu**, c'est **Athena** qui détecte le mot d'activation. Cohérent avec l'architecture décidée (pas de micro_wake_word on-device).
- Le moteur côté serveur suit **`VOICE_WAKE_ENGINE`** (« stt » par défaut → mot custom « athena » par transcription ; « openwakeword » pour un modèle efficace). Commentaires de la config corrigés (n'imposent plus « openWakeWord »).
## v0.11.43 (Wake word « Athena » par transcription, défaut cohérent)

### 🗣️ Mot d'activation custom (« Athena ») fonctionnel par défaut
- **Combo par défaut cassé corrigé** : le défaut était `openwakeword` + `hey athena`, or openwakeword ne connaît QUE des mots **pré-entraînés** (alexa, hey_jarvis…) — **pas « athena »** → dire « Athena » ne déclenchait rien.
- **Nouveau défaut : `VOICE_WAKE_ENGINE=stt`** → détecte le mot custom (« athena » + variantes) en **transcrivant une fenêtre glissante** (faster-whisper), sans aucun modèle. Marche immédiatement pour « Athena ».
- `.env.example` documente enfin l'option **`stt`** + le caveat openwakeword (mots pré-entraînés) + `OWW_INFERENCE_FRAMEWORK`.
- Pour l'efficacité (satellites / always-on) : openwakeword reste dispo avec `hey_jarvis`, ou un modèle custom « athena » à entraîner.
## v0.11.42 (openwakeword compatible Python 3.13 — backend ONNX)

### 🎙️ Wake word sur Python 3.13
- **openwakeword échouait** : son `install_requires` force `tflite-runtime`, qui n'a **aucun wheel pour Python ≥3.10** (dont 3.13) → l'install du pipeline vocal entier avortait. Or openwakeword tourne aussi en **ONNX** (onnxruntime a des wheels 3.13).
- **Fix** : `setup_wizard.py` installe openwakeword **à part** (`--no-deps` + onnxruntime/scipy/scikit-learn) puis **télécharge les modèles** ; le runtime (`voice/wakeword.py`) utilise désormais **`inference_framework='onnx'`** par défaut (surchargeable via `OWW_INFERENCE_FRAMEWORK`).
- **Install vocale résiliente** : `requirements-voice.txt` s'installe paquet par paquet en cas d'échec groupé (un paquet incompatible n'avorte plus tout le vocal). openwakeword retiré du fichier (géré spécialement, recette documentée dedans).
- Vérifié de bout en bout sur Python **3.13** : import OK, modèles téléchargés, `Model(onnx)` → wakewords (alexa, hey_jarvis, hey_mycroft…).
## v0.11.41 (Install interactive sous curl|bash + accès distant + marque)

### 🔧 Correctifs d'installation
- **Wizard non interactif sous `curl | bash`** (CAUSE COMMUNE) : stdin était occupé par le script piped → aucun prompt → ni optionnels, ni `requirements-voice`, ni `requirements-observability`, ni mot de passe. Le wizard **lit désormais sur `/dev/tty`** → il redevient interactif malgré le pipe (et `install.sh` lit aussi ses prompts Ollama sur `/dev/tty`). Repli propre si aucun terminal.
- **Accès distant + mot de passe** : le wizard demande explicitement **Local (127.0.0.1) vs Réseau (0.0.0.0)** ; en réseau, l'**`ADMIN_PASSWORD` devient obligatoire** (le serveur refuse de démarrer exposé sans lui) et `HOST` est réglé en conséquence.
- **Marque** : bannière ASCII corrigée — elle épelait « ATUENA » (U au lieu du H) → bannière texte **ATHENA** simple et sûre.
## v0.11.40 (Correctifs d'installation)

### 🔧 install.sh utilisable de bout en bout
- **Commande `athena` introuvable** : le CLI était posé dans `~/.local/bin` (hors PATH sur une base nue). Désormais installé dans **`/usr/local/bin`** quand on est root (conteneur LXC, déjà sur le PATH) ; sinon `~/.local/bin` **ajouté durablement au `.bashrc`/`.zshrc`** + activé pour la session.
- **`python server.py` → fastapi introuvable** : fastapi vit dans le `.venv`. Message explicite (lance **`athena start`** ou **`.venv/bin/python server.py`**, JAMAIS le python système) + **vérification finale** que fastapi est bien présent dans le venv.
- **Composants optionnels non proposés** (install via `curl|bash` = non interactif) : message indiquant comment relancer le wizard (`source .venv/bin/activate && python setup_wizard.py`).
- **Marque** : suppression du logo ASCII et des mentions « Jarvis/Athena v2 » résiduels → bannière « ATHENA » propre.
## v0.11.39 (Playbooks Markdown — « Agent Skills » procéduraux)

### 📓 Savoir-faire procédural (complément des skills Python)
- Nouveau type de compétence : **playbooks Markdown** (`playbooks/*.md`) — du **savoir-faire** (procédures, checklists, conventions « comment faire X »), complément des skills Python qui, eux, **calculent**.
- **Disclosure progressive** (économie de tokens) : un **index compact** (nom + description) est toujours visible dans le contexte ; le **corps complet** n'est chargé qu'à la demande via l'outil **`load_playbook(name)`** quand un playbook est pertinent.
- Frontmatter optionnel (`name:` / `description:`). `load_playbook` n'est exposé que si au moins un playbook existe. Index injecté dans le préfixe **stable** (cacheable). Dossier configurable via `PLAYBOOKS_DIR`. Un exemple fourni (`deployer-site-statique.md`).
## v0.11.38 (Création de compétences « propre », sans bruit)

### 🧬 Induction de skill seuillée
- L'acquisition automatique de compétences se déclenchait dès **un seul** appel d'outil → la bibliothèque se remplissait de **bruit** (skills triviales). Désormais elle ne se déclenche que pour des tâches **SUBSTANTIELLES**, l'un de ces critères suffisant :
  - **≥ `SKILL_MIN_TOOL_CALLS` appels d'outils** (défaut **5**),
  - une **récupération d'erreur** (un outil/skill a échoué puis le run a continué),
  - une **correction** (passe auto-critique déclenchée, ou l'utilisateur corrige explicitement).
- Les tâches triviales à une étape ne génèrent plus de skill. Réglable via `SKILL_MIN_TOOL_CALLS`.
## v0.11.37 (RAG sobre — #6, fin de la roadmap efficacité)

### 🔎 RAG sobre (#6)
- Le **RAG automatique en arrière-plan** (chunks mémoire pré-injectés) tournait et se ré-injectait **à CHAQUE tour** de la boucle agentique (alors que le message utilisateur ne change pas) → re-recherche + re-paste des mêmes chunks inutiles. Désormais **injecté UNE seule fois par run** ; si l'agent a besoin de re-chercher, il a l'outil `search_memory`.
- Top-k déjà minimal (2) ; nouveau knob **`RAG_BACKGROUND_TOPK`** (défaut 2 ; **0 = désactive le RAG auto** → 100 % via `search_memory`, le mode le plus sobre).

### ✅ Roadmap efficacité tokens — complète
1 Programmatic tool calling · 2 Disclosure progressive skills/MCP · 3 Prompt caching · 4 Discipline du swarm · 5 Compaction + éviction · 6 RAG sobre — **tous traités**.
## v0.11.36 (Éviction des gros résultats d'outils — #5)

### 🗜️ Compaction + éviction (#5 de la roadmap efficacité)
- **Déjà en place** : `_maybe_compact` résume les anciens messages et garde les K récents verbatim (vue LLM seulement). Au passage, son **résumé** passe maintenant par le petit modèle (`UTILITY_MODEL`/`FAST_MODEL`).
- **Ajout — éviction des gros résultats** : un résultat d'outil volumineux (> `EVICT_TOOL_RESULT_MAX`, 2000 par défaut) qui n'est plus dans les `EVICT_KEEP_RECENT` derniers messages (donc **déjà exploité** par le modèle) est remplacé par un **extrait tête/queue + un pointeur** au lieu de retrimballer tout le payload à chaque tour. Les résultats récents restent intacts ; agit même si l'historique est court mais contient un gros payload. N'affecte **jamais** l'historique persistant. `EVICT_TOOL_RESULT_MAX=0` désactive.
## v0.11.35 (Discipline du swarm — tiering des appels utilitaires)

### 🧠 #4 de la roadmap efficacité (audit + complément)
- **Déjà en place (confirmé par audit)** : les sous-agents renvoient un **résultat distillé** (réponse finale + métriques), jamais leur transcript complet — vrai pour `delegate_to_` ET `query_agent`. Tiering par difficulté (`_route_model`/`FAST_MODEL`) et mini-routeur/juge de relais utilisent déjà le petit modèle. Débats inter-agents = opt-in.
- **Ajout** : nouveau knob **`UTILITY_MODEL`** pour les appels LLM **utilitaires** (jugement/extraction/classification : induction de compétence, relecture critique) → un petit modèle suffit. Priorité `UTILITY_MODEL` > `FAST_MODEL` > modèle de l'agent. Appliqué à l'induction de compétence et au relecteur critique (auto-critic).
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
