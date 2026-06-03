# 📖 Guide Utilisateur d'Athena

Bienvenue ! Si vous lisez ce guide, c'est que vous venez d'installer **Athena**, votre chef d'orchestre d'Intelligence Artificielle multi-agents. Ce document est pensé pour vous aider à prendre en main l'outil, même si vous n'êtes pas un expert technique.

---

## 1. 🌟 Premier Lancement et Connexion

Une fois Athena installé et démarré sur votre machine, l'interface n'est accessible que via votre navigateur web.

1. Ouvrez votre navigateur et allez sur l'adresse : **`http://localhost:8000`** (ou l'adresse IP de votre serveur si vous l'avez installé sur une autre machine).
2. S'il s'agit du tout premier lancement, on vous demandera de créer un compte avec une adresse email et un mot de passe.
3. Une fois connecté, vous arrivez sur le **Bureau**.

---

## 2. 💬 Discuter avec l'IA (L'Interface Web)

### A. Le Bureau Visuel (Vue 3D)
Sur la page principale, vous verrez une représentation visuelle d'Athena et de ses "Agents" (les différents corps de métier de l'IA : Le Codeur, Le Chercheur, etc.). 
Lorsqu'Athena réfléchit ou délègue une tâche, vous verrez des animations lumineuses vous indiquant quel agent est actuellement en train de travailler.

### B. Envoyer un message
En bas de l'écran se trouve la barre de saisie. Écrivez votre requête et validez. 
> [!TIP]
> **Le menu déroulant des agents** : Par défaut, vos messages sont envoyés à l'"Orchestrateur" (le chef) qui décide à qui confier le travail. Si vous souhaitez parler directement à un agent précis sans passer par le chef, utilisez le petit menu déroulant à côté de la barre de texte pour le forcer.

### C. L'Explorateur de Fichiers (Workspaces)
Sur la gauche se trouve un panneau contenant vos fichiers. 
- Vous pouvez y glisser-déposer des documents (PDF, Markdown, code).
- **Projets Partagés** : Si vous êtes plusieurs sur le même serveur Athena, vous pouvez créer un dossier et décider de le partager (en lecture seule ou en modification) avec d'autres utilisateurs via le bouton de partage.

---

## 3. 🛠️ Que peut faire Athena ?

Athena possède de nombreux "outils" (skills) lui permettant d'agir sur le monde réel.
- **S'informer** : Vous pouvez lui demander la météo d'une ville, la date et l'heure, ou lui demander de faire une recherche sur le Web.
- **Domotique (Home Assistant)** : Si configuré, Athena connaît les objets connectés de votre maison. Demandez-lui *"Éteins la lumière du salon"* ou *"Fait-il froid dans le bureau ?"*.
- **Planification (Routines)** : Demandez à l'IA : *"Fais-moi un résumé de ma journée tous les matins à 7h30"*. Athena se réveillera toute seule à cette heure pour exécuter la tâche.
- **Créativité** : Demandez-lui de *"Générer une image"* (si l'administrateur a configuré une clé API d'image).

---

## 4. ⚙️ Comprendre les Paramètres de l'Interface

En cliquant sur l'icône d'engrenage (⚙️) dans la barre latérale, vous accédez aux réglages de votre profil. **Chaque paramètre est isolé pour votre utilisateur.**

### Onglet "Profil & Espace de Travail"
- **Prénom & Email** : Les informations de base. C'est ici que l'IA va chercher comment vous appeler.
- **Changement de mot de passe** : Permet de sécuriser votre accès.

### Onglet "Mon Modèle & Clés LLM"
Athena fonctionne avec un modèle par défaut configuré par l'administrateur. Mais vous pouvez utiliser le vôtre !
- **Fournisseur IA (Ex: OpenAI, Anthropic)** : Choisissez la marque de l'IA.
- **Nom du Modèle (Ex: gpt-4o, claude-3-5-sonnet)** : Précisez la version que vous souhaitez.
- **Clé API Personnelle** : Collez votre clé secrète ici. *Si ce champ est rempli, Athena utilisera VOTRE clé pour générer du texte, et vous serez facturé sur votre propre compte développeur au lieu de celui du serveur.*

