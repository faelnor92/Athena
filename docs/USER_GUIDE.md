# 📖 Guide Utilisateur d'Athena

Bienvenue ! Si vous lisez ce guide, c'est que vous venez d'installer **Athena**, votre chef d'orchestre d'Intelligence Artificielle multi-agents. Ce document est pensé pour vous aider à prendre en main l'outil.

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
- **L'Explorateur de fichiers (Workspaces)** : Sur la gauche se trouve un panneau contenant vos fichiers. Vous pouvez y glisser-déposer des documents (PDF, Markdown, code source) pour que l'IA puisse les analyser. 

### B. Depuis la Console Interactive (CLI)
Si vous préférez le terminal à l'interface graphique, vous pouvez lancer une discussion textuelle pure.
Allez dans le dossier d'Athena et tapez :
`python3 athena_cli.py`

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
- **Navigation Git & Code** : L'IA peut lire vos dépôts Git, comprendre votre code source existant et l'éditer en direct.
- **Maintenance autonome** : Un agent nocturne peut vérifier et réparer le code source automatiquement.

### 🏠 Domotique, Contexte & Quotidien
- **Domotique (Home Assistant)** : Grâce au protocole MCP, Athena interagit avec votre maison. Demandez-lui *"Éteins la lumière du salon"*.
- **Conscience Spatiale** : L'IA peut savoir dans quelle pièce vous vous trouvez (si vous avez des capteurs) pour adapter ses actions (ex: *"Allume la lumière"* allumera celle de la pièce où vous êtes).
- **Météo & Temps** : Prévisions météorologiques sur plusieurs jours et synchronisation temporelle.
- **Listes & Courses** : Demandez-lui de rajouter du lait sur votre liste de courses ou de créer une Todo-list.

### 📅 Productivité & Communication
- **Agenda & Planification** : Synchronisation avec vos calendriers (iCal, CalDAV) pour lire et créer des événements.
- **Résumés de Réunions** : Capacité à transcrire et résumer des réunions ou des fichiers audios.
- **Notifications** : Athena peut vous envoyer des messages de son plein gré sur Telegram, Discord ou Slack.
- **Génération Média** : Création d'images (via API Fal/Replicate) et manipulations de fichiers (PDF, documents).
- **Workflows (n8n)** : Déclenchement de scénarios complexes via des webhooks n8n.

### ⏰ Routines Proactives
Athena n'attend pas que vous lui parliez. Demandez-lui : *"Fais-moi un résumé de ma journée tous les matins à 7h30"*. Elle se réveillera toute seule, analysera votre agenda, la météo, l'état de votre maison, et pourra même déclencher la cafetière !

---

## 4. ⚙️ Comprendre les Paramètres de l'Interface

En cliquant sur l'icône d'engrenage (⚙️) dans la barre latérale, vous accédez aux réglages de votre profil. **Chaque paramètre est strictement isolé pour votre utilisateur.**

### Onglet "Profil & Espace de Travail"
- **Prénom & Email** : C'est ici que l'IA va chercher comment vous appeler.
- **Changement de mot de passe** : Permet de modifier le mot de passe de votre compte.
- **Projets Partagés** : Permet d'inviter d'autres utilisateurs du serveur dans votre dossier de travail en mode "Lecteur" ou "Éditeur".

### Onglet "Mon Modèle & Clés LLM"
- **Fournisseur IA (Ex: OpenAI, Anthropic, Ollama)** et **Nom du Modèle** : Choisissez la version de l'IA que vous souhaitez utiliser.
- **Clé API Personnelle** : Si ce champ est rempli, Athena utilisera VOTRE clé pour fonctionner, et vous serez facturé sur votre propre compte développeur. Cela permet de surcharger le modèle par défaut du serveur.

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

#### 3. Orchestration & agents (avancé)
- `Aiguillage LLM (Delegation Router)` : L'Orchestrateur lit votre message et choisit le bon agent. 
- `Modèle rapide` : Vous pouvez forcer un modèle très rapide (ex: `gpt-4o-mini` ou `haiku`) juste pour les prises de décision de routage, ce qui rend l'IA plus nerveuse.
- `Modèles de repli (Fallback)` : Si l'API de votre IA principale plante, Athena tentera d'utiliser ces modèles de secours.
- `Cache de prompt` : Technologie permettant d'économiser de l'argent et du temps sur les longues conversations.
- `Auto-critique` : Si activé, l'IA relit et vérifie sa propre réponse avant de vous l'envoyer.

#### 4. Mémoire
- `Base de faits (Core Memory)` : Liste tout ce qu'Athena a appris sur vous de façon permanente (vos goûts, votre métier). Vous pouvez y supprimer des éléments.
- `Knowledge Graph` : En plus des faits simples, l'IA construit un réseau de relations ("Graphe") entre les entités pour mieux comprendre votre contexte.
- `Compaction au-delà de N messages` : Pour éviter de faire exploser la facture, Athena résume automatiquement les vieilles parties de la conversation au bout de N messages (40 par défaut).
- `Messages récents gardés mot pour mot` : Athena garde toujours les N derniers échanges stricts en mémoire à court terme (12 par défaut).

#### 5. Voix expressive
- `Émotions vocales` : Le LLM insère des balises `[laugh]`, `[sad]` dans ses textes, et le moteur vocal adapte son ton !
- `Serveur TTS expressif & Voix` : Si vous utilisez un moteur vocal tiers (comme XTTS), renseignez son adresse IP ici.

#### 6. Conscience Spatiale (Présence / follow-me)
- `Entité HA de pièce courante` : Si vous avez des détecteurs de présence sur Home Assistant, indiquez ici l'entité (ex: `sensor.piece_actuelle`). L'IA saura alors dans quelle pièce vous êtes pour y allumer la bonne lumière ou adapter son comportement.

#### 7. Automatisation (n8n)
- `Workflows autorisés` : Vous pouvez connecter Athena à des automatisations n8n complexes en lui donnant accès à des adresses web (Webhooks).

### Les autres Onglets du Panneau de Réglages
En plus de "Comportement", la barre latérale des réglages vous donne accès à d'autres menus spécialisés :

* **Onglet "Connaissances (RAG)"** : C'est ici que vous pouvez demander à l'IA d'analyser (ou de purger) les documents que vous avez placés dans l'Explorateur de fichiers.
* **Onglet "Routines"** : Permet de programmer des tâches automatiques (ex: "Fais le résumé de la maison tous les jours à 7h00"). Vous pouvez aussi y récupérer les adresses "Webhooks" de ces routines.
* **Onglet "Satellites Vocaux"** : Permet de configurer les enceintes ESP32 connectées à Athena.
* **Onglet "Extensions MCP"** : Permet de brancher des plugins externes standards (ex: connecteur GitHub, connecteur Home Assistant) à l'IA.
* **Onglet "Diagnostics & Système"** : Vérifie la santé de l'installation (base de données, STT, TTS). C'est ici que se trouve le bouton d'urgence **Redémarrer le moteur Vocal (Kokoro)** en cas de bug sonore.
* **Onglet "Utilisateurs" (Admin)** : Si vous êtes administrateur, vous pouvez ici inviter de nouvelles personnes sur votre serveur et gérer leurs droits.

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
