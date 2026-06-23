# 📖 Guide Utilisateur d'Athena

🌍 **Langues** : Français · [English](USER_GUIDE.en.md) · [Español](USER_GUIDE.es.md) · [Italiano](USER_GUIDE.it.md) · [Deutsch](USER_GUIDE.de.md) · [中文](USER_GUIDE.zh.md) · [日本語](USER_GUIDE.ja.md)

Bienvenue ! Si vous lisez ce guide, c'est que vous venez d'installer **Athena**, votre chef d'orchestre d'Intelligence Artificielle multi-agents. Ce document est pensé pour vous aider à prendre en main l'outil.

---

## ✨ Nouveautés de la version 0.28.0

- **Modèle dédié au Design et au Code** : dans **Réglages → Mon modèle & clés LLM**, choisissez un modèle spécifique pour **AthenaDesign** (🎨) et pour la **console Code** (🧩), différent de celui du chat (ex. un modèle « coder » pour le code, un autre pour la conversation). Les listes ne proposent que les modèles **réellement accessibles** (votre endpoint + les fournisseurs dont la clé est renseignée).
- **Compteur de tokens en temps réel** : la consommation **entrante (↓) et sortante (↑)** s'affiche en direct pendant la génération (chat, design, code). Un **cumul global** figure dans la barre du haut — **persistant** (conservé entre les redémarrages) avec un bouton **↺** pour le remettre à zéro.
- **Console Code en direct** : les étapes de l'agent et la consommation s'affichent **au fil de l'eau** (streaming), comme le chat, sans attendre la fin.
- **AthenaDesign amélioré** : une modification repart désormais de la **version que vous regardez** (et non plus systématiquement de la dernière) ; designs plus **modernes** ; l'auto-correction détecte aussi les **écrans blancs** dus au CSS.

---

## 1. 🌟 Premier Lancement et Connexion

Une fois Athena installé et démarré sur votre machine, l'interface graphique (UI) n'est accessible que via votre navigateur web.

1. Ouvrez votre navigateur et allez sur l'adresse : **`http://localhost:8000`** (ou l'adresse IP de votre serveur si vous l'avez installé sur une autre machine).
2. S'il s'agit du tout premier lancement, on vous demandera de créer un compte avec une adresse email et un mot de passe.
3. Une fois connecté, vous arrivez sur le **Bureau virtuel**.

---

## 2. 💬 Discuter avec l'IA

Il existe **deux moyens** d'interagir avec Athena : l'Interface Web et le Terminal (CLI).

