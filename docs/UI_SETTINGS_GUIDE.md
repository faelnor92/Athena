# Guide des Paramètres de l'Interface (UI)

L'interface web d'Athena possède un panneau de réglages complet (l'icône ⚙️ dans le dock). Depuis la mise à jour multi-tenant (v0.9.35), ce panneau est divisé en plusieurs sections clés pour vous permettre de configurer l'IA selon vos besoins, sans jamais toucher au code.

## 1. Mon Modèle & Clés LLM
Par défaut, Athena utilise le modèle défini par l'administrateur du serveur. Cependant, chaque utilisateur peut **surcharger** cette configuration.
- Si vous préférez utiliser Claude (Anthropic) plutôt que GPT-4o, vous pouvez renseigner votre propre clé API ici.
- Seules vos requêtes seront facturées sur votre clé. Les requêtes de l'agent de nuit ou des autres utilisateurs ne seront pas affectées.

## 2. Profil & Espace de Travail
C'est ici que vous définissez les informations personnelles de base que l'IA peut utiliser (votre nom de préférence). Vous y trouverez aussi les options pour modifier votre mot de passe SSO, et la gestion de vos projets partagés.

## 3. Agenda & Todo
Permet de brancher un serveur CalDAV (Nextcloud, Synology) ou de fournir une URL iCal (Google Calendar) en lecture seule.
L'IA pourra lire votre agenda quand vous lui demandez votre emploi du temps ou lors du briefing du matin.

## 4. Satellites Vocaux (ESPHome)
Configuration des enceintes intelligentes ESP32.
- **MicroWakeWord / openWakeWord** : Choisissez le mot clé (ex: "Hey Athena") qui déclenchera l'écoute.
- L'appairage se fait automatiquement si la clé de cryptage (Noise) correspond à celle flashée sur votre ESP.

---

## 5. ⚠️ Onglet "Comportement" (Le Cerveau d'Athena)
Cet onglet est souvent le plus intimidant, mais il est crucial. Il contrôle comment l'intelligence artificielle interagit avec son environnement et ses outils.

### A. La Mémoire Sémantique (Core Memory)
L'IA sauvegarde automatiquement des faits vous concernant ("L'utilisateur est développeur", "Il n'aime pas être tutoyé").
- **Purge** : Si l'IA commence à avoir des hallucinations sur votre vie, vous pouvez vider cette mémoire ici.
- **RAG (Base Vectorielle)** : Vous pouvez forcer la réindexation de vos documents (PDF, Markdown) stockés dans l'explorateur de fichiers.

### B. Routines & Briefings
C'est ici que vous programmez l'IA pour agir d'elle-même (CRON).
- **Briefing Matinal** : Une tâche typique est `"Fais-moi un résumé de ma journée, de la météo et des alertes serveur"`, programmée à `07:30` tous les jours. L'IA s'exécutera toute seule et vous enverra un message (ou parlera si un satellite est configuré).
- **Webhooks** : Chaque routine possède une URL unique. Vous pouvez l'appeler depuis Home Assistant ou n8n pour réveiller Athena.

### C. Gestion des Outils (Tools & Sandbox)
Athena dispose de "bras" pour agir. Vous pouvez lui couper certains bras ici si vous avez peur pour votre sécurité :
- **Exécution Python / Bash** : Autorise l'IA à lancer des scripts. (Fortement recommandé d'utiliser le mode **Sandbox Docker** pour éviter qu'elle ne casse votre serveur hôte).
- **Computer Use (Navigateur)** : Autorise l'IA à ouvrir une page web cachée, cliquer sur des boutons et lire le contenu (utile pour scrapper des sites sans API).

### D. Serveurs MCP (Model Context Protocol)
Les MCP sont des extensions (plugins) standards.
- **Home Assistant** : C'est ici que vous connectez l'IA à votre domotique. Elle découvrira automatiquement vos ampoules et vos capteurs de température. Il n'est plus nécessaire d'avoir un outil météo compliqué pour les pièces de votre maison ; Athena interrogera Home Assistant directement.

### E. Moteurs Vocaux (TTS / STT)
Si vous hébergez Athena vous-même :
- **Kokoro TTS** : Vous trouverez ici un bouton **"Redémarrer le Moteur Vocal"** (très utile si la synthèse vocale locale plante ou bloque la mémoire vive).
- Ce bouton interagit directement avec Docker pour relancer le conteneur `kokoro-fastapi-cpu` sans couper l'orchestrateur.

### F. Observabilité & Logs
Le panneau des logs permet de voir exactement ce que l'IA fait en arrière-plan.
- Vous pouvez changer le niveau de bavardage (`INFO` vers `DEBUG`) à chaud si une routine échoue et que vous souhaitez enquêter.
