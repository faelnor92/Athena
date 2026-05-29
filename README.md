# 🎛️ Jarvis v2 - Dashboard Multi-Agent & Bureau Virtuel Immersif

Jarvis v2 est un écosystème d'orchestration multi-agent intelligent, doté d'une interface web cyberpunk-neon dépolie (glassmorphism) et d'un bureau virtuel en 3D isométrique ("Swarm Open Space").

Ce projet associe la puissance d'un moteur d'agents autonome multi-fournisseurs (OpenAI, Anthropic, Gemini, Ollama, etc.) à une interface utilisateur haut de gamme, fluide et interactive.

---

## 🌟 Fonctionnalités Majeures

### 1. 💬 Swarm Open Space (Bureau Virtuel 3D Isométrique)
*   **Visualisation Temps Réel** : Tous les agents actifs de votre essaim disposent de leur propre bureau physique modélisé en perspective isométrique.
*   **Sprites Cyber-Néon Haute Fidélité** : Des personnages vectoriels détaillés avec des attributs uniques (Jarvis le robot écran, Robert le développeur à lunettes matricielles, Émilie l'auteur avec son chevalet de peinture, Sofia la traductrice avec ses écouteurs et sa tasse de café fumante, Marc le correcteur avec son bloc-notes de relecture, et Lucas le chef couronné avec son mégaphone).
*   **Mouvements & Animations Réactives** : Les agents se déplacent de bureau en bureau pour interagir.
*   **Animations de Délégation** : Lorsqu'un agent délègue son travail à un autre agent (ex: `Jarvis` ➔ `Codeur`), une enveloppe de courrier physique vole en temps réel entre leurs deux bureaux pour matérialiser le transfert d'information.

### 2. 📊 Cockpit de Télémétrie Cyberpunk
*   **Indicateurs Live** : Jetons consommés (Tokens), estimation du coût réel en Euros, quota d'agents en cours d'utilisation, et compteurs d'états dynamiques (agents occupés vs. en pause).
*   **Galerie Médias Premium** : Visualisez instantanément les images et vidéos générées par les agents. Survol interactif avec effet de flou dépoli, bouton de téléchargement rapide, lueur néon-cyan, et badges distinctifs rose-magenta pour les vidéos.

### 3. 📁 Explorateur de Fichiers & Coloration Syntaxique
*   **Navigation Visuelle** : Parcourez et téléversez (drag & drop) des fichiers de votre espace de travail.
*   **Coloration Syntaxique Live (PrismJS)** : Lisez le code avec une coloration de syntaxe ultra-pro qui s'adapte à l'extension du fichier (`.js`, `.py`, `.html`, `.css`, `.json`, `.sh`, `.md`).
*   **Thème Tomorrow-Night** : Parfaitement intégré dans le design de panneau glassmorphic.

### 4. 📋 Liste de Tâches & Agenda Connecté
*   **Planification Interactive** : Ajoutez, suivez et supprimez des événements et réunions d'agenda.
*   **Indicateurs Temporels** : Les événements à venir sont surlignés en cyan, tandis que les tâches passées passent automatiquement en opacité réduite.

### 5. 🌿 Arbre de Conversations Branché
*   **Historique Non-Linéaire** : Naviguez dans l'historique complet des échanges sous forme de branches de décision.
*   **Multi-Branching** : Possibilité de bifurquer ("forker") la conversation à n'importe quel niveau pour tester différents scénarios d'orchestration.

---

## 🛠️ Architecture & Technologies

Le projet est conçu avec un couplage robuste entre un backend rapide en Python et un frontend moderne :

*   **Backend / API** : [FastAPI](https://fastapi.tiangolo.com/) & [Uvicorn](https://www.uvicorn.org/) pour une réactivité instantanée et une gestion asynchrone des requêtes.
*   **Moteur d'Agents (Core)** : Moteur multi-agent basé sur [LiteLLM](https://github.com/BerriAI/litellm) permettant le routage dynamique et transparent vers n'importe quel LLM du marché.
*   **Base de Données Vectorielle** : [ChromaDB](https://www.trychroma.com/) pour la mémoire sémantique à long terme (RAG), permettant aux agents de se souvenir des discussions passées.
*   **Design & Style** : CSS3 Vanilla avancé (flexbox, grid, animations keyframes, filtres CSS de flou et de lueur) pour un rendu haut de gamme sans framework lourd.

---

## 🏆 Quota & Limite des Agents : Explication Technique

Dans la barre de télémétrie supérieure, vous verrez un quota affichant par exemple `6/8` avec une icône de coupe dorée (🏆).

> [!NOTE]
> **Pas de limite technique !**
> La valeur **`8`** est une recommandation ergonomique et esthétique pour le frontend afin de garantir que les bureaux des agents restent parfaitement positionnés, lisibles et spacieux dans la vue Open Space en 3D isométrique. 
> 
> Techniquement, le backend ne possède **aucune limite stricte** d'agents. Vous pouvez configurer 10, 15 ou 20 agents dans votre fichier `agents.yaml` ou via l'API, ils seront traités et exécutés de manière totalement transparente.

---

## 🚀 Installation & Déploiement Multi-Plateforme

Des scripts d'installation automatisés de qualité professionnelle sont mis à votre disposition pour configurer et intégrer Jarvis en une seule étape selon votre système d'exploitation.

### 🐧 Linux & 🍏 macOS (Darwin)

1. Ouvrez votre terminal dans le répertoire du projet.
2. Exécutez le script d'installation unifié :
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
   *Ce script vérifie vos paquets, prépare l'environnement `.venv`, déploie le fichier de configuration `.env` et réalise l'intégration système suivante :*
   *   **Commande CLI Globale** : Installe la commande `jarvis` dans `~/.local/bin/jarvis` pour contrôler l'essaim depuis n'importe quel dossier (`jarvis start|stop|status|logs`).
   *   **Lanceurs de Bureau Natifs** : Crée un lanceur de bureau utilisable instantanément (`~/Desktop/jarvis.desktop` sous Linux, ou l'application `Jarvis.app` sur votre Bureau macOS).
   *   **Service d'Arrière-plan permanent** : Génère un agent de démarrage `launchd` sous macOS (`~/Library/LaunchAgents/fr.unistra.jarvis.plist`) pour s'exécuter en tâche de fond automatique sur votre session.
   *   **Découverte Ollama** : Détecte Ollama local et vous conseille sur les meilleurs modèles à utiliser.

### 🪟 Windows (PowerShell)

1. Ouvrez une invite PowerShell dans le répertoire du projet.
2. Exécutez le script d'installation natif Windows :
   ```powershell
   .\install.ps1
   ```
   *Ce script configure votre environnement local et configure Windows de façon optimale :*
   *   **Raccourci Bureau Windows Officiel** : Crée un raccourci `Jarvis.lnk` sur votre Bureau avec une icône système personnalisée.
   *   **Scripts utilitaires** : Génère un script de démarrage en un clic `run.bat` ainsi qu'un lanceur silencieux `launch.vbs` pour cacher la console de commande si vous le souhaitez.
   *   **Découverte Ollama** : Scanne et liste tous les modèles locaux disponibles dans votre installation Ollama Windows.

3. Renseignez votre clé API LLM dans le fichier `.env` nouvellement généré.

---

## 💻 Démarrage du Bureau Virtuel

Pour démarrer votre serveur d'orchestration Jarvis v2 et l'interface Web :

*   **Sur Linux & Mac (CLI)** :
    ```bash
    jarvis start
    ```
    *(Pour l'arrêter : `jarvis stop`, pour voir les logs : `jarvis logs`)*
*   **Sur Windows (CLI)** :
    Double-cliquez simplement sur le script `run.bat` à la racine ou sur le raccourci **Jarvis** de votre Bureau.

Connectez-vous ensuite sur votre navigateur préféré à l'adresse suivante :
👉 **[http://localhost:8000/](http://localhost:8000/)**
