# Historique des Versions (Changelog)

## [0.24.4] - 2026-06-18
### Fix — traductions UI manquantes (Proxmox, Vigie, Réglages…)
- 5 libellés ajoutés récemment n'étaient traduits dans AUCUNE langue → s'affichaient en français pour les utilisateurs en/es/it/de/zh/ja : `dock.logs`, `dock.redaction` (Écriture), `dock.settings` (Réglages), `tab.events` (👁️ Vigie), `tab.proxmox` (🖧 Proxmox).
- Complétés dans les **6 langues** de `static/i18n.js`. Couverture des clés `data-i18n` du HTML : 100 % par langue.


## [0.24.3] - 2026-06-18
### Perf/refactor — transcription unifiée sur UN moteur partagé et caché
- Nouveau `core/transcription.py` : **un seul** modèle STT en mémoire, chargé **une fois** (thread-safe), réutilisé par la dictée du chat (`/api/voice/transcribe`), la transcription de réunion (`/api/meeting/transcribe`) et l'outil `transcribe_and_summarize_meeting`. Fini les deux caches séparés (~140 Mo ×2) et tout `load_model` direct.
- **Moteur préféré : faster-whisper** (CTranslate2, INT8 — le même que les satellites : plus rapide, plus léger), **repli openai-whisper** s'il est absent → aucune install existante cassée. Langue auto, réglages partagés (`VOICE_STT_MODEL/DEVICE/COMPUTE/LANGUAGE`).
- Cohérence docs/deps : `requirements.txt` et `requirements-voice.txt` mis à jour (faster-whisper = moteur de transcription par défaut, openai-whisper = repli optionnel). `install.sh`/`update.sh` inchangés (voix optionnelle, hors install de base — volontaire).