### Onglet "Agenda & Todo"
- **Agenda Principal (URL)** : Collez l'adresse d'un flux iCal (Google Calendar, etc.). L'IA pourra alors lire votre planning si vous lui demandez votre programme de la journée.
- **Serveur CalDAV (URL, Utilisateur, Mot de passe)** : Si vous utilisez un agenda avancé (Nextcloud, Synology), l'IA pourra non seulement lire, mais aussi *créer* des événements.

### Onglet "Comportement" (Le Cerveau d'Athena)
C'est la section la plus importante pour ajuster les réactions de la machine.

* **Mémoire Sémantique (Ce qu'elle retient)**
  - `Base de faits (Core Memory)` : Liste tout ce qu'Athena a appris sur vous de façon permanente (vos goûts, votre métier). Vous pouvez y supprimer des éléments si elle se trompe.
  - `Rafraîchir les documents RAG` : Force l'IA à relire tous les documents que vous avez mis dans l'explorateur de fichiers pour les garder en mémoire.

* **Routines & Automatisations**
  - `Liste des Routines` : Affiche les tâches programmées (ex: le briefing du matin). Vous pouvez activer/désactiver une routine ou récupérer son adresse "Webhook" (pour la déclencher depuis un logiciel externe).

* **Gestion des Outils (Sécurité)**
  - `Exécution de Code Sandbox` : Autorise l'IA à écrire et exécuter des scripts de programmation complexes dans un espace sécurisé. Fortement recommandé de le laisser coché.
  - `Computer Use (Navigateur)` : Autorise l'IA à ouvrir un navigateur virtuel invisible pour aller lire et interagir avec des sites web complexes.

* **Connecteurs externes (MCP)**
  - `Serveurs MCP Connectés` : Affiche les extensions externes (comme Home Assistant). C'est ce qui indique si votre domotique est bien branchée à l'IA.

* **Observabilité & Logs (Pour les utilisateurs avancés)**
  - `Niveau de bavardage (Log Level)` : Réglez sur `INFO` pour un fonctionnement normal, ou `DEBUG` si vous voulez voir les moindres détails techniques de ce que l'IA fait (utile en cas de panne).
  - Bouton `Redémarrer le moteur Vocal` : Relance le système qui génère la voix (Kokoro) si celui-ci se bloque.

---

## 5. 💻 Gérer le Serveur (Commandes CLI)

En plus de la page Web, vous disposez d'un "CLI" (une commande tapée dans le terminal) pour gérer le logiciel Athena lui-même en arrière-plan.
Ouvrez votre Terminal (Linux/macOS) ou PowerShell (Windows) et tapez ces commandes n'importe où.

### 🍎 Linux & macOS
La commande principale s'appelle `athena`.
- `athena start` : Allume l'IA en arrière-plan. (Vous pouvez fermer le terminal, elle continuera de tourner).
- `athena stop` : Éteint le serveur proprement.
- `athena restart` : Redémarre l'application.
- `athena status` : Vérifie si Athena est actuellement en cours d'exécution.
- `athena logs` : Affiche en direct le journal technique (les bugs, les connexions). Faites `Ctrl+C` pour quitter.

**Mettre à jour le logiciel :**
Pour recevoir les dernières nouveautés, allez dans le dossier d'installation (ex: `cd ~/athena`) et lancez :
`./update.sh`

### 🪟 Windows (PowerShell)
Sur Windows, la commande se termine par `.ps1`.
- `athena.ps1 start` : Démarre le serveur.
- `athena.ps1 stop` : Coupe le serveur.
- `athena.ps1 restart` : Redémarre le processus.
- `athena.ps1 status` : Affiche l'état.
- `athena.ps1 logs` : Affiche la console technique.

**Mettre à jour le logiciel :**
Ouvrez PowerShell dans le dossier d'installation (ex: `cd C:\Utilisateurs\Nom\athena`) et lancez :
`.\update.ps1`
