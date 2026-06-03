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

## 3. 🛠️ Que peut faire Athena ? (Code Agentique & Capacités)

Athena n'est pas un simple "ChatGPT". C'est un framework d'**agents d'intelligence artificielle autonomes** capables d'agir sur votre machine et sur le web.

### 💻 Code Agentique (Software Engineering)
C'est le cœur d'Athena. L'assistant peut remplacer un développeur humain sur certaines tâches :
- **Exécution Python & Bash (Sandbox)** : Athena peut écrire du code, créer des scripts complexes, et surtout **les exécuter de manière autonome** dans un bac à sable Docker sécurisé pour vérifier qu'ils fonctionnent.
- **Computer Use (RPA 2.0)** : L'IA peut ouvrir un vrai navigateur web en arrière-plan, cliquer sur des boutons, remplir des formulaires et lire le contenu (utile pour scraper des sites web ou faire des tests automatisés).
- **Maintenance autonome** : Un agent nocturne peut nettoyer et vérifier le code source de vos projets automatiquement.

### 🏠 Domotique & Outils Quotidiens
- **Outils natifs** : Lui demander l'heure, la météo, ou de faire une recherche Web approfondie (Recherche sémantique).
- **Domotique (Home Assistant)** : Grâce au protocole MCP, Athena connaît les objets connectés de votre maison. Demandez-lui *"Éteins la lumière du salon"* et elle transmettra l'ordre sans aucune configuration complexe.
- **Génération Média** : Si configurée avec une API externe, elle peut générer des images ou modifier des fichiers.

### 📅 Planification (Routines)
Demandez à l'IA : *"Fais-moi un résumé de ma journée et de la météo tous les matins à 7h30"*. Athena se réveillera toute seule pour exécuter la tâche et vous préparer le briefing.

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

### Onglet "Comportement" (Le Cerveau d'Athena)
C'est la section la plus importante pour ajuster les "bras" (outils) de la machine.

* **Mémoire Sémantique**
  - `Base de faits (Core Memory)` : Liste tout ce qu'Athena a appris sur vous de façon permanente (vos goûts, votre métier). Vous pouvez y supprimer des éléments.
  - `Rafraîchir les documents RAG` : Force l'IA à relire et indexer mathématiquement tous les documents de l'explorateur de fichiers.

* **Routines & Automatisations**
  - `Liste des Routines` : Affiche les tâches programmées. Vous pouvez en désactiver une ou récupérer son adresse "Webhook" (pour la déclencher depuis un logiciel comme n8n).

* **Gestion des Outils (Sécurité & Capacités)**
  - `Exécution de Code Sandbox` : **Essentiel pour le Code Agentique**. Autorise l'IA à exécuter le code qu'elle écrit dans un conteneur sécurisé.
  - `Computer Use (Navigateur)` : Autorise l'IA à utiliser le navigateur web caché.

* **Connecteurs externes (MCP)**
  - `Serveurs MCP Connectés` : Affiche si des plugins standards (ex: connecteur GitHub, Home Assistant) sont bien branchés à l'IA.

* **Observabilité & Logs (Pour les curieux)**
  - `Niveau de bavardage (Log Level)` : Réglez sur `DEBUG` si vous voulez voir dans les moindres détails techniques comment l'IA réfléchit et appelle ses outils.
  - `Redémarrer le moteur Vocal` : Bouton de secours pour relancer le serveur de génération de voix Kokoro en cas de bug.

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