## [0.24.2] - 2026-06-18
### Perf — hooks d'apprentissage post-run en ARRIÈRE-PLAN (latence)
- Les hooks passifs de fin de run (Chronos/graphe, retour d'expérience, induction de skill, profil utilisateur, réparation de skill) faisaient **2-4 appels LLM dans le chemin critique** : la réponse était déjà streamée, mais le run restait « occupé » plusieurs secondes (voyant, enchaînement, worker bloqué).
- Désormais ils s'exécutent dans un **thread d'arrière-plan** (contexte/identité propagé via `copy_context` → Chronos écrit dans le bon compte) ; **`run()` rend la main dès la réponse finale**. Gain net surtout en vocal et en enchaînement rapide.
- `_auto_critic` reste SYNCHRONE (il modifie la réponse ; OFF par défaut). Désactivable globalement via `ASYNC_POST_HOOKS=false` (revient à l'ancien comportement synchrone).


## [0.24.1] - 2026-06-18
### Feat — routeur de DÉLÉGATION sémantique (zéro appel LLM) + auto-continuation affinée
- **`core/agent_router.py`** remplace l'ancien « juge LLM » de `_route_target` (un appel de complétion EN PLUS à chaque run : lent, facturé, biaisé « aucun », limité au dernier message). Désormais : **similarité d'embeddings** requête (3 derniers messages user) ↔ description des agents, via l'embedder partagé (bge-m3 → all-MiniLM local). **Instantané, multilingue, zéro LLM.**
- **Décision à 3 niveaux** (évite de pénaliser l'ambigu) : match franc (plancher + écart net) → délègue ; rien de pertinent (chit-chat) → l'orchestrateur répond ; pertinent mais ambigu (ex. deux agents techniques) → **ne restreint pas**, l'orchestrateur garde `delegate_to_` et tranche lui-même. Réglables : `DELEGATION_ROUTER_MIN` (0.50), `_GAP` (0.04), `_GENERAL` (0.45).
- **Auto-continuation** : ne se déclenche plus sur un COMPTE-RENDU (« voici ce que j'ai trouvé… », « c'est fait », « résultat : ») — uniquement sur une vraie intention future. Évite de relancer une action déjà exécutée.


## [0.24.0] - 2026-06-18
### Feat — routage d'outils SÉMANTIQUE & MULTILINGUE (fini les mots-clés rigides)
- Nouveau `core/tool_router.py` : sélectionne les outils à exposer par **similarité d'embeddings** (requête ↔ nom+docstring), donc **indépendant de la langue** — « enciende la luz » (ES), « accendi la luce » (IT) activent la domotique, là où les mots-clés FR/EN codés en dur étaient à la ramasse.
- **Réutilise l'embedding déjà en place** (`core.memory`) : **bge-m3** via endpoint si configuré (multilingue, idéal), sinon **all-MiniLM** local de ChromaDB. **Zéro nouvelle dépendance** (numpy + chromadb déjà présents).
- **Stratégie robuste** : sélection par **écart-au-meilleur** (pas de seuil absolu fragile) + **UNION avec le routage mots-clés** → le keyword garde la précision FR/EN (« git commit »), le sémantique ajoute le multilingue ; on ne manque jamais un outil (sur-exposer ne coûte que des tokens).
- **Replis en cascade** : bge-m3 → all-MiniLM local → mots-clés. **Disjoncteur** : si l'endpoint embed tombe, bascule keyword instantanément (pas de timeout à chaque tour). Réglables : `TOOL_ROUTER=semantic|keyword`, `TOOL_ROUTER_GAP` (0.06), `TOOL_ROUTER_COOLDOWN` (300 s).
- Sûreté inchangée : outils cœur toujours exposés ; le filtre ne touche que le SCHÉMA, jamais l'exécution.


## [0.23.9] - 2026-06-18
### Fix — une intégration CONFIGURÉE n'est plus rendue invisible par le filtre
- Les outils Proxmox/mail sont auto-injectés quand l'intégration est configurée, MAIS le filtre par mot-clé les masquait quand la requête n'en contenait pas (« pourquoi *immich* est tombée » → aucun mot « vm/proxmox » → Athena se croyait sans outils Proxmox, alors qu'elle voyait l'état des VM dans d'autres phrases). Désormais : **une capacité configurée est TOUJOURS exposée** (jamais masquée par le filtre de pertinence).
### Feat — `proxmox_vm_logs(vmid)` : pourquoi une VM est tombée
- Nouvel outil (lecture seule) listant les dernières **tâches Proxmox** d'une VM/CT (démarrage, arrêt, extinction, sauvegarde, erreurs) avec qui/quand/résultat → distingue un arrêt **manuel** (`qmstop` par un user) d'un **crash/échec** (tâche en erreur) ou d'une extinction interne. Marche même VM **éteinte** (contrairement à `proxmox_vm_exec`/`journalctl` qui exige la VM allumée).


## [0.23.8] - 2026-06-18
### Feat — Home Assistant : noyau d'outils garanti + découverte de TOUS les outils
- **Noyau fondamental toujours exposé** sur une intention HA : `ha_entities`, `ha_search_entities`, `ha_get_state`, `ha_get_entity`, `ha_devices`, `ha_call_service`, `ha_get_overview`, `ha_deep_search`… (avant, Athena voyait les pièces mais pas les entités, faute du bon outil dans le top-N).
- **Nouvel outil natif `list_mcp_tools(query)`** : toujours disponible dès qu'un serveur MCP est connecté. Athena peut **chercher dans les 77 outils HA** (par mot-clé : « entité », « camera », « light »…) un outil non affiché, puis **l'appeler par son nom** — il s'exécute même hors schéma (`_secured_tools`). Répond au besoin « inclure le noyau, et si l'outil voulu n'y est pas, chercher dans tous les outils HA ».
- **Échappatoire** `TOOL_HA_TOPN=0` : expose TOUS les outils HA à chaque requête HA (zéro risque, coût en tokens).


## [0.23.7] - 2026-06-18  — CAUSE RACINE du « pas d'outils MCP/HA »
### Fix — server.py ne démarrait JAMAIS les serveurs MCP
- Le service systemd lance `server.py`, or le `mcp_manager.start()` avait disparu de `server.py` lors de son refactoring (il ne restait que dans `main.py`, non utilisé par le service). Résultat : en prod, **aucun serveur MCP ne démarrait** → `tool_functions()` vide → l'essaim n'avait AUCUN outil MCP (les 77 outils Home Assistant notamment), et le panneau MCP affichait tout en rouge. Un script lancé à la main (`diag_mcp.py`) connectait HA dans SON process, masquant le problème.
- `server.py` démarre désormais les serveurs MCP au boot (comme Telegram et le moniteur Proxmox). Combiné à v0.23.6 (exposition des outils HA à l'essaim), Home Assistant est pleinement fonctionnel.

## [0.23.6] - 2026-06-18
### Fix — Athena « ne voit pas » les outils Home Assistant (MCP)
- Les 77 outils du serveur MCP HA portent des noms ANGLAIS (`ha_*`) ; le filtre de pertinence (qui borne les outils « extra ») ne les faisait remonter QUE si un mot-clé domotique FR précis était présent, et seulement « les 12 premiers » (ordre arbitraire). Résultat : « regarde ce qui est dispo sur HA », « liste mes entités », « regarde le mcp » → **0 outil HA exposé** → Athena répondait n'avoir que `get_ha_state`/`call_ha_service`, alors que le serveur MCP HA était **bien connecté** (diagnostic `scripts/diag_mcp.py`).
- **Détection HA élargie** : domotique OU mention explicite (home assistant, mcp, entité, maison, capteur, interrupteur, scène, `\bha\b`…). Les outils HA sont alors classés **par pertinence puis complétés** jusqu'à `TOOL_HA_TOPN` (défaut 25) — une requête FR de découverte obtient enfin un jeu d'outils utilisable. Aucun bruit HA sur les requêtes agenda/email/heure.


## [0.23.5] - 2026-06-18  — HOTFIX CRITIQUE
### Fix — chat & Telegram muets : « 'module' object is not callable »
- La phase 4 du découpage avait créé le sous-module `core/swarm/completion.py`. Or `core.swarm.completion` était AUSSI l'attribut où `__init__` exposait la fonction `completion` de litellm (point monkeypatchable). L'import du sous-module **écrasait** la fonction → la couche LLM appelait un *module* (`'module' object is not callable`) → **tous** les appels LLM échouaient (chat web ET Telegram muets).
- Sous-module renommé **`core/swarm/llm.py`** : plus de collision, `core.swarm.completion` redevient la fonction litellm. Régression introduite en v0.23.3, présente en v0.23.3/0.23.4.


## [0.23.4] - 2026-06-18
### Fix — Home Assistant : doublon d'entrée MCP qui cassait le token
- Au fil des presets, le serveur HA a porté DEUX noms (`home-assistant` historique puis `homeassistant`). Quand les deux coexistent dans `mcp_servers.json`, ils exposent les mêmes outils : le second chargé **écrase** le premier → si son token est vide/périmé, tous les appels HA partent sur la mauvaise entrée et échouent (« le mot de passe HA ne fonctionne plus »).
- **Auto-réparation** : `mcp_manager` fusionne désormais les doublons en UNE seule entrée canonique `homeassistant`, en conservant le token le plus exploitable (non vide, puis le plus long). Idempotent (no-op s'il n'y a pas de doublon).
- `update.sh` applique la même fusion **sur le fichier** (en plus de forcer le STDIO), pour nettoyer durablement la config.


## [0.23.3] - 2026-06-18
### Refactor — découpage `core/swarm` (phase 4 : complétion + routage)
- **`core/swarm/completion.py`** (`_CompletionMixin`) : `_complete`, `_complete_streaming`, `_maybe_continue` (auto-continuation des réponses tronquées), `_apply_prompt_cache`, `_route_target` (aiguillage vers un spécialiste), `_route_model` (modèle rapide/fort), `_utility_model`. Le helper `_completion` (indirection monkeypatchable `core.swarm.completion`) y est rapatrié.
- `engine.py` : 2108 → **1729 lignes** (contre ~3050 au départ). Il ne reste que `__init__`, la boucle `run`, le cache d'outils, `_push_approval_notice`, `SwarmStepsList` et `AVAILABLE_TOOLS`.
- Bilan du package : `engine` 1729 · `completion` 399 · `learning` 340 · `text_tools` 294 · `agents` 185 · `schema` 165 · `context` 90 · `__init__` 50.
- Iso-comportement (suite complète OK ; seuls `test_memory`/`test_claude_code` échouent, à l'identique de `main` — préexistants).


## [0.23.2] - 2026-06-18
### Refactor — découpage `core/swarm` (phase 3 : essaim + contexte) + correctif chemin
- **`core/swarm/agents.py`** (`_AgentsMixin`) : `load_agents`, `create_handoff_function`, `create_delegate_function`.
- **`core/swarm/context.py`** (`_ContextMixin`) : `_maybe_compact` (compaction d'historique) + `_evict_large_results` (éviction des gros résultats d'outils). N'altèrent que la vue LLM.
- `engine.py` : 2343 → 2108 lignes.
- **Correctif** : `load_agents` résolvait `agents.default.yaml` au mauvais endroit depuis le passage en package (régression du chemin basé sur `__file__`, visible uniquement au TOUT premier install) → racine projet désormais résolue explicitement.
- Iso-comportement (tests OK ; `test_agent_tools`/`test_delegation` qui exercent ces méthodes passent).


## [0.23.1] - 2026-06-18
### Refactor — découpage `core/swarm` (phase 2 : apprentissage)
- Les 6 hooks d'auto-amélioration post-tâche sortent d'`engine.py` vers **`core/swarm/learning.py`** (`_LearningMixin`, mélangé à `Swarm`) : `_write_experience_report`, `_extract_graph_facts` (Chronos), `_update_user_profile`, `_improve_skills`, `_auto_critic`, `_induce_skill`.
- `engine.py` : 2652 → 2343 lignes. Iso-comportement (tests cœur + `test_skill_induction` OK).


## [0.23.0] - 2026-06-17
### Refactor — `core/swarm.py` découpé en package (phase 1)
- L'ancien module monolithique (~3050 lignes) devient le **package `core/swarm/`** :
  - `engine.py` : la classe `Swarm` (boucle `run`, routage, complétion, apprentissage) + `AVAILABLE_TOOLS` ;
  - `schema.py` : conversion fonction→schéma d'outil + coercition/validation des arguments ;
  - `text_tools.py` : sélection d'outils par pertinence, récupération de tool-calls écrits en texte, détection d'intention annoncée, skills dynamiques ;
  - `__init__.py` : **ré-exporte l'API publique historique** → tout `from core.swarm import …` existant fonctionne à l'identique.
- Contrat de test préservé : `core.swarm.completion` reste monkeypatchable (le moteur l'appelle via le namespace du package) ; `_TOOL_CACHE`, `_delegate_depth`, `DELEGATE_BLOCKED_TOOLS` ré-exportés.
- **Iso-comportement** : tous les tests qui passaient passent toujours (les 2 échecs restants — `test_memory`, `test_claude_code` — préexistaient sur `main`).


## [0.22.1] - 2026-06-17
### Fix — l'échafaudage interne ne fuit plus dans la conversation
- L'**auto-continuation** (« tu viens d'ANNONCER une action… »), l'**auto-correction de tool-call** et les **relais système** étaient écrits dans la conversation visible : on voyait le message d'intention de l'agent ET la consigne système affichée comme un message « Vous ». Désormais ces messages sont marqués `_internal` : conservés dans le contexte du modèle le temps du run, mais **jamais affichés ni persistés** (filtrés à la finalisation, retirés de la copie envoyée au LLM).
- Supprime au passage le **doublon** du message d'intention (« Je vais… ») qui était ré-ajouté inutilement.


## [0.22.0] - 2026-06-17
### Robustesse multi-worker (suite à revue de code)
- **Migration JSON→SQLite rendue ATOMIQUE** (`shared_store.migrate_json_dict`) : réservation via `update`/`BEGIN IMMEDIATE` → plus de double-migration ni de doublons en multi-worker ; en cas d'échec, le verrou est relâché (réessai sûr).
- **`telegram_pairing` → store SQLite partagé** (fini le `telegram_paired.json` corruptible) ; migration douce de l'ancien fichier. La liaison chat→compte est désormais multi-worker-safe.
- **`plan_store` → store SQLite partagé**, mutations **atomiques** (`update`) ; migration douce de l'ancien `plans.json`. API inchangée.
### Note
- Caches `_tool_cache` / `_summary_cache` : volontairement **par-worker** (caches bornés, pas des fuites) — les partager via SQLite coûterait plus cher que recalculer. Rate-limiting : par-worker (cf. note README) → limite globale = reverse-proxy.


## [0.21.9] - 2026-06-17
### Added
- **Recherche web APPROFONDIE (`deep_research`)** — vraie « deep search » : cherche le sujet, LIT réellement plusieurs pages (web_scrape), puis SYNTHÉTISE une réponse factuelle et SOURCÉE (URL citées) via le LLM. Complète `web_search` (rapide) ; exposée à l'orchestrateur sur les requêtes web/approfondies.
### Security
- **`coder_cli`** : les arguments d'outils affichés en console sont passés par `redact_secrets` (plus de fuite de clés/mots de passe dans le terminal).


## [0.21.8] - 2026-06-17
### Security / Robustesse (passe de durcissement, suite à revue de code)
- **Rate-limiting : fuite mémoire corrigée** — purge GLOBALE une fois par minute (toute entrée d'une minute écoulée), au lieu d'attendre 5000 entrées. Comportement par-worker documenté (limite globale = reverse-proxy).
- **Scripts de migration `extract_*.py` supprimés** (dette technique, basés sur des numéros de ligne, non importés).
- **`except Exception` de démarrage durcis** : traceback loggé (Telegram, moniteur Proxmox) au lieu d'un message muet ; observabilité loggée en debug.
- **`athena_cli.py`** : `os.system` → `subprocess.run` (console locale opérateur, passthrough shell assumé).
- **README** : note explicite que le rate-limiting applicatif est par-worker (utiliser le reverse-proxy pour une limite globale).
### Note
- La garde réseau existait déjà : le serveur REFUSE de démarrer si bind exposé sans `ADMIN_PASSWORD` ni utilisateur (`_enforce_network_security`).


## [0.21.7] - 2026-06-17
### Changed
- **Capteurs satellites : config optimisée** — les capteurs de gaz (SGP30, SGP40, ENS160) reçoivent automatiquement une **compensation température/humidité** (précision nettement meilleure) dès qu'un capteur temp+humidité (AHT20/SHT3x/BME280/DHT) est aussi choisi sur le même satellite ; sinon, pas de compensation (aucune référence morte). Audit : toutes les sorties capteurs sont lisibles (le BME680 brut était le seul « chiffre obscur », déjà corrigé en IAQ).


## [0.21.6] - 2026-06-17
### Added
- **Satellites : options bluetooth_proxy, improv BLE et boutons volume** (cases à cocher). bluetooth_proxy (relais BLE → HA, présence/follow-me) et improv (config WiFi par Bluetooth) **n'utilisent aucun GPIO** ; les boutons volume ont des broches sûres par défaut (GPIO47/21) avec **détection de conflit GPIO** (avertissement si une broche est déjà prise par l'audio/I2C/LED/capteur).
### Changed
- **BME680 : sortie LISIBLE** — passage au composant `bme680_bsec2` (Bosch) → **indice IAQ (0-500)**, **CO2 équivalent (ppm)** et **COV équivalent**, au lieu de la résistance de gaz brute (chiffre obscur). L'IAQ se calibre sur ~1 h.


## [0.21.5] - 2026-06-17
### Changed
- **Satellites : LED de statut en vraie machine à états** — retour visuel par phase via les événements ESPHome : rouge (Athena déconnectée), bleu (écoute), violet clignotant (réflexion), cyan (réponse), repos éteint, rouge clignotant (erreur). Effets pulse inclus.


## [0.21.4] - 2026-06-17
### Added
- **Générateur de satellites enrichi** : (1) **schéma de câblage** injecté en tête du YAML généré (micro/ampli/I2C/1-wire/LED, broches réelles) ; (2) **LED de statut en option** (case à cocher), défaut = LED RGB **embarquée GPIO48** de la devkit S3 (aucun composant), avec retour couleur selon la phase vocale (écoute/réponse) ; (3) **RCWL-0516** (radar de présence pas cher) ajouté au catalogue pour le suivi de pièce (en plus du PIR). Tout reste mains-libres (wake word serveur/embarqué) — pas de bouton requis.


## [0.21.3] - 2026-06-17
### Changed
- **Briefing quotidien enrichi (infra)** : `get_daily_briefing` ajoute — si Proxmox est configuré — un point INFRASTRUCTURE (VM en marche/arrêt, stockages élevés) + les **alertes Vigie des dernières 24 h**, en plus de météo/agenda/tâches/courses. Parfait en routine matinale livrée sur Telegram (« briefing tous les jours à 7h30 »).


## [0.21.2] - 2026-06-17
### Added
- **Vigie Proxmox — alertes automatiques** : un moniteur léger (poll non-LLM, `core/proxmox_monitor.py`) vérifie périodiquement Proxmox et POUSSE un événement à la Vigie en cas d'incident → VM/LXC qui tombe, nœud offline, RAM ou disque (réel) au-dessus d'un seuil. Détection par transition (pas de spam). Le LLM ne se réveille que sur incident. Réglable dans Réglages → 👁️ Vigie (case « Surveiller Proxmox » + intervalle + seuils RAM/disque). **Ne tourne (ne poll) que si la Vigie est activée ET Proxmox configuré** — sinon le thread dort (coût nul).


## [0.21.1] - 2026-06-17
### Added
- **Athena peut se mettre à jour sur demande** (`self_update`) : lance `update.sh` en arrière-plan DÉTACHÉ (git pull + dépendances + redémarrage) → survit au restart, contrairement à un `update.sh` lancé via `execute_bash_command` (qui couperait Athena en plein run). Action SENSIBLE → validation HITL. Exposé à l'orchestrateur (« Athena, mets-toi à jour »).


## [0.21.0] - 2026-06-17
### Added
- **Proxmox : exécuter une commande DANS une VM** (`proxmox_vm_exec`) via l'agent invité (qemu-guest-agent), sans SSH. Lance la commande (`/agent/exec`), attend la fin (`/agent/exec-status`) et renvoie sortie/erreur/code. **Action très sensible → validation HITL obligatoire.** Gère les cas « guest-exec désactivé » et droits insuffisants (PVEAdmin requis). Pour un LXC : passer par SSH.


## [0.20.6] - 2026-06-17
### Changed
- **Proxmox : le résumé garde les Go, pas seulement les %** — consigne ajoutée pour que l'assistant restitue les valeurs absolues (Go) ET les pourcentages (RAM/disque), au lieu de condenser en pourcentages seuls.


## [0.20.5] - 2026-06-17
### Added
- **Proxmox : disque RÉELLEMENT utilisé des VM** via l'agent invité (`qemu-guest-agent`) — `proxmox_status` interroge `/agent/get-fsinfo` pour chaque VM en marche et affiche l'espace réel écrit (somme des systèmes de fichiers, hors pseudo-FS), marqué « réel ». Si l'agent est absent → « alloué » (taille provisionnée), comme avant. Les LXC montrent toujours le réel.


## [0.20.4] - 2026-06-17
### Changed
- **Proxmox : le résumé de l'assistant n'alarme plus à tort sur le stockage** — une consigne dans le résultat de `proxmox_status` demande à l'IA de ne PAS présenter les % comme « presque plein/critique » sans préciser qu'il s'agit d'espace ALLOUÉ/provisionné au pool (ZFS/LVM-thin), pas de l'écrit réel.


## [0.20.3] - 2026-06-17
### Changed
- **Proxmox : jauge stockage clarifiée (honnêteté)** — les chiffres affichés sont la jauge Proxmox (espace alloué/réservé au niveau pool/FS) ; une note rappelle que sur ZFS/LVM-thin — y compris un stockage « dir » posé sur un pool ZFS — l'espace réellement écrit peut être bien inférieur (`zfs list`/`df` pour le réel). Plus de fausse distinction dir = « réel ».


## [0.20.2] - 2026-06-17
### Changed
- **Proxmox : affichage stockage plus clair** — chaque stockage indique son **type** (`dir`, `zfspool`, `lvmthin`, `pbs`…) et les types « thin » (LVM-thin/ZFS/RBD) sont annotés **« provisionné/alloué »** (l'usage réel peut être inférieur). Le disque du nœud est étiqueté **« disque root »** (système) pour ne pas le confondre avec les stockages.


## [0.20.1] - 2026-06-17
### Changed
- **Proxmox : `proxmox_status` montre la charge CPU, RAM ET disque** par nœud / VM / conteneur, plus l'espace des **stockages** (datastores). Un seul appel `/cluster/resources`. (Pour une VM QEMU, l'usage disque réel nécessite l'agent invité ; sinon la taille allouée est indiquée.)


## [0.20.0] - 2026-06-17
### Added
- **Intégration Proxmox VE native (MCP d'environnement)** : Athena lit l'état du cluster (nœuds, VM QEMU, conteneurs LXC, CPU/RAM) via `proxmox_status`, et peut **démarrer/arrêter/redémarrer** une VM/LXC via `proxmox_vm_action` (action SENSIBLE → validation/HITL). API REST native (jeton d'API, anti-SSRF, TLS optionnel), sans SDK ni dépendance MCP tierce. Config par-utilisateur dans l'UI (Réglages → 🖧 Proxmox) ; auto-exposée à l'orchestrateur quand configurée (« état de mes VM », « redémarre la VM 100 »).


## [0.19.7] - 2026-06-16
### Changed
- **Latence vocale fortement réduite (chat)** : au lieu d'attendre la synthèse de TOUT le message avant de parler, Athena synthétise et lit désormais **phrase par phrase en pipeline** — la voix démarre dès la 1ʳᵉ phrase (~1 s) pendant que les suivantes se préparent en arrière-plan. Annulation propre si une nouvelle réponse arrive.


## [0.19.6] - 2026-06-16
### Fixed
- **LA cause du « NotSupportedError » à la lecture vocale (chat + bouton Test), sur TOUS les navigateurs** : la Content-Security-Policy n'avait **pas de directive `media-src`** → `<audio>` chargé depuis un `blob:` retombait sur `default-src 'self'` et était **bloqué**. Ajout de `media-src 'self' blob: data:`. La voix (TTS) se lit désormais normalement. (Les corrections WAV/MP3 précédentes restent utiles selon le serveur TTS, mais le vrai verrou était la CSP.)


## [0.19.5] - 2026-06-16
### Fixed
- **Aperçu/chat vocal lu sur TOUS les navigateurs** : l'endpoint navigateur `/api/voice/tts` demande désormais du **MP3** (universellement lisible) au lieu du WAV de Kokoro (en-tête « streaming » + chunk LIST refusés par Edge/Firefox). Sans effet sur les satellites (chemin séparé). Réglable via `BROWSER_TTS_FORMAT` (défaut mp3). La normalisation WAV reste en repli. Vérifié contre un vrai Kokoro (sortie `audio/mpeg`).


## [0.19.4] - 2026-06-16
### Fixed
- **Lecture vocale impossible sur TOUS les navigateurs (Edge inclus), pas seulement Firefox** : le WAV de Kokoro contient un chunk `LIST/INFO` (métadonnées libav) **et** des tailles d'en-tête bidon que les décodeurs navigateur refusent. `_normalize_wav` **réémet désormais un WAV canonique** (`fmt `+`data` uniquement, tailles exactes) via le module `wave` → fichier universellement lisible. Vérifié de bout en bout contre un vrai serveur Kokoro.


## [0.19.3] - 2026-06-16
### Fixed
- **Test/lecture vocale « NotSupportedError » (Kokoro)** : Kokoro renvoie un WAV « streaming » avec une **taille d'en-tête bidon** (`RIFF … 0xFFFFFFFF`) que Firefox refuse. L'endpoint `/api/voice/tts` **réécrit désormais les tailles RIFF/data réelles** (`_normalize_wav`) → WAV valide, lecture OK. Détection du format conservée (wav/mp3/ogg). Le bouton « Tester » affiche maintenant le format reçu (type/taille/octets) pour diagnostiquer en un clic.


## [0.19.2] - 2026-06-16
### Fixed
- **Test vocal « NotSupportedError »** : le serveur TTS peut renvoyer du WAV, du MP3 ou de l'OGG ; l'endpoint `/api/voice/tts` **détecte le vrai format** (octets magiques) et pose le bon Content-Type (fini le mp3 étiqueté « audio/wav » que Firefox refusait), et **rejette proprement** une réponse non audio (erreur serveur).
- **Voix corrompue auto-nettoyée** : une valeur de voix héritée invalide (un dict enregistré par erreur) est ignorée (`_clean_voice`) → repli sur une vraie voix.
- **Liaison Telegram → compte** : le menu inclut désormais le **compte connecté** (cas admin via `ADMIN_PASSWORD`, absent du user_store) + les comptes déjà liés, en plus du user_store et de « local ».


## [0.19.1] - 2026-06-16
### Fixed
- **Sélecteur de voix affichait le dict brut** (`{'id': 'af_bella', ...}`) quand Kokoro renvoie des objets : `_voice_label` est désormais défensif (extrait l'ID même si un objet arrive) → libellés propres (« 🇺🇸 Bella (féminine) »). NB : nécessite un vrai redémarrage du service côté serveur.


## [0.19.0] - 2026-06-16
### Added
- **Proactivité événementielle — agent « Vigie » (vers Jarvis).** Athena réagit à des événements POUSSÉS par la supervision (Zabbix, Grafana, LibreNMS, Home Assistant, traps SNMP via forwarder…). 100 % piloté par événement : **rien ne tourne en boucle**, un worker bloqué se réveille uniquement à l'arrivée d'un événement, l'analyse, alerte et propose un correctif (action sensible → validée via le HITL Telegram). Ingress `POST /api/events` (jeton dédié `X-Event-Token`, sans session), filtrage par sévérité + dé-duplication + file bornée (anti-tempête). **Configurable dans l'UI** (onglet 👁️ Vigie) **et par Athena** (`configure_monitoring`, `list_recent_events`). `core/events.py`, gate `EVENT_BROKER`.


## [0.18.0] - 2026-06-16
### Added
- **Goal Manager — objectifs persistants (continuité de but, vers Jarvis).** Athena suit des buts à long terme par utilisateur : `create_goal(titre, detail, priorité, étapes)`, `list_goals`, `update_goal_status` (active/paused/done/abandoned), `add_goal_step`, `complete_goal_step`, `set_goal_priority`. Les objectifs ACTIFS sont rappelés dans la conscience situationnelle de chaque run → Athena « ne perd pas le fil ». Bridage : le module SUIT les objectifs, il n'exécute rien tout seul (toute action passe par les outils normaux + HITL). Par compte, persistant. Gate `GOAL_MANAGER`.


## [0.17.0] - 2026-06-16
### Added
- **HITL multi-canal asynchrone (validation des actions critiques depuis le téléphone).** Quand une action SENSIBLE est déclenchée depuis Telegram, le run se **FIGE** (au lieu de « demander et s'arrêter ») et pousse une **notification actionnable** avec boutons inline **✅ Autoriser / ⛔ Refuser** (ou `/allow <id>` / `/deny <id>`). La décision **libère le run** : approuvé → l'outil s'exécute ; refusé/expiré → non exécuté. Endpoints `GET /api/approvals` et `POST /api/approvals/{id}/decision`. File `core/approval_queue.py` (timeout = refus sûr, `APPROVAL_TIMEOUT`). Gate `APPROVAL_ASYNC` (canaux push uniquement ; web/voix restent in-band). `APPROVAL_ASYNC_ALL` pour étendre au web.


## [0.16.1] - 2026-06-16
### Added
- **Conscience situationnelle (World Model, couche lecture)** : au début d'un run, Athena reçoit l'« état actuel » — les **parenthèses ouvertes** (tâches mises de côté) et la **pièce courante** (présence Home Assistant). Complète le profil utilisateur / graphe / RAG / Core Memory déjà injectés, sans doublon (`core/context_assembler.py`).
- **Outil `reset_sandbox`** : réinitialise l'environnement d'exécution (conteneur Docker) si un script l'a cassé / saturé / mis en boucle. Les fichiers du workspace sont conservés. Donné automatiquement aux agents qui exécutent du code/des commandes.


## [0.16.0] - 2026-06-16
### Added
- **Context Stacker (« fil d'Ariane ») — pile de contextes (vers Jarvis).** Athena peut METTRE DE CÔTÉ la tâche en cours pour traiter une parenthèse, puis REPRENDRE exactement où elle s'était arrêtée. Outils orchestrateur : `open_context(sujet)` (PUSH), `close_context()` (POP), `list_contexts()`. S'appuie sur l'arbre de conversation natif (aucun snapshot lourd : on parque l'`active_node_id` et on repart sur une branche neuve) et **gèle/relance la sandbox Docker associée** (`docker pause`/`unpause`). Pile LIFO par session, persistée, imbrication supportée. Activable via `CONTEXT_STACK`.


## [0.15.1] - 2026-06-16
### Fixed
- **Fiabilité du tool-calling (LLM qui « appelle » un outil en texte).** Le rattrapage des appels écrits en texte gère désormais le **JSON malformé** (virgules traînantes, quotes simples, None/True/False) et le **style Python** `outil({...})` / `outil()`, en plus des blocs ```json``` et balises `<tool_call>`. Et si le modèle DÉCRIT un appel sans le déclencher (et que rien n'est récupérable), Athena se **relance automatiquement** pour qu'il l'exécute vraiment au format structuré (`TOOLCALL_AUTOFIX`, borné par `TOOLCALL_FIX_MAX`). Anti faux-positif : ne s'active que si un outil réel est cité.


## [0.15.0] - 2026-06-16
### Added
- **Chronos — mémoire relationnelle automatique (vers Jarvis).** En fin de run, Athena extrait les FAITS DURABLES de l'échange (identité/préférences de l'utilisateur, personnes, lieux, machines et leurs relations) et les range dans la mémoire-graphe par-utilisateur (`GRAPH_AUTO_EXTRACT`). Au début d'un run, le contexte-graphe pertinent (entités citées dans la demande) est injecté — « ce que je sais déjà » — pour résoudre les références implicites (« le serveur de dev », « ma femme »…) (`GRAPH_CONTEXT_INJECT`, `GRAPH_CONTEXT_TOPK`). Le moteur graphe (triplets, voisinage) existait déjà ; ceci le câble en automatique.


## [0.14.6] - 2026-06-16
### Added
- **Listes (courses, tâches…) synchronisées avec Nextcloud Notes** (optionnel, par-utilisateur). Quand c'est activé (Réglages → Nextcloud), Nextcloud devient la source de vérité : une note Markdown (cases à cocher) par liste dans le dossier Notes, synchro **2 sens** (cocher/ajouter/supprimer depuis l'app Notes mobile se répercute dans Athena, et inversement). Réconciliation par texte pour préserver les éléments ; garde-fou anti-perte (jamais d'écrasement du local si Nextcloud est injoignable). Désactivé = listes purement locales (inchangé).


## [0.14.5] - 2026-06-16
### Added
- **Vocal : routage par locuteur vers SON compte.** Le satellite reconnaît qui parle (empreinte vocale, `voice/speaker_id.py`) et transmet `as_user` à `/api/chat/stream` : agenda, listes et mémoire deviennent ceux du membre du foyer identifié. Mapping optionnel locuteur→compte via `VOICE_SPEAKER_ACCOUNTS` (JSON), sinon le nom enrôlé sert de compte. Sécurité : `as_user` honoré seulement si l'auth est désactivée (mono-poste) ou si l'appelant est admin.
  - Enrôlement : `python3 voice_assistant.py enroll <nom> <échantillon.wav>`.


## [0.14.4] - 2026-06-16
### Fixed
- **Telegram voyait le mauvais agenda/compte** : toutes les requêtes Telegram s'exécutaient en tant qu'utilisateur « local », alors que l'agenda/config/mémoire sont par compte. Du coup, en demandant par Telegram, Athena ne voyait que l'agenda local et jamais ton CalDAV. On peut désormais **lier chaque chat Telegram à un compte Athena** (Réglages → Messageries) : les messages de ce chat utilisent l'agenda, la config et la mémoire de CE compte. Liaison possible pour les chats approuvés ET configurés ; variable `TELEGRAM_DEFAULT_USER` comme repli.


## [0.14.3] - 2026-06-16
### Changed
- **Modèles Vision et Rédaction = liste déroulante dynamique** (comme les agents) : les modèles disponibles sont récupérés en direct depuis l'endpoint (`/api/config/models`), groupés par fournisseur. La valeur courante reste préservée ; un modèle saisi manuellement et absent de la liste est conservé (« actuel »).


## [0.14.2] - 2026-06-16
### Fixed
- **Ctrl+Entrée / Ctrl+Maj+Entrée insèrent enfin un saut de ligne** dans le chat et dans AthenaDesign. Un `<textarea>` n'insère rien par défaut sur Ctrl+Entrée (seul Maj+Entrée le fait) : le saut est désormais inséré à la main. Entrée seule = envoyer.


## [0.14.1] - 2026-06-16
### Changed
- **Réglages « Comportement » repensés (user-friendly)** : sections en cartes repliables avec icône, chaque réglage accompagné d'une description en français clair, interrupteurs visuels (on/off), barre de recherche pour filtrer les réglages. Rendu responsive vérifié (desktop + mobile).


## v0.14.0 (UI responsive : utilisable sur téléphone/tablette)

### 📱 Correctif majeur du layout mobile
- BUG racine (≤600px) : le dock (1er du DOM) prenait la grande ligne de la grille et écrasait
  le contenu principal à 60px → zone principale INVISIBLE / app inutilisable sur téléphone.
  Corrigé : placement explicite (contenu en haut = 1fr, dock en bas = 60px).
- Vues internes empilées sur téléphone : grilles 2 colonnes (Écriture, Réunions, inline) → 1
  colonne ; vue Tâches/Listes (flex) → empilée ; anti-débordement horizontal ; bandeau du haut
  qui s'enroule ; chat plein écran.
- Vérifié au navigateur headless (Playwright) en 390px (tel) et 1440px (desktop intact).


## v0.13.11 (Skills auto : réseau + fichier autorisés, système bridé)

### 🛠️ Politique de validation assouplie (création confirmée)
- save_new_skill (créé À LA DEMANDE, confirmé par l'humain) accepte désormais le RÉSEAU
  (requests/urllib/http…) et les FICHIERS (open/pathlib/shutil…) — utile pour des outils qui
  appellent une API ou manipulent des fichiers. Le SYSTÈME reste BRIDÉ : subprocess, os.system,
  os.popen/exec/spawn/fork, socket, ctypes, eval/exec/__import__ → refusés (utiliser
  execute_bash_command pour le shell). Nouveau validate_skill ; l'AUTO-INDUCTION non supervisée
  garde le validateur STRICT (fonction pure) — inchangé.


## v0.13.10 (Auto-création d'outils : Athena peut créer un outil quand il en manque)

### 🛠️ save_new_skill exposé à l'orchestrateur (proactif, validé)
- save_new_skill n'était PAS dans les outils d'Athena (réservé à l'induction interne) → elle ne
  pouvait pas créer un outil À LA DEMANDE. Désormais auto-injecté à l'orchestrateur (si
  SELF_IMPROVE_SKILLS), retiré du filtrage par mots-clés (toujours disponible), + préambule qui
  l'encourage pour une opération réutilisable manquante. Reste bridé : fonction PURE validée par
  AST + confirmation utilisateur.
- Préambule create_routine pour les tâches récurrentes.
- Fix test_skill_induction (périmé) : aligné sur le garde anti-bruit (≥ SKILL_MIN_TOOL_CALLS).


## v0.13.9 (Auto-amélioration : Athena crée ses routines)

### 🤖 create_routine (avec validation)
- Nouvel outil create_routine : Athena peut créer une routine planifiée (briefing matinal,
  rappel récurrent…) directement par la conversation, sans aller dans l'UI. Marqué SENSIBLE
  (_requires_approval) → l'utilisateur CONFIRME avant création (reste bridé). + list_routines
  (lecture). Auto-injectés à l'orchestrateur, exposés par mots-clés (routine/chaque matin…).
- Complète l'auto-création d'OUTILS déjà possible (save_new_skill, validé par AST).


## v0.13.8 (Confort fichiers & projets)

### 📂 Navigateur de fichiers + vue workspace dans Écriture
- Bouton 📂 à côté du champ chemin de l'onglet Écriture → sélecteur de fichiers du workspace
  (filtré .docx, recherche intégrée) → remplit le champ. Sélecteur réutilisable (openWorkspacePicker).

### ✏️ Renommer les projets Design
- Clic sur le titre du projet (AthenaDesign) → renommage. Endpoint POST
  /api/athenadesign/projects/{id}/rename + core.projects.rename (registre unifié code+design).


## v0.13.7 (UX quick wins — saisie & fichiers)

### ⌨️ Saisie cohérente partout
- Chat : le champ devient un TEXTAREA multiligne — Entrée = envoyer, Ctrl/Cmd/Maj+Entrée = saut
  de ligne, avec auto-grandissement.
- AthenaDesign : Entrée envoie le prompt (Ctrl/Maj+Entrée = saut de ligne).

### 🗑️ Suppression de fichiers dans l'onglet Code
- Bouton 🗑️ (avec confirmation) sur chaque fichier/dossier de l'explorateur ; nouvel endpoint
  DELETE /api/workspace/file (anti-traversée, refus en lecture seule).


## v0.13.6 (Modèle de rédaction configurable)

### ✍️ Choisir le LLM qui révise les romans
- La révision/cohérence/traduction de romans utilisait toujours le modèle de l'orchestrateur
  (chat-qwen). Nouveau DOCUMENT_MODEL (réglage UI « Rédaction (romans) ») : permet d'utiliser un
  modèle plus littéraire (ex. custom/gemma) pour la rédaction tout en gardant chat-qwen pour
  l'orchestration. Vide = modèle d'Athena (comportement par défaut inchangé).


## v0.13.5 (Auto-continuation : Athena agit après avoir annoncé)

### ⚡ Plus besoin de dire « vas-y »
- Quand Athena ANNONCE une action (« je vais vérifier tes mails », « je lance l'archivage… »)
  mais n'appelle aucun outil, elle est désormais RELANCÉE automatiquement pour EXÉCUTER tout de
  suite, au lieu de rendre la main et d'attendre une relance manuelle.
- Bornée (AUTO_CONTINUE_MAX=2 par tour, anti-boucle) et RESPECTUEUSE : si le message pose une
  question à l'utilisateur (demande d'avis/approbation), on s'arrête — c'est à l'utilisateur de
  décider. Réglages dans l'UI (Comportement → AUTO_CONTINUE / AUTO_CONTINUE_MAX).


## v0.13.4 (Ménage code & tests)

### 🧹 Nettoyage
- Suppression de fichiers cruft locaux (*.bak) et du script jetable scripts/diag_vision.py.
- scripts/diag_agenda.py : retrait de la référence morte à core.google_oauth (feature OAuth
  supprimée précédemment).
- tests/test_email_tools.py : mock IMAP mis à jour (conn.uid) suite au passage des mails en UID.
- tests/test_document_editor.py : écrit dans un workspace TEMPORAIRE → ne pollue plus le dépôt
  (dossier redaction/ parasite supprimé + ignoré).
- Revue : compilation complète OK, suite de tests verte (hors échecs PRÉ-EXISTANTS/optionnels :
  computer_use=Playwright absent, claude_code=plugin off, skill_induction=déjà rouge avant session).


## v0.13.3 (Fix def — embedding endpoint conforme à ChromaDB 1.x)

### 🐛 Recherche RAG (embedding endpoint) enfin opérationnelle
- L'embedding via endpoint plantait à la recherche : `_HttpEmbeddingFunction` n'héritait pas de
  `chromadb.api.types.EmbeddingFunction` → erreurs « no attribute embed_query » puis
  « embed_query() got unexpected keyword 'input' ». Corrigé en HÉRITANT de EmbeddingFunction
  (chromadb 1.5.9) : on n'implémente que __call__(input)/name()/get_config ; embed_query &
  embed_with_retries viennent de la base (signature `input` correcte). Testé store+search OK.


## v0.13.2 (Fix recherche RAG avec embedding endpoint)

### 🐛 « '_HttpEmbeddingFunction' object has no attribute 'embed_query' »
- La recherche mémoire (ChromaDB query) échouait avec un embedding via endpoint : ChromaDB
  attendait aussi l'interface embed_query/embed_documents (style LangChain), pas seulement
  __call__. Ajout des trois méthodes → recherche RAG opérationnelle avec bge-m3 / qwen3-embedding.


## v0.13.1 (Embeddings configurables : local par défaut, endpoint optionnel)

### 🧠 Mémoire RAG : meilleur embedding au choix (sans casser le défaut)
- L'embedding de la mémoire vectorielle (ChromaDB) était le défaut local (all-MiniLM, anglo-centré).
  Désormais CONFIGURABLE : EMBEDDING_PROVIDER=local (défaut, marche partout, aucun endpoint requis)
  ou =http (endpoint OpenAI-compatible /v1/embeddings : bge-m3, qwen3-embedding… → bien meilleur en
  français). Repli automatique sur le local si l'endpoint est injoignable.
- Collections ISOLÉES par moteur d'embedding (dimensions différentes → pas de mélange/crash) ;
  l'embedding local garde le nom historique (rétro-compat).
- Réglages dans l'UI (Comportement → « Mémoire — Embeddings ») : provider, modèle, URL.


## v0.13.0 (Vision : Athena voit les images)

### 👁️ Analyse d'images via le modèle multimodal de l'endpoint
- core/vision.py + tools/vision_tools.py : `analyze_image(filename, question)` → Athena décrit/lit
  une image uploadée (capture, photo, schéma, doc scanné) via un modèle vision (défaut
  custom/chat-gemma), en BASE64 (contrainte de l'endpoint). Auto-injecté à l'orchestrateur,
  exposé par mots-clés (image/capture/« que vois-tu »…).
- `capture_screen` : 1ʳᵉ brique « computer use » — capture l'écran de la machine et l'analyse.
  OPTIONNEL/GATÉ (COMPUTER_USE=true) et inutile sur serveur headless. Le contrôle souris/clavier
  reste à part (l'automatisation NAVIGATEUR existe déjà via computer_use_action / Playwright).
- Réglages dans l'UI (Comportement) : VISION_MODEL + COMPUTER_USE.


## v0.12.10 (Routines : envoi du résultat sur Telegram)

### 📲 Briefing matinal (et toute routine) livré sur Telegram
- Nouvelle option « Envoyer sur Telegram (chat ID) » dans les routines : le résultat de la
  routine (ex. briefing du matin) est ENVOYÉ sur le chat Telegram indiqué, en plus de la
  notification interne. Couvre les routines à prompt ET les workflows. Si Telegram n'est pas
  configuré, l'envoi est ignoré proprement.


## v0.12.9 (Réglages TTS dans l'UI)

### ⚙️ URL serveur TTS + émotion + vitesse réglables dans l'UI
- Réglages → Satellites vocaux : en plus du menu de voix, on règle désormais depuis l'UI
  l'URL du serveur TTS (VOICE_TTS_HTTP_URL), le toggle « Émotion par marqueur »
  (VOICE_TTS_EMOTION_MARKERS) et la vitesse de base (VOICE_TTS_SPEED). Persisté en .env + à
  chaud, partagé chat + satellites. Plus besoin d'éditer le .env à la main pour brancher
  Kokoro/Fish-Speech/XTTS.


## v0.12.8 (Émotion par marqueur — prêt pour Fish-Speech)

### 🎭 [emotion:X] → marqueur natif « (sad) … » (émotion pilotée)
- Nouveau VOICE_TTS_EMOTION_MARKERS=true : Athena traduit l'émotion de l'agent en MARQUEUR injecté
  en tête du texte envoyé au TTS (enjoué→(happy), triste→(sad), fâché→(angry), chuchoté→
  (whispering)…), pour les moteurs à marqueurs type Fish-Speech / OpenAudio S1. Vraie émotion
  pilotée (au-delà de la vitesse/volume). Sans effet sur piper/pyttsx3 (jamais prononcé).
- docs/fish-speech-server.md : recette complète serveur Fish-Speech français/émotion/clonage sur
  GPU dédié (docker-compose + shim OpenAI /v1/audio/speech + /v1/audio/voices + sécurisation 24/7).


## v0.12.7 (Voix : nuance d'intensité par émotion, CPU)

### 🎭 Volume modulé par l'émotion (en plus de la vitesse)
- 2ᵉ levier expressif applicable sur CPU (numpy seul) : l'émotion module désormais aussi le
  VOLUME — chuchoté nettement plus doux, triste/calme/empathique adoucis ; les émotions
  énergiques gardent l'intensité (+ la vitesse fait l'effet). Sans saturation (réduction
  uniquement + clip de sécurité). Appliqué au chat (WAV) et aux satellites (stream).
- Note : sur CPU sans GPU, Kokoro reste le meilleur compromis basse-latence ; pour une
  expressivité bien supérieure, brancher un moteur XTTS sur une machine dédiée via
  VOICE_TTS_HTTP_URL (l'architecture le permet déjà).


## v0.12.6 (Voix émotionnelle activée par défaut + dédup)

### 🎭 Correctif
- Une instruction d'émotion gated « VOICE_EMOTION_TAGS » existait déjà mais était DÉSACTIVÉE par
  défaut (false) → les agents n'émettaient jamais de balise, l'émotion ne marchait pas. Passée à
  ACTIVE par défaut (le tag ne fuite jamais — retiré à l'affichage et de la prononciation ;
  VOICE_EMOTION_TAGS=false pour couper). Suppression de l'instruction dupliquée ajoutée en 0.12.5.


## v0.12.5 (Voix émotionnelle)

### 🎭 Émotion de bout en bout (chat + satellites)
- Les agents peuvent préfixer leur réponse d'une balise « [emotion: X] » (neutre, enjoué,
  excité, triste, calme, sérieux, empathique, fâché, chuchoté) — instruction ajoutée au
  préambule. La balise est extraite (voice/emotion.py) puis RETIRÉE du texte affiché (déjà
  géré) et du texte prononcé.
- L'émotion module désormais réellement la voix : mapping émotion → VITESSE Kokoro (seul levier
  expressif de l'API OpenAI ; pas de pitch/volume), appliqué dans tous les chemins TTS (stream,
  wav, satellites). Base réglable via VOICE_TTS_SPEED.


## v0.12.4 (Voix du chat : plus de repli robotique par défaut)

### 🔊 Voix Kokoro même sans voix enregistrée
- Si aucune voix n'était choisie, le TTS envoyait « alloy » (voix OpenAI inconnue de Kokoro) →
  échec → repli sur la voix robotique du navigateur. Désormais, sans voix définie, le serveur
  prend AUTOMATIQUEMENT la 1ʳᵉ voix Kokoro disponible → le chat parle en Kokoro dès le départ.
  (Choisir + 💾 une voix dans Réglages → Satellites reste recommandé.)


## v0.12.3 (Voix Kokoro : libellés lisibles + écoute fonctionnelle)

### 🔊 Liste des voix propre
- Les voix s'affichaient en ID bruts (« af_heart ») voire en objets « {id:…} », ce qui cassait
  aussi le test (valeur invalide envoyée à Kokoro). /api/voice/voices renvoie désormais un ID
  PROPRE + un LIBELLÉ lisible (ex. « 🇫🇷 Siwis (féminine) », « 🇺🇸 Adam (masculine) »), avec
  extraction robuste (chaîne ou objet). Le bouton ▶️ Tester fonctionne (ID valide transmis).


## v0.12.2 (Voix du chat = Kokoro + sélecteur de voix dynamique)

### 🔊 Le chat parle avec Kokoro (même voix que les satellites)
- La lecture vocale du chat utilisait la voix ROBOTIQUE du navigateur (Web Speech API).
  Désormais elle passe par Kokoro via /api/voice/tts (le MÊME moteur que les satellites) →
  voix naturelle + émotion. Repli automatique sur la voix du navigateur si Kokoro est injoignable.
- Sélecteur de voix DYNAMIQUE (Réglages → Satellites vocaux) : liste les voix proposées par
  Kokoro (/v1/audio/voices), bouton Tester, et enregistrement → VOICE_TTS_VOICE partagé par le
  CHAT et les SATELLITES (changement appliqué à chaud).


## v0.12.1 (Révisé d'un fichier Nextcloud ouvrable dans OnlyOffice d'Athena)

### 📝 Copie locale du révisé même pour les fichiers Nextcloud
- Quand le document venait de Nextcloud, le révisé était uploadé sur Nextcloud mais aucune copie
  locale n'était gardée → le bouton OnlyOffice d'Athena (qui ouvre un fichier local) retombait
  sur l'original. Désormais une copie locale « — révisé.docx » est conservée dans le workspace en
  plus de l'upload Nextcloud → le bouton ouvre bien le révisé.


## v0.12.0 (Bouton OnlyOffice ouvre le révisé)

### 📝 Le bouton OnlyOffice ouvre le « — révisé.docx », pas l'original
- Le bouton ouvrait le fichier de travail (original chargé) au lieu du révisé, notamment quand
  la révision avait été faite via le chat. Désormais /api/redaction/chapters signale s'il existe
  déjà un « — révisé.docx » et le bouton l'ouvre EN PRIORITÉ (sinon le fichier de travail).
- Note : sous Firefox/Linux, la protection renforcée contre le pistage peut bloquer l'iframe
  OnlyOffice (cross-site) → l'éditeur reste sur le squelette ; OK sous Windows/autres navigateurs.


## v0.11.99 (Diagnostic OnlyOffice : URL que le DS n'arrive pas à joindre)

### 📝 Message clair quand le document reste sur le squelette
- Quand l'éditeur reste bloqué sur le squelette (le Document Server ne télécharge pas le
  fichier), la page affiche après ~22 s l'URL EXACTE que le DS tente d'atteindre + la commande
  `curl -I <url>` à lancer depuis la machine OnlyOffice pour vérifier la joignabilité, et rappelle
  de régler « URL d'Athena vue par OnlyOffice » avec l'IP LAN d'Athena.


## v0.11.98 (Éditeur OnlyOffice en fenêtre dédiée + erreurs claires)

### 📝 Ouverture dans une nouvelle fenêtre
- L'éditeur OnlyOffice s'ouvre désormais dans une PAGE DÉDIÉE plein écran (/oo_editor.html),
  plus confortable que l'embarqué. La page lit le jeton de session (même origine) et affiche
  un MESSAGE D'ERREUR EXPLICITE si ça coince (api.js injoignable = mauvaise URL DS ; zone grise
  vide = le Document Server n'arrive pas à télécharger le fichier depuis Athena → régler « URL
  d'Athena vue par OnlyOffice » ; ou secret JWT incorrect).


## v0.11.97 (Bouton « Ouvrir dans OnlyOffice » fiable)

### 📝 Ouvrir n'importe quel doc chargé dans OnlyOffice
- Le bouton n'apparaissait qu'après une révision (à côté du téléchargement) → ajout d'un BOUTON
  PERMANENT « Ouvrir dans OnlyOffice » dans l'onglet Écriture, visible dès qu'un document est
  chargé ET qu'OnlyOffice est configuré. Ouvre le fichier révisé s'il existe, sinon la copie de
  travail.
- /api/redaction/chapters renvoie désormais le chemin workspace du fichier (ws_path) + l'état
  OnlyOffice → le bouton s'active sans recharger la page.


## v0.11.96 (Éditeur OnlyOffice embarqué dans l'onglet Écriture)

### 📝 Visualiser/éditer les .docx révisés in-app
- Intégration OnlyOffice Document Server : on ouvre un .docx révisé (modifications suivies)
  directement dans l'onglet Écriture, on accepte/refuse les changements et on sauvegarde.
- Réglages dans l'onglet Écriture (repliable) : URL du Document Server, URL publique d'Athena
  vue par le DS, secret JWT. Persistés en .env (POST /api/config/onlyoffice).
- Sécurité : le DS télécharge le fichier et POSTe les sauvegardes via des endpoints protégés
  par JETON à usage limité + JWT (core/onlyoffice.py) ; ces deux endpoints sont exemptés d'auth
  de session (le DS n'en a pas). La CSP autorise dynamiquement l'origine du Document Server.
- Bouton « Ouvrir dans OnlyOffice » à côté du téléchargement quand c'est configuré.


## v0.11.95 (Fichier révisé visible + téléchargeable)

### ✍️ Le fichier révisé est enfin trouvable
- Bug : le fichier révisé d'un .docx UPLOADÉ tombait sous ACTIVE_WORKSPACE_DIR/redaction/…
  alors que l'UI et /api/workspace/download travaillent depuis get_workspace_dir() (projet
  actif) → fichier hors périmètre, lien cassé, « créé mais introuvable ». _dir() s'appuie
  désormais sur get_workspace_dir() (même base que l'UI).
- Onglet Écriture : le résultat affiche un vrai BOUTON « Télécharger le fichier révisé »
  (téléchargement via apiFetch→blob, qui porte le jeton d'auth ; un simple lien ne l'aurait pas).


## v0.11.94 (Catégories Gmail : Promotions, Réseaux sociaux…)

### 📬 Ménage par onglet Gmail
- search_emails et clean_inbox acceptent un paramètre `category` ciblant les ONGLETS Gmail
  (Promotions, Réseaux sociaux=social, Notifications=updates, Forums) via l'extension X-GM-RAW
  → « archive l'onglet Promotions » ou « range mes réseaux sociaux » vide la catégorie entière
  en un appel. Synonymes FR reconnus (promotions, réseaux sociaux, notifications, forums…).
- Nouvel outil list_mail_folders : liste les dossiers/libellés (avec décodage UTF-7) et rappelle
  les catégories Gmail ciblables. Mots-clés de routage étendus (promotions, réseaux sociaux).


## v0.11.93 (Fin des appels run_tool_script gâchés sur mail/SSH)

### ⚡ run_tool_script masqué pour les tâches mail et SSH
- Athena tentait run_tool_script AVANT le bon outil (par habitude) → appels gâchés en boucle,
  car le bac à sable ne peut exécuter ni les mutations mail (clean_inbox/archive…) ni le SSH
  (subprocess interdit). Désormais, dès qu'un outil mail (clean_inbox/archive_emails/
  mark_emails_read/read_inbox) ou SSH (execute_bash_command) est exposé, run_tool_script est
  retiré de l'exposition → le modèle appelle directement le bon outil.


## v0.11.92 (Archivage mail : nom de dossier ASCII + UTF-7 modifié)

### 📬 Plus d'erreur d'encodage sur le libellé d'archive
- « 'ascii' codec can't encode character '\xe9' » : un nom de dossier IMAP accentué
  (« Archivés ») doit être encodé en UTF-7 MODIFIÉ (RFC 3501), pas envoyé en ASCII brut.
  Ajout d'un encodeur _imap_utf7 (les noms accentués fonctionnent désormais) et défaut
  ramené à « Archives » (ASCII, non réservé par Gmail). EMAIL_ARCHIVE_FOLDER accepte les accents.


## v0.11.91 (Archivage Gmail réparé : « Label name is not allowed: Archive »)

### 📬 Le libellé d'archive fonctionne enfin sur Gmail
- Erreur Gmail « Invalid Arguments: Label name is not allowed: Archive » : « Archive » est un
  nom RÉSERVÉ par Gmail, refusé via X-GM-LABELS. Corrigé :
  - méthode UNIFORME pour tous les serveurs (Gmail compris) : créer le dossier/libellé puis
    COPIER les mails dedans (sur Gmail, copier vers un libellé = appliquer ce libellé) puis les
    retirer de la boîte — on n'utilise plus X-GM-LABELS ;
  - libellé par défaut renommé « Archivés » (non réservé) ; toujours configurable via
    EMAIL_ARCHIVE_FOLDER ;
  - archivage par LOTS de 300 UID → des milliers de mails traités rapidement.


## v0.11.90 (Ménage mail en masse par critère + fix STORE-in-AUTH)

### 🧹 clean_inbox : ménage de milliers de mails en un appel
- Nouvel outil `clean_inbox(from_contains, subject_contains, older_than_days, unread_only,
  action)` : filtre CÔTÉ SERVEUR et archive (ou marque lu) tout ce qui correspond en UN appel.
  Fini l'énumération d'IDs lot par lot (cause des listes inventées et des « j'ai archivé X »
  hallucinés sur un weak model). Refuse d'agir sans aucun critère. Plafond de sécurité.
- Préambule mail réécrit : pour le ménage en masse → clean_inbox ; JAMAIS run_tool_script ni
  énumération d'IDs ; toujours montrer un aperçu (search_emails) + nombre avant d'agir.

### 🐛 Corrections
- « command STORE illegal in state AUTH » : le SELECT du dossier n'était pas vérifié avant les
  STORE (archivage/marquage) → désormais contrôlé (_select_rw), message clair si échec.
- search_emails tolère un argument `query` (rabattu sur le sujet) que certains modèles inventent.
- Mots-clés email étendus (ménage, archive, newsletter, spam, publicité…) sans collision avec
  le domaine code.


## v0.11.89 (Archivage mail dans un dossier/libellé dédié)

### 📬 Les mails archivés vont dans un libellé « Archive » propre
- Avant, l'archivage Gmail retirait juste de la boîte → le mail se noyait dans « Tous les
  messages ». Désormais un LIBELLÉ DÉDIÉ (défaut « Archive », configurable EMAIL_ARCHIVE_FOLDER)
  est appliqué via X-GM-LABELS puis le mail est retiré de la boîte → il apparaît sous ce
  libellé propre dans Gmail. IMAP générique : le dossier d'archive est créé au besoin et le
  mail y est déplacé. Toujours aucune suppression (le mail est conservé).


## v0.11.88 (Archivage Gmail corrigé + identifiants mail fiables)

### 📬 Archivage Gmail qui fonctionne vraiment
- L'archivage Gmail ne marchait pas (méthode \Deleted+EXPUNGE dépendante d'un réglage). On
  utilise désormais la méthode CANONIQUE Gmail : retirer le libellé « \Inbox » via
  X-GM-LABELS → le mail sort de la boîte et reste dans « Tous les messages » (rappel : Gmail
  n'a PAS de dossier « Archive », c'est normal). IMAP générique : copie vers le dossier
  d'archive PUIS retrait (copie échouée = rien retiré).
- Tout le flux mail passe en UID (identifiants STABLES entre la liste et l'action) → on n'agit
  plus jamais sur le mauvais mail entre read_inbox/search et mark/archive.


## v0.11.87 (SSH : fin de la boucle subprocess — cause racine corrigée)

### 🖥️ Athena garde execute_bash_command même quand le routeur vise le Codeur
- Cause racine de la boucle « j'utilise subprocess » : une demande SSH/système (« connecte-toi
  à openmediavault, regarde les update apt ») était routée vers le Codeur → l'orchestrateur se
  faisait RETIRER execute_bash_command (outil-métier du Codeur) tout en gardant run_tool_script
  → il se rabattait sur run_tool_script + subprocess (bloqué) en boucle. Désormais
  execute_bash_command et list_ssh_hosts sont conservés sur l'orchestrateur même en cas de
  délégation (_orch_keep) — il les exécute lui-même.
- Défense en profondeur : un run_tool_script contenant subprocess/os/paramiko/ssh est refusé
  AVEC redirection explicite vers execute_bash_command(command, host=...).


## v0.11.86 (Mails : recherche + ménage non destructif)

### 📬 Tri et ménage des mails (sans rien supprimer)
- read_inbox : plafond relevé à 100 (au lieu de 30) pour le tri.
- search_emails(from_contains, subject_contains, since_days, unread_only…) : trouve les mails
  à traiter (newsletters, vieux mails d'un expéditeur, non-lus…).
- mark_emails_read / archive_emails : marquer comme lu et ARCHIVER (sortir de la boîte en
  CONSERVANT une copie — Gmail : reste dans « Tous les messages » ; autres : copie dans le
  dossier d'archive AVANT retrait). Aucune suppression définitive possible. Si la copie échoue,
  rien n'est retiré (zéro perte).
- Garde-fou : Athena doit LISTER les mails ciblés et obtenir l'accord explicite AVANT tout
  ménage en lot (préambule). EMAIL_ARCHIVE_FOLDER configurable.


## v0.11.85 (Onglet Écriture + SSH LAN fiable + diagnostic mail)

### ✍️ Nouvel onglet « Écriture » (atelier romans)
- Onglet dédié dans le dock : charge un .docx (Nextcloud OU upload), liste les chapitres,
  lance Révision / Cohérence / Répétitions / Traduction en tâche de fond avec barre de
  progression, puis affiche le rapport ou le lien de téléchargement du fichier révisé.
  Branché sur /api/redaction/* (jobs du lot précédent).

### 🖥️ SSH : connexion LAN qui marche enfin (TOFU)
- « Server not found in known_hosts » sur un NAS/serveur local : on applique désormais le
  TOFU (trust-on-first-use) AUTOMATIQUEMENT pour les hôtes du réseau LOCAL (IP privée RFC1918,
  loopback, .local/.lan) comme le client ssh — les hôtes PUBLICS restent en RejectPolicy (ou
  auto_add explicite), avec un message d'erreur actionnable.
- L'orchestrateur est explicitement guidé : pour une commande SSH/système, appeler
  execute_bash_command(command, host='LABEL') DIRECTEMENT, jamais run_tool_script (le bac à
  sable interdit subprocess/os → boucle d'échecs observée sur gpt-oss/gemma/qwen3).

### 📬 Mail : message d'erreur IMAP explicite
- Échec IMAP (EOF/timeout/refus) → message guidé : activer l'accès IMAP dans la boîte,
  IMAP_PORT=993 + IMAP_SSL=true, port 993 non bloqué (l'envoi SMTP peut marcher même si l'IMAP
  est bloqué) ; échec d'auth → rappel du mot de passe d'application Google.


## v0.11.84 (Athena lit les mails et se connecte en SSH elle-même)

### 📬 Mails + 🖥️ SSH donnés automatiquement à l'orchestrateur
- Athena répondait « je n'ai pas accès aux mails / pas d'outil SSH » : ces outils
  appartenaient à la Secrétaire / au Codeur et n'étaient pas dans sa liste, et elle ne
  déléguait pas. Désormais auto-injectés à l'orchestrateur QUAND ils sont configurés :
  - mails (LECTURE IMAP + BROUILLONS, jamais d'envoi) si IMAP_HOST/USERNAME/PASSWORD sont
    renseignés → « vérifie mes mails » marche sans déléguer ;
  - SSH (execute_bash_command + list_ssh_hosts) si au moins un hôte est configuré →
    « connecte-toi à <serveur> » marche sans passer par la console Codeur.
- Mots-clés de domaine étendus (connecte/connexion/nas/openmediavault/omv/synology/proxmox/
  docker…) pour que ces demandes exposent bien les outils via le filtre par pertinence.


## v0.11.83 (Atelier romans : opérations en arrière-plan + plus de délégation fantôme)

### ⛔ Plus de délégation à l'Auteur pour éditer un .docx existant
- Cause racine (reproduite sur 3 modèles : gpt-oss, gemma, qwen3) : l'orchestrateur déléguait
  « révise/nettoie le roman » à l'Auteur (Émilie), qui NE PEUT PAS éditer un fichier → impasse,
  narration et livrables hallucinés. Consigne durcie : pour éditer/réviser/corriger/nettoyer/
  traduire un .docx EXISTANT, Athena utilise TOUJOURS les outils document_* elle-même et ne
  délègue JAMAIS (ni transfer_to_/delegate_to_/query_agent). Nettoyer répétitions/style →
  document_autorevise(chemin, instruction=...).

### ⏳ Opérations longues en arrière-plan (jobs + progression)
- Nouveau runner core/jobs.py (thread démon, progression, TTL) + endpoints REST
  /api/redaction/{chapters,job,job/{id},jobs} : réviser/traduire/vérifier la cohérence d'un
  roman entier tourne en tâche de fond avec progression → ne bloque plus une requête HTTP et
  ne s'arrête plus avant la fin. Le contexte utilisateur (ContextVar) est propagé au thread du
  worker (sinon écriture dans le mauvais espace). Base de l'onglet rédaction (lot C).


## v0.11.82 (Atelier romans : suivi conversationnel + sans Nextcloud + intégration cohérence)

### 🐛 « intègre-les » partait en texte au lieu d'appeler l'outil
- Le filtre d'outils ne regardait QUE le dernier message : un suivi sans mot-clé
  (« intègre-les », « fais-le », « oui ») masquait les outils du domaine déjà engagé →
  le modèle narrait faute d'outil. Désormais fenêtre glissante sur les 3 derniers messages
  utilisateur → le domaine (ex. rédaction) reste exposé sur les tours de suivi.

### 🔧 Intégration des corrections de cohérence opérationnelle
- `_llm_corrections` ignorait la consigne (prompt codé « ne change pas le sens ») → « intègre
  les corrections de cohérence » ne produisait RIEN. Nouveau mode CONSIGNE : applique les
  corrections demandées (cohérence, continuité, faits, chronologie, climat…) en fragments
  ponctuels {old→new} (toujours en modifications suivies, jamais de réécriture globale).

### 📤 L'atelier fonctionne SANS Nextcloud (fichiers uploadés)
- `document_open` accepte un .docx UPLOADÉ dans l'app (workspace/uploads) en plus d'un chemin
  Nextcloud. Révision/traduction → fichier produit déposé dans le workspace avec lien de
  téléchargement (`/api/workspace/download`). Nextcloud devient une source/destination
  OPTIONNELLE ; l'original reste toujours intact.


## v0.11.81 (Outils romans robustes + équipe nettoyée)

### 🧹 Agents redondants retirés du modèle d'équipe
- `agents.example.yaml` : suppression de Correcteur (Marc) et Traducteur (Sofia), désormais
  couverts par les outils document_* (révision en modifications suivies, cohérence, répétitions,
  traduction vivante). Évite qu'Athena délègue à un agent au lieu d'appeler l'outil.

### 🛡️ Appels d'outils document_* tolérants
- Les petits modèles nommaient mal les arguments (`file=`, `instructions=`, `langue=`) →
  remappage automatique vers les noms canoniques (nextcloud_path/instruction/target_language),
  kwargs inconnus ignorés au lieu de lever TypeError. Le schéma exposé au LLM reste correct.
- Consigne renforcée : appeler les outils document_* DIRECTEMENT (jamais via run_tool_script,
  ni `.run(...)`, ni recopiés en texte) ; pour intégrer des corrections de cohérence →
  `document_autorevise(chemin, instruction=...)`.


## v0.11.80 (Outils romans déclenchés en langage naturel)

### 🗣️ Plus besoin de nommer l'outil
- Mots-clés du domaine « rédaction » étendus (cohérence, incohérence, répétition, traduis,
  traduction, « en anglais/espagnol… ») → une demande naturelle (« vérifie la cohérence de mon
  roman », « traduis-le en anglais », « repère les répétitions ») expose désormais les outils
  document_* et Athena choisit le bon, sans qu'on ait à citer le nom de l'outil.


## v0.11.79 (Détection des répétitions à l'échelle du roman)

### 🔁 document_check_repetitions
- Nouvel outil **`document_check_repetitions(chemin)`** : analyse DÉTERMINISTE (sans LLM, exhaustive,
  pas de saturation) qui repère les **mots de contenu surutilisés** et les **tournures-tics**
  (groupes de mots réemployés) sur tout le document. LECTURE SEULE → rapport. Complète
  `document_autorevise` (qui ne corrige que les répétitions locales).


## v0.11.78 (Traduction VIVANTE de roman)

### 🌍 document_translate : traduire un roman de façon vivante (pas mot-à-mot)
- Nouvel outil **`document_translate(chemin, langue)`** : traduit un .docx chapitre par chapitre
  dans la langue cible, en traduction **littéraire et naturelle** (préserve la voix de l'auteur,
  le ton, le rythme ; adapte les idiomes ; garde les noms propres). Crée un NOUVEAU fichier
  « <nom> (<langue>).docx » sur Nextcloud — l'original reste intact. Contexte borné (lots par
  chapitre). Validé sur l'endpoint réel (gemma rend une VO naturelle, pas littérale).


## v0.11.77 (Vérification de cohérence narrative)

### 🔎 document_check_coherence : détecter les incohérences d'un roman
- Nouvel outil **`document_check_coherence(chemin)`** : analyse un .docx **chapitre par chapitre**
  en maintenant une « bible » (canon : personnages, traits, lieux, règles, chronologie) et signale
  les **contradictions** (ex. yeux verts ch.1 → bleus ch.7, nom de lieu mal orthographié, règle de
  magie contredite). LECTURE SEULE → renvoie un **rapport**, ne modifie pas le texte.
- Contexte borné (1 chapitre + bible compacte) → pas de saturation sur un long roman.
- Validé sur l'endpoint réel (gemma et qwen3 détectent bien les incohérences).


## v0.11.76 (Révision de roman : corrections ciblées, plus de réécriture)

### ✍️ Révision par CORRECTIONS ponctuelles (fidèle par construction)
- Avant, `document_autorevise` demandait au LLM de RÉÉCRIRE chaque chapitre → le modèle changeait
  l'histoire et le diff marquait tout. Désormais le LLM renvoie une **liste de corrections**
  (`{ancien → nouveau}`) et on **n'applique QUE ces fragments**, en modifications suivies mot à mot.
- Résultat : seules les vraies fautes/lourdeurs (au sein des phrases) sont marquées ; l'intrigue,
  les noms et le texte non concerné restent **strictement intacts** — par construction, impossible
  de « changer l'histoire ». Changements fins, faciles à suivre/accepter dans OnlyOffice.


## v0.11.75 (Révision de roman : plus fine et fidèle)

### ✍️ Révisions mot à mot + consigne stricte (ne plus changer l'histoire)
- **Diff MOT À MOT** : les modifications suivies ne marquent plus le paragraphe entier (barré +
  réinséré) mais seulement les **fragments réellement modifiés** — bien plus lisible/suivable dans
  OnlyOffice (le texte inchangé reste en normal).
- **Consigne renforcée** : la révision est désormais une correction LÉGÈRE (orthographe, grammaire,
  redondances, fluidité) qui PRÉSERVE l'intrigue, les personnages, les noms et les faits — l'IA ne
  doit plus réécrire/changer l'histoire ni rien inventer, et garder le même découpage.


## v0.11.74 (Révision de roman en UN appel + garde-fou contexte)

### ✍️ document_autorevise : tout le roman en un seul outil
- Nouvel outil **`document_autorevise(chemin, instruction)`** : télécharge le .docx (original
  intact), **révise chaque chapitre via le LLM en contexte ISOLÉ** (plus de saturation), applique
  les **modifications suivies**, et publie « — révisé.docx ». Un SEUL appel d'outil → le modèle ne
  peut plus « raconter » 20 étapes sans agir. Option `chapter="3"` pour un seul chapitre.
- **Garde-fou contexte** : `document_read` sans chapitre ne déverse plus un roman entier (100k+
  caractères) dans le contexte — au-delà de `DOCUMENT_READ_CAP` (8000), il renvoie la liste des
  chapitres et invite à lire chapitre par chapitre.
- Préambule mis à jour pour pousser `document_autorevise`.


## v0.11.73 (Édition docs : exécutables en script + garde anti-narration)

### 🔧 Réduire l'hallucination d'outils sur l'édition de documents
- Les outils `document_*` et `nextcloud_*` sont désormais disponibles dans `run_tool_script`
  → l'agent peut enchaîner open→read→revise→publish en **un seul script** qui s'EXÉCUTE
  vraiment (avant, ces appels en script échouaient → l'agent retombait dans la narration).
- Préambule renforcé : pour réviser un document, l'agent DOIT appeler les outils et ne jamais
  affirmer « c'est fait » sans résultat d'outil.
- ⚠️ Limite honnête : un modèle local faible peut continuer à « raconter » au lieu d'agir —
  pour ce type de tâche multi-étapes, un modèle plus capable (orchestrateur) reste le levier #1.


## v0.11.72 (Édition de romans/.docx en modifications suivies)

### ✍️ Réviser un document long sans détruire l'original
- Nouvel atelier d'édition (`tools/document_editor.py`, dépendance `python-docx`) : Athena ouvre
  un `.docx` depuis Nextcloud dans un **workspace dédié** (l'original reste INTACT), le lit par
  **chapitre**, et applique des révisions en **MODIFICATIONS SUIVIES Word** (`w:ins`/`w:del`,
  auteur « Athena »). À la fin, une **copie « <nom> — révisé.docx »** est déposée sur Nextcloud.
  Tu l'ouvres dans **OnlyOffice** → tu vois les ajouts/suppressions et tu les **acceptes/refuses**.
- Outils : `document_open`, `document_read`, `document_revise`, `document_publish` (donnés à
  l'orchestrateur quand Nextcloud est configuré + aux agents Auteur/Correcteur). Garde `can_write`,
  anti-traversal, anti-SSRF.
- Test : `tests/test_document_editor.py`.


## v0.11.71 (Choix d'outils plus fiable + Nextcloud dispo pour Athena)

### 🎯 L'agent choisit mieux ses outils
- **Fini le « calendrier → Home Assistant »** : les outils « extra » (MCP, dont les 84 de HA, et
  skills) n'étaient exposés au modèle qu'en comblant un top-12 **au hasard** quand rien ne matchait
  → du bruit qui faisait partir l'agent sur le mauvais outil. Désormais on n'expose que les extras
  **réellement pertinents** (recouvrement de mots > 0).
- **Domotique préservée** : les outils Home Assistant (noms anglais) sont **ré-exposés quand la
  requête est domotique** (mots-clés FR : allume, lumière, salon…), donc « allume le salon » marche
  toujours sans polluer les autres requêtes.

### ☁️ Nextcloud accessible à Athena
- Les outils Nextcloud (Fichiers/Tâches/Contacts) sont **donnés automatiquement à l'orchestrateur**
  quand Nextcloud est configuré (plus besoin de les cocher par agent). « liste mes fichiers Nextcloud »
  fonctionne directement.

### ✅ Tests
- `tests/test_swarm.py::test_select_relevant_funcs_ne_garde_que_le_pertinent`.


## v0.11.70 (Retrait de l'OAuth Google)

### 🧹 OAuth Google retiré
- L'OAuth Google (Calendar + Gmail) est supprimé : sans HTTPS et sans client OAuth dédié, il ne
  pouvait pas offrir le « se connecter avec Google » en un clic attendu pour un usage homelab.
  Supprimés : `core/google_oauth.py`, `routers/oauth_google.py`, `tools/gmail_oauth.py`, le bloc
  UI et la doc associée. Le **compte de service** Google reste disponible (Réglages → Agenda).
- Pour l'agenda, **CalDAV/Nextcloud** est la voie recommandée (lecture+écriture OK).


## v0.11.69 (Telegram : indicateur « écrit… »)

### ✈️ Telegram : feedback immédiat
- Le bot envoie l'action « typing » (« Athena écrit… ») dès réception d'un message, pendant que
  l'essaim réfléchit → ressenti de latence amélioré (le temps de réponse vient du LLM, pas du bot).


## v0.11.68 (Agenda : événements horodatés enfin lus + fuseau configurable)

### 🐛 Fix majeur : les événements Nextcloud (avec fuseau) étaient SAUTÉS
- Le parseur ICS ne reconnaissait que `DTSTART:` / `DTSTART;VALUE=DATE:` → il **ignorait**
  `DTSTART;TZID=Europe/Paris:...` (le format par défaut de Nextcloud) → événements visibles
  dans Nextcloud mais **invisibles dans Athena**. Regex corrigé (n'importe quel paramètre).
- **Fuseau horaire correct** : les horodatages UTC (`...Z`) sont convertis en heure locale
  (avant : décalés de l'offset). L'écriture CalDAV se fait en **UTC explicite** (fini le
  `TZID` sans `VTIMEZONE` qui décalait de +2h).
- **Fuseau CONFIGURABLE** (plus de Europe/Paris en dur) : `AGENDA_TIMEZONE` par utilisateur
  (Réglages → Agenda), sinon le **fuseau système** de la machine, sinon repli Europe/Paris.
- Test : `tests/test_mcp_and_agenda.py::test_ics_parses_tzid_events_and_converts_utc`.


## v0.11.67 (CalDAV : lecture des événements réparée + diags)

### 🐛 Fix : `list_calendar_events` ne voyait pas les événements CalDAV (Nextcloud)
- La synchro CalDAV cherchait `<c:calendar-data>` (préfixe en dur), mais Nextcloud/SabreDAV
  renvoie sa réponse avec SON préfixe (souvent `<cal:calendar-data>`) → **0 événement lu** →
  l'agenda n'affichait que les événements locaux. Extraction rendue **indépendante du préfixe**.
- Outils de diagnostic ajoutés : `scripts/diag_caldav_write.py` (test d'écriture + origine d'un
  403 : Nextcloud vs Cloudflare) et `scripts/list_caldav_calendars.py` (liste les calendriers
  et donne l'URL exacte à coller — endpoint `/calendars/`, pas `/principals/`).
- Test : `tests/test_mcp_and_agenda.py::test_caldav_sync_extracts_any_namespace_prefix`.


## v0.11.66 (Agenda : choix du calendrier d'écriture)

### 📝 Sélecteur « où créer les événements »
- Quand plusieurs calendriers sont configurés (Google + CalDAV/Nextcloud), Athena écrivait
  toujours sur **Google en priorité** → les RDV finissaient dans un calendrier non visible
  (compte de service). Ajout d'un réglage **« Calendrier d'écriture »** (Réglages → Agenda) :
  **auto / CalDAV / Google / local**. `add_calendar_event` respecte ce choix (une cible
  indisponible retombe sur « auto »). Ex. choisir **CalDAV** → les RDV apparaissent dans Nextcloud.


## v0.11.65 (Anti-SSRF : plages CIDR dans l'allowlist — débloque Nextcloud/CalDAV LAN)

### 🛡️ Fix : `NET_GUARD_ALLOW_HOSTS` ne reconnaissait pas les plages CIDR
- Mettre `NET_GUARD_ALLOW_HOSTS=192.168.1.0/24` (une PLAGE) ne marchait pas : l'allowlist ne
  faisait qu'une comparaison de chaîne exacte → `192.168.1.10 ≠ "192.168.1.0/24"` → l'hôte
  restait bloqué → **synchro CalDAV/Nextcloud (et tout service LAN) vide**.
- **Correctif** : l'allowlist accepte désormais les **plages CIDR** (et les IP résolues d'un
  hostname dans une plage). La métadonnée cloud (169.254.169.254) reste toujours bloquée.
- Test : `tests/test_nextcloud.py::test_allowlist_supports_cidr`.


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