### A. Depuis l'Interface Web (UI)
C'est la méthode la plus visuelle et la plus simple.
- **La vue 3D** : Sur la page principale, vous verrez une représentation visuelle d'Athena et de ses "Agents" (Le Codeur, Le Chercheur, etc.). Lorsqu'Athena réfléchit ou délègue une tâche, vous verrez des animations lumineuses vous indiquant quel agent est en train de travailler.
- **L'Orchestrateur automatique** : Dans la barre de discussion en bas, écrivez simplement votre requête. Dans l'Interface Web, **vous parlez toujours à l'Orchestrateur**. C'est lui qui est assez intelligent pour comprendre votre demande et l'assigner automatiquement au bon agent (ex: il passera le relais à l'Agent Codeur si vous demandez un script).
- **Artifacts dans le chat** : quand l'IA produit du code prévisualisable (HTML, **React**, SVG, **Mermaid**, **Markdown**), un bouton **« 👁️ Aperçu »** ouvre un **panneau d'aperçu docké** à droite — exécuté dans un bac à sable isolé. Vous **naviguez entre les versions** générées au fil de la conversation, **copiez/téléchargez** le code, ou cliquez **« 🎨 Ouvrir dans AthenaDesign »** pour poursuivre dans le studio.
- **L'Explorateur de fichiers (Workspaces)** : Sur la gauche se trouve un panneau contenant vos fichiers. Vous pouvez y glisser-déposer des documents (PDF, Markdown, code source) pour que l'IA puisse les analyser.
- **L'Éditeur intégré (mini-IDE)** : cliquez sur un fichier pour l'**éditer** directement dans le navigateur — plusieurs fichiers ouverts en **onglets**, coloration syntaxique, autocomplétion (Ctrl+Espace), et **enregistrement** avec **Ctrl+S** (💾). Un *Lecteur* d'un projet partagé reste en lecture seule. Vous pouvez **rétrécir ou replier l'explorateur** (poignée centrale ou bouton « ◀ Réduire ») pour agrandir l'éditeur, et quand l'**agent modifie un fichier ouvert**, votre vue se **rafraîchit en direct** (avec la présence des autres lecteurs).
- **La Console Codeur (Terminal interactif)** : un véritable terminal où vous parlez à l'agent **Codeur** pour développer. Spécificités :
  - **Projet ciblé indépendant** : un sélecteur permet de coder sur un projet **différent** de celui du chat/vocal (vos commandes vocales et la domotique continuent sur leur contexte).
  - **Arborescence du projet** à droite (le chat y est masqué car inutile) : elle se **rafraîchit automatiquement** — vous voyez les fichiers créés par l'agent apparaître.
  - **IDE en fenêtre séparée** : le bouton **« ⧉ IDE »** (ou un clic sur un fichier de l'arbre) ouvre l'éditeur dans une **vraie fenêtre déplaçable** (idéale sur un 2ᵉ écran), avec onglets, coloration, autocomplétion et **Ctrl+S**. *(Au 1ᵉʳ usage, autorisez les pop-ups pour le site.)*
  - Les commandes préfixées `$` ou `!` s'exécutent directement comme du shell ; sinon l'agent Codeur traite votre demande et **écrit les fichiers dans le projet** (sandbox Docker montée sur le projet).

### C. Projets & Collaboration (Workspaces partagés)
Un **projet** est un dossier de travail dédié. Quand vous sélectionnez un projet dans la barre de projets (en haut de l'explorateur), **tout ce que fait l'IA (lecture, édition de code, terminal, git) est confiné à ce dossier** — pratique pour isoler un dépôt de code ou un dossier client.
- **Créer / changer de projet** : bouton `＋ Projet` puis sélection dans la liste. Chaque utilisateur a ses propres projets, invisibles des autres.
- **Partager un projet** (bouton `👥 Partager`) : en tant que **propriétaire**, vous invitez d'autres utilisateurs et choisissez leur rôle :
  - **Lecteur** : peut consulter et discuter avec l'IA sur le projet, mais **ne peut RIEN modifier** — même en demandant à l'agent (le verrou est appliqué côté serveur, sur chaque outil d'écriture : édition de fichier, git, bash, Python). Impossible à contourner.
  - **Éditeur** : peut modifier les fichiers, lancer du code, commiter.
- Seul le propriétaire peut partager, changer les rôles ou supprimer le projet.

### B. Depuis la Console Interactive (CLI)
Si vous préférez le terminal à l'interface graphique, vous pouvez lancer une discussion textuelle pure.
Allez dans le dossier d'Athena et tapez :
`python3 athena_cli.py`

#### ⚙️ Fonctionnalités du CLI (Console Interactive)
- **Approbations interactives** : Pour assurer la sécurité, toute action sensible (comme l'exécution de commandes bash ou d'actions système) requiert une confirmation manuelle directe dans le terminal (`[y/N]`).
- **Commandes Slash** : Dans la console de l'Agent Codeur (`coder_cli.py`), vous pouvez utiliser des raccourcis comme `/clear` (effacer l'historique), `/exit` (quitter) ou `/help` (lister les commandes).
- **Règles locales** : Athena charge et applique automatiquement les instructions ou règles définies dans un fichier `.athena-rules.md` ou `.claudecode.md` situé à la racine de votre workspace, vous permettant de personnaliser son comportement par projet.

> [!TIP]
> **Forcer un agent spécifique (Console uniquement)** : Contrairement à l'interface web où l'Orchestrateur gère tout, la console vous permet de contourner le chef et de parler directement à un agent spécialiste. Pour cela, utilisez : 
> `python3 athena_cli.py --agent Codeur`

---

## 3. 🛠️ Que peut faire Athena ? (Les Super-Pouvoirs)

Athena n'est pas un simple "ChatGPT". C'est un framework d'**agents d'intelligence artificielle autonomes** qui intègrent des dizaines d'outils ("Skills") capables d'agir sur votre machine et sur le web.

### 💻 Code Agentique (Software Engineering)
C'est le cœur du système. Athena peut remplacer un administrateur système ou un développeur :
- **Exécution Python & Bash (Sandbox)** : L'IA écrit du code et l'exécute de manière autonome dans un bac à sable Docker sécurisé.
- **Création de Skills à la Volée** : Fonctionnalité unique, l'IA peut coder de nouveaux "outils" pour s'améliorer elle-même, et les enregistrer définitivement dans son code source de base !
- **Administration SSH** : L'IA peut se connecter à vos autres serveurs distants via SSH pour faire de la maintenance.
- **Computer Use (RPA 2.0)** : L'IA peut ouvrir un vrai navigateur web caché, cliquer sur des boutons, remplir des formulaires et scraper des sites.
- **Navigation Git & Code** : L'IA peut lire vos dépôts Git, comprendre votre code source existant et l'éditer en direct (recherche `glob`/contenu, plan de fichier, références).
- **Diagnostics après édition (boucle de feedback)** : à chaque modification de fichier, Athena relit les **erreurs/avertissements** introduits (serveur LSP **basedpyright** pour Python, repli intégré sinon) et les **corrige immédiatement**. Ces diagnostics s'affichent aussi dans l'onglet **Code** (bouton « 🔍 Analyser »).
- **Liste de tâches de session** : pour un travail en plusieurs étapes, l'agent tient une **checklist** (📋 Tâches) visible dans `athena_cli` et l'onglet Code, mise à jour en temps réel.
- **Mode plan (lecture seule)** : bouton **« 🧭 Mode plan »** (ou `/plan` / `/build` en CLI) — l'agent **propose un plan sans rien modifier** ; repassez en mode normal pour exécuter.
- **Instructions de projet** : posez un `CLAUDE.md`, `ATHENA.md` ou `AGENTS.md` à la racine de votre projet (conventions, commandes) — Athena les charge automatiquement, en cascade jusqu'à la racine git.
- **Maintenance autonome** : Un agent nocturne peut vérifier et réparer le code source automatiquement.

### 🎨 AthenaDesign Studio (Design IA)
Un studio de design intégré (onglet **🎨 Design**). Décrivez ce que vous voulez créer, Athena le génère et l'**affiche en direct** :
- **Types** : pages web (HTML/CSS/JS), **apps React** interactives, **diagrammes Mermaid**, et scripts **Python** (présentations **PowerPoint**, graphiques). Des **modèles de départ** (Landing, Pitch deck, Dashboard…) pré-remplissent un prompt.
- **Votre charte (Design System)** : panneau « Design System » pour donner vos couleurs/police — à la main, en collant un CSS, via **« 🌐 D'une URL »**, ou en la **générant automatiquement** : **« 🧩 Depuis le code »** (déduite du projet : Tailwind/CSS), **« 🖼️ Depuis une image »** (palette/typo d'une capture), **« ✨ Depuis une description »** (charte de départ pour un projet vide).
- **Références** : joignez une image/un document (📎) ou une page web (🔗) comme inspiration.
- **Affiner** : annotez l'aperçu, ajustez en direct (sliders couleur/arrondi/police), parcourez les versions. Si un script Python échoue, Athena **se corrige toute seule**.
- **Partager / exporter** : bouton **Partager** (lien lecture seule), **Export PDF**, et téléchargement des `.pptx`.
- *Astuce* : un projet Athena réunit **code et design** — vous gérez les deux au même endroit.

### 🔌 Plugins (dont Claude Code)
Dans **Réglages > 🔌 Plugins**, activez des extensions. Le **plugin Claude Code** fait appel à l'agent de code **Claude Code** (il faut le CLI `claude` installé et connecté) : une fois activé, votre **Codeur** peut lui déléguer les tâches de code complexes, directement dans le projet actif. *(Consomme votre abonnement/clé Claude.)*

### 🏠 Domotique, Contexte & Quotidien
- **Domotique Native (Home Assistant)** : L'IA se connecte directement à votre domotique. Demandez-lui *"Éteins la lumière du salon"* ou *"Ferme les volets"* et elle le fait instantanément.
- **Extensions MCP (Avancé)** : Athena supporte le protocole MCP. Cela lui permet de brancher des plugins complexes (comme un accès profond à la base de données de Home Assistant pour créer des automatisations, ou tout autre serveur MCP existant).
- **Conscience Spatiale** : L'IA peut savoir dans quelle pièce vous vous trouvez (si vous avez des capteurs) pour adapter ses actions (ex: *"Allume la lumière"* allumera celle de la pièce où vous êtes).
- **Météo & Temps** : Prévisions météorologiques sur plusieurs jours et synchronisation temporelle.
- **Listes & Courses** : Demandez-lui de rajouter du lait sur votre liste de courses ou de créer une Todo-list. Option : **synchronisation bidirectionnelle avec Nextcloud Notes** (Réglages → Nextcloud) — vos listes deviennent des notes Markdown modifiables depuis l'app Notes sur mobile, et inversement.
- **Voix : qui parle ?** Avec un satellite vocal, Athena peut **reconnaître chaque membre du foyer** (empreinte vocale) et répondre avec **son** agenda / ses listes / sa mémoire. Enrôlement : `python3 voice_assistant.py enroll prénom échantillon.wav`.

### 📅 Productivité & Communication
- **Agenda & Planification** : Synchronisation avec vos calendriers (iCal, CalDAV) pour lire et créer des événements.
- **Résumés de Réunions** : Capacité à transcrire et résumer des réunions ou des fichiers audios.
- **Notifications** : Athena peut vous envoyer des messages de son plein gré sur Telegram, Discord ou Slack.
- **Génération Média** : Création d'images (via API Fal/Replicate) et manipulations de fichiers (PDF, documents).
- **Workflows (n8n)** : Déclenchement de scénarios complexes via des webhooks n8n.

### ⏰ Routines Proactives
Athena n'attend pas que vous lui parliez. Demandez-lui : *"Fais-moi un résumé de ma journée tous les matins à 7h30"*. Elle se réveillera toute seule, analysera votre agenda, la météo, l'état de votre maison, et pourra même déclencher la cafetière !

### 🧭 Continuité : objectifs & « fil d'Ariane »
Athena garde le fil sur la durée :
- **Objectifs persistants** : dites *"Note comme objectif : migrer le serveur mail, en 3 étapes"*. Elle suit l'objectif, ses étapes et leur avancement, et vous le rappelle d'elle-même au fil des échanges (*"où en est-on sur la migration ?"*).
- **Mettre une tâche de côté (parenthèse)** : en plein travail, dites *"Attends, mets ça de côté, on regarde un souci sur la base de données"*. Athena **gèle** la tâche en cours (et son environnement Docker) et démarre un fil propre. Quand vous dites *"c'est bon, on reprend"*, elle **restaure tout** exactement où vous en étiez.
- **Mémoire qui apprend (Chronos)** : elle retient les faits durables (vos proches, vos machines, vos préférences) et les réutilise — plus besoin de tout réexpliquer.

### 👁️ Surveillance proactive (Vigie)
Athena peut **réagir toute seule** quand quelque chose se passe sur votre infrastructure :
- Vos outils de supervision (Zabbix, Grafana, LibreNMS, Home Assistant, sondes SNMP…) **poussent** un événement vers Athena. Rien ne tourne en boucle : elle ne se réveille que lorsqu'un événement arrive.
- Elle **analyse**, vous **alerte** (Telegram/notification) et **propose un correctif**.
- **Validation à distance (HITL)** : pour toute action sensible (redémarrer un service, modifier une config…), Athena **se met en pause** et vous envoie une demande avec boutons **✅ Autoriser / ⛔ Refuser** sur Telegram. Vous décidez depuis votre téléphone ; l'action ne s'exécute qu'après votre accord.
- Réglage dans **Réglages → 👁️ Vigie** : activez, choisissez la sévérité minimale, le chat Telegram destinataire, et générez le **jeton** à mettre dans vos outils de supervision (`POST /api/events`, en-tête `X-Event-Token`).

---

## 4. ⚙️ Comprendre les Paramètres de l'Interface

En cliquant sur l'icône d'engrenage (⚙️) dans la barre latérale, vous accédez aux réglages de votre profil. **Chaque paramètre est strictement isolé pour votre utilisateur.**

### Onglet "🔑 Clés API" (Mon Modèle & Clés LLM)
- **Fournisseur IA (Ex: OpenAI, Anthropic, Ollama)** et **Nom du Modèle** : Choisissez la version de l'IA que vous souhaitez utiliser.
- **Clé API Personnelle** : Si ce champ est rempli, Athena utilisera VOTRE clé pour fonctionner, et vous serez facturé sur votre propre compte développeur. Cela permet de surcharger le modèle par défaut du serveur.
- **📊 Mon usage** : juste sous vos clés, un récapitulatif de votre consommation personnelle (requêtes, tokens, coût €) sur aujourd'hui, les 30 derniers jours et au total — pour suivre vos dépenses en un coup d'œil. (Un administrateur voit, lui, la consommation de tous les comptes.)

### 🔐 Sécuriser mon compte (onglet « Utilisateurs »)
- **Mon mot de passe** : changez-le quand vous voulez (min. 8 caractères). Par sécurité, changer votre mot de passe **déconnecte vos autres sessions**.
- **Authentification à deux facteurs (2FA)** : cliquez sur **Activer la 2FA**, ajoutez le compte dans votre application d'authentification (Google Authenticator, Authy, FreeOTP…) en scannant/saisissant le secret affiché, puis entrez un code pour confirmer. À chaque connexion, un **code temporaire** vous sera alors demandé en plus du mot de passe. Vous pouvez la désactiver à tout moment (un code est requis pour confirmer).
  - *Appareil perdu ?* Un administrateur peut réinitialiser votre 2FA pour vous redonner l'accès.

### Onglet "Agenda & Todo"
- **Agenda Principal (URL)** : Collez l'adresse d'un flux iCal (Google Calendar). L'IA pourra alors lire votre planning.
- **Serveur CalDAV (URL, Utilisateur, Mot de passe)** : Si vous utilisez un agenda avancé (Nextcloud, Synology), l'IA pourra *créer* et *modifier* des événements directement.

### Onglet "Comportement & Sécurité" (Le Cerveau d'Athena)
C'est la section la plus importante pour ajuster le comportement global et les sécurités de la machine. Elle est divisée en plusieurs sous-sections :

#### 1. Exécution & garde-fous
- `Sandbox d'exécution de code/commandes` : Choisissez **Docker** (recommandé) pour que l'IA exécute ses scripts dans un bac à sable sécurisé, ou **Local** si vous voulez qu'elle agisse directement sur votre système d'exploitation.
- `Auto-amélioration` : Autorise l'IA à tirer des leçons de ses échecs pour créer des règles de comportement futures.
- `Budgets (Temps et Tokens)` : Sécurités financières. Permet de brider le nombre de secondes maximum (0 = infini) ou le nombre de jetons maximum que l'IA a le droit de consommer par tâche.
- `Alerte coût du jour` : Si la dépense journalière dépasse ce seuil en euros, vous recevrez une notification.

#### 2. Sécurité
- `Auto-approuver les outils sensibles` : Par défaut (décoché), l'IA vous demandera toujours une confirmation avant d'utiliser un outil marqué comme "sensible" (ex: écrire dans un fichier système). Si vous le cochez, l'IA devient totalement autonome (à vos risques et périls).
- `Mot de passe admin / Origines CORS` : Sécurisation du serveur web pour empêcher les connexions extérieures non désirées.
- `Durée de validité d'une session` : Temps (en heures) avant d'être déconnecté de l'interface (défaut: 168h, soit une semaine).
- `Quotas et Limites` : Le système protège vos finances. Un administrateur peut définir une limite de consommation de tokens par jour dans la base des utilisateurs.
- `Chiffrement au repos` : Les conversations et les traces d'exécution sont chiffrées en base (SQLite) via Fernet (AES-128-CBC + HMAC). La clé est stockée dans le `.env` de votre installation — **ne la perdez pas** (sinon l'historique chiffré devient illisible), et pour une vraie protection contre le vol de disque, conservez-la hors du dossier (variable d'environnement injectée / secret-manager).
- `Protections intégrées (invisibles)` : Athena masque automatiquement vos clés API et secrets dans les logs (Redaction) et intègre une protection anti-SSRF bloquant les requêtes web vers votre réseau interne ou vos métadonnées Cloud.

#### 3. Orchestration & agents (avancé)
- `Aiguillage LLM (Delegation Router)` : L'Orchestrateur lit votre message et choisit le bon agent. 
- `Modèle rapide` : Vous pouvez forcer un modèle très rapide (ex: `gpt-4o-mini` ou `haiku`) juste pour les prises de décision de routage, ce qui rend l'IA plus nerveuse.
- `Modèles de repli (Fallback)` : Si l'API de votre IA principale plante, Athena tentera d'utiliser ces modèles de secours.
- `Cache de prompt` : Technologie permettant d'économiser de l'argent et du temps sur les longues conversations.
- `Auto-critique` : Si activé, l'IA relit et vérifie sa propre réponse avant de vous l'envoyer.

#### 4. Mémoire
- `Base de faits (Core Memory)` : Liste tout ce qu'Athena a appris sur vous de façon permanente (vos goûts, votre métier). Vous pouvez y supprimer des éléments.
- `Knowledge Graph` : En plus des faits simples, l'IA construit un réseau de relations ("Graphe") entre les entités pour mieux comprendre votre contexte.
- `Chronos (extraction automatique)` : à la fin d'un échange, Athena range automatiquement les faits durables dans le graphe ; au début, elle réinjecte ce qui est pertinent. Résultat : elle résout « le serveur de dev » ou « ma femme » sans qu'on réexplique. (Réglable via `GRAPH_AUTO_EXTRACT` / `GRAPH_CONTEXT_INJECT`.)
- `Objectifs & conscience situationnelle` : les objectifs actifs, les parenthèses en cours et la pièce courante sont rappelés à Athena à chaque échange — elle ne perd pas le fil.
- `Compaction au-delà de N messages` : Pour éviter de faire exploser la facture, Athena résume automatiquement les vieilles parties de la conversation au bout de N messages (40 par défaut).
- `Messages récents gardés mot pour mot` : Athena garde toujours les N derniers échanges stricts en mémoire à court terme (12 par défaut).

#### 5. Voix expressive
- `Émotions vocales` : Le LLM insère des balises `[laugh]`, `[sad]` dans ses textes, et le moteur vocal adapte son ton !
- `Serveur TTS expressif & Voix` : Si vous utilisez un moteur vocal tiers (comme XTTS), renseignez son adresse IP ici.

#### 6. Conscience Spatiale (Présence / follow-me)
- `Entité HA de pièce courante` : Si vous avez des détecteurs de présence sur Home Assistant, indiquez ici l'entité (ex: `sensor.piece_actuelle`). L'IA saura alors dans quelle pièce vous êtes pour y allumer la bonne lumière ou adapter son comportement.

#### 7. Automatisation (n8n)
- `Workflows autorisés` : Vous pouvez connecter Athena à des automatisations n8n complexes en lui donnant accès à des adresses web (Webhooks).

#### 8. Rédaction & Vision (modèles dédiés)
- `Modèle de rédaction` (atelier d'écriture) et `Modèle d'analyse d'images` se choisissent désormais dans une **liste déroulante dynamique** (les modèles réellement disponibles sur votre endpoint, comme pour les agents). Laissez vide pour le modèle d'Athena par défaut.

> 💡 Le panneau **« Comportement »** a été repensé : réglages en **cartes repliables** avec descriptions en clair, **interrupteurs** visuels et **barre de recherche** pour retrouver un réglage. L'interface est aussi **responsive** (mobile/tablette).

### Les autres Onglets du Panneau de Réglages
En plus de "Comportement", la barre latérale des réglages vous donne accès à d'autres menus spécialisés :

* **Onglet "Connaissances (RAG)"** : C'est ici que vous pouvez demander à l'IA d'analyser (ou de purger) les documents que vous avez placés dans l'Explorateur de fichiers.
* **Onglet "Routines"** : Permet de programmer des tâches automatiques (ex: "Fais le résumé de la maison tous les jours à 7h00"). Vous pouvez aussi y récupérer les adresses "Webhooks" de ces routines, ou faire en sorte qu'une routine **déclenche un Workflow** déterministe (champ « Workflow » du formulaire) au lieu d'une simple tâche.
* **Onglet "👁️ Vigie (événements)"** : Active la **surveillance proactive**. Activez-la, choisissez la sévérité minimale traitée, le compte et le **chat Telegram** destinataire des alertes/validations, et **générez le jeton** à donner à vos outils de supervision. Ceux-ci poussent alors les alertes sur `POST /api/events` (en-tête `X-Event-Token`). Bouton **« Émettre un test »** pour vérifier le pipeline de bout en bout, et un **journal** des derniers événements reçus.
* **Onglet "Messageries"** : Gère le bot **Telegram** (appairage des contacts) et — important — permet de **lier chaque chat Telegram à un compte Athena**. Sans cette liaison, les messages Telegram tournent sur le compte « local » et ne voient pas votre agenda/mémoire personnels.
* **Onglet "Nextcloud"** : URL/identifiants Nextcloud (fichiers, tâches, contacts) **et** l'option de **synchronisation des listes avec Nextcloud Notes**.
* **Onglet "Satellites Vocaux"** : Permet de configurer les enceintes ESP32 connectées à Athena.
* **Onglet "Extensions MCP"** : Permet de brancher des plugins externes standards (ex: connecteur GitHub, connecteur Home Assistant) à l'IA.
* **Onglet "Diagnostics & Système"** : Vérifie la santé de l'installation (base de données, STT, TTS). C'est ici que se trouve le bouton d'urgence **Redémarrer le moteur Vocal (Kokoro)** en cas de bug sonore, ainsi que les options de **Sauvegarde & Restauration** de votre environnement complet.
* **Onglet "Workflows"** : Crée des **pipelines déterministes** (chaîne d'agents, type "assembly line") en alternative au mode autonome — utile quand on veut un déroulé reproductible et auditable. Voir la section dédiée plus bas.
* **Onglet "Utilisateurs" (Admin)** : Si vous êtes administrateur, vous pouvez ici inviter de nouvelles personnes, gérer leurs droits et leurs quotas de tokens. Vous y **validez aussi les automatisations** (workflows/routines) créées par les comptes "utilisateur" avant qu'elles ne puissent s'exécuter, vous pouvez **réinitialiser la 2FA** d'un compte (appareil perdu), et consulter le **journal d'audit** (connexions, changements de mot de passe, validations…) via `GET /api/audit`.

---

## 5. 💻 Gérer le Serveur (Commandes d'Administration)

Si vous êtes l'administrateur de la machine hébergeant Athena, vous disposez de commandes systèmes puissantes pour gérer le cycle de vie du serveur.

### 🍎 Linux & macOS
Ouvrez votre Terminal. La commande principale s'appelle `athena`.
- `athena start` : Allume l'IA en arrière-plan (processus SystemD / LaunchAgent).
- `athena stop` : Éteint le serveur proprement.
- `athena restart` : Relance complètement l'application.
- `athena status` : Vérifie si le serveur est bien en ligne.
- `athena logs` : Affiche le journal technique du serveur en temps réel. (Faites `Ctrl+C` pour quitter).

**Mettre à jour le logiciel :**
Allez dans le dossier du code source et lancez : `./update.sh`

### 🪟 Windows (PowerShell)
Ouvrez PowerShell. La commande d'administration se termine par `.ps1`.
- `athena.ps1 start` : Démarre le serveur en tâche de fond.
- `athena.ps1 stop` : Coupe le serveur.
- `athena.ps1 restart` : Redémarre le processus.
- `athena.ps1 status` : Affiche l'état.
- `athena.ps1 logs` : Affiche la console technique de l'orchestrateur.

**Mettre à jour le logiciel :**
Allez dans le dossier du code source et lancez : `.\update.ps1`
