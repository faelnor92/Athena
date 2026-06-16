# 🦉 Athena — Inventaire complet des fonctionnalités

> Assistant multi-agents auto-hébergé, orienté « Jarvis ». Document généré le 2026-06-16.

---

## 1. Cœur : orchestration multi-agents (Swarm)
- Orchestrateur **Athena** + agents spécialisés qui se **délèguent** le travail
  (`transfer_to_`, `delegate_to_`, `query_agent`, `debate_between_agents`).
- **Routage sémantique** (qui répond / à qui déléguer).
- **Filtrage d'outils par pertinence** (économie de tokens).
- **Exécution d'outils en parallèle**.
- Garde-fous d'exécution : disjoncteur anti-répétition, compaction mémoire en cours de run,
  budget temps / tokens, annulation (barge-in / stop), steering (consignes en cours de run).
- **Auto-continuation** (agir sans attendre « vas-y »).
- **Auto-correction du tool-calling** (JSON cassé / appel en texte → relance automatique).
- Agents par défaut : **Auteur (Émilie)**, **Codeur (Robert)**, **Traducteur (Sofia)**,
  **Correcteur (Marc)**, **CommunityManager (Lucas)**, **Juriste**.
- Création d'agents à la volée (`create_agent`).

## 2. Auto-amélioration
- **Skills auto-créées** : Athena écrit ses propres outils Python validés
  (`save_new_skill`, validation AST sécurisée) ; induction automatique de compétences.
- **Rapports d'expérience** archivés en mémoire (RAG).
- **Auto-critique** des réponses.
- **Modélisation de l'utilisateur** (profil évolutif).
- Réparation automatique des skills défaillantes.

## 3. Mémoire
- **RAG vectoriel** (ChromaDB) : `memorize_fact`, `store_document`, `search_memory`, `ingest_file`.
- Embeddings **configurables** (local par défaut, ou HTTP bge-m3 / qwen3).
- **Mémoire-graphe / Chronos** : faits durables (sujet-relation-objet) extraits
  automatiquement en fin de run et réinjectés en début de run
  (`remember_relation`, `query_graph`).
- **Profil utilisateur** durable.
- Gestion des **conversations** (`manage_conversations`).
- Tout est **par compte utilisateur**.

## 4. Voix & satellites
- **STT** (Whisper).
- **TTS** (Kokoro ; recettes serveur XTTS / Fish-Speech disponibles).
- **Wake-word** (« Athena »).
- **Barge-in** (interruption à la voix pendant qu'Athena parle).
- **Streaming token → voix** (latence minimale).
- **Reconnaissance du locuteur** (empreinte vocale) → routage vers le bon compte (`as_user`).
- Satellites ESP (capteurs → Home Assistant, voix → Athena).

## 5. Vision & images
- **Analyse d'images** via l'endpoint (base64) : `analyze_image`, `analyze_document` (OCR / scan).
- **Capture d'écran** + **computer use** (actions à l'écran, optionnel).
- **Génération** d'images et de vidéos artistiques
  (`generate_image`, `generate_artistic_image`, `generate_artistic_video`).

## 6. Communication / canaux
- **Chat web** (streaming SSE, multiligne, mentions @agent).
- **Telegram** (bot entrant, pairing/approbation, liaison chat → compte Athena).
- **Notifications** (`send_notification`).

## 7. Agenda
- iCal / **CalDAV** / Google Calendar.
- Lecture + écriture : `add_calendar_event`, `list_calendar_events`, `delete_calendar_event`.
- Fuseau horaire, cible d'écriture, synchronisation.
- **Par compte utilisateur**.

## 8. Mail
- IMAP : `read_inbox`, `read_email`, `search_emails` (+ catégories Gmail).
- **Ménage** : `clean_inbox`, `mark_emails_read`, `archive_emails` (vers un dossier dédié),
  `list_mail_folders`.
- **Brouillons** : `create_email_draft` (zéro envoi automatique).
- Anti-injection de prompt.

## 9. Listes & tâches
- Listes (courses, tâches, idées) par compte :
  `add_list_item`, `get_list_items`, `toggle_list_item`, `delete_list_item`.
- **Synchronisation bidirectionnelle avec Nextcloud Notes** (optionnelle, source de vérité).

## 10. Domotique
- **Home Assistant** : `get_ha_state`, `call_ha_service`.
- **Présence / follow-me** : `get_current_room`.
- Météo (`get_weather`), heure (`get_time`), **briefing quotidien** (`get_daily_briefing`).
- **Monitoring d'infrastructure** : la télémétrie des serveurs/baie (température, hyperviseurs)
  remonte via Home Assistant / capteurs ESP, et peut être interrogée par Athena. Une alerte
  critique peut déclencher une notification (et, à terme, un correctif proposé en sandbox).

## 11. Code & développement
- **Sandbox Docker persistante** : `execute_bash_command`, `execute_python_code`, `run_tool_script`.
- Édition : `edit_file`, `apply_patch`, `write_file`, `read_file`.
- Navigation de code : `find_definition`, `find_references`, `search_code`, `file_outline`, repo map.
- **Git** complet : `git_commit`, `git_create_branch`, **worktrees** (`git_create/list/remove_worktree`),
  `git_diff`, `git_log`, `git_status`.
- **Auto-fix** de code, tests (`run_checks`).
- **Claude Code** intégré (`claude_code`).
- **`reset_sandbox`** : réinitialise l'environnement d'exécution (conteneur cassé/saturé),
  workspace conservé.
- **Virtualisation / hyperviseurs** : aujourd'hui via **SSH** (commandes sur l'hôte : `virsh`,
  `docker`, `pct/qm` Proxmox…). Un **MCP d'environnement** dédié (Proxmox/VM en natif) est prévu
  dans la roadmap pour lire/agir sur l'état des VM sans passer par des commandes brutes.

## 12. Rédaction (romans) — onglet Écriture
- Révision / traduction / cohérence / répétitions de chapitres :
  `document_revise`, `document_translate`, `document_check_coherence`,
  `document_check_repetitions`, `document_autorevise`, `document_read`, `document_publish`.
- **Modèle LLM configurable** pour la rédaction.
- Intégration **OnlyOffice** (édition en ligne).
- **Cohérence de l'univers (lore) via le graphe de connaissances** : fiches personnages,
  règles de l'univers et relations stockées dans la mémoire-graphe (Chronos) → Émilie (l'agent
  auteur) vérifie qu'un élément (mythologie, cyberpunk…) reste cohérent d'un chapitre à l'autre.

## 13. AthenaDesign — onglet Design
- Génération de sites / projets web (iframe dédiée).
- Renommage de projets, partage en lecture seule par jeton.

## 14. Web
- `web_search`, `web_scrape`.
- Navigateur **Playwright** (`render_page`).

## 15. Proactivité & automatisation
- **Routines** planifiées créées et gérées par l'agent (`create_routine`, `list_routines`) :
  daily / weekly / interval / webhook ; livraison notification + Telegram.
- **Pipelines** rigides : `run_rigid_pipeline`, `make_plan`, `get_plan`, `update_plan_step`.
- **Playbooks** : `load_playbook`.
- **Workflows n8n** : `trigger_workflow`.

## 16. MCP (Model Context Protocol)
- **Marketplace** : recherche dans le registre MCP officiel.
- Serveurs MCP personnels.
- Home Assistant en STDIO géré par Athena (sans Docker).

## 17. SSH / serveurs
- Hôtes SSH gérés (`list_ssh_hosts`), exécution distante.
- Partage d'hôte par utilisateur (TOFU sur le LAN).

## 18. Réunions
- `transcribe_and_summarize_meeting` (transcription + résumé + diarisation) — onglet Meeting.

## 19. Sécurité & multi-utilisateur
- **Authentification** (sessions), **MFA / TOTP**, **SSO OIDC**.
- **RBAC** (rôles admin / user, outils réservés admin).
- **Approbations HITL** (Human-in-the-loop) pour les outils sensibles.
- **Anti-SSRF** (net_guard, allowlist d'hôtes internes).
- **Audit**, **tool_policy**.
- **Invitations**, **quotas de tokens** par utilisateur.
- Données et configuration **par compte**.

## 20. Pilotage & maintenance
- **Cockpit** : télémétrie, coûts par modèle, observabilité.
- **Tarification LLM** configurable.
- **Backup / restore** (archive .zip).
- **Diagnostics / doctor**.
- **Plugins**.
- **Évaluations** (eval), **logs**.

## 21. Interface (onglets)
Orchestrateur · Cockpit · Mémoire (+ vue graphe) · Agenda · Fichiers · Console ·
**Design** · **Rédaction** · **Office (OnlyOffice)** · **Meeting** · Branches (git) ·
**MCP** (marketplace + perso).
UI responsive (mobile / tablette). Réglages repensés (cartes + descriptions + recherche).

---

## Roadmap « Jarvis » — ce qui est prévu

### ✅ Déjà fait (base Jarvis posée)
- **Chronos** : mémoire relationnelle automatique (extraction de faits durables + réinjection
  du contexte-graphe pertinent au début d'un run).
- **Voix temps réel** : streaming token → voix, wake-word, barge-in, reconnaissance du
  locuteur → routage vers le bon compte.
- **Proactivité de base** : routines planifiées créables et gérables par l'agent.
- **Fiabilité du tool-calling** : réparation du JSON malformé / appels en texte + auto-correction.
- **Identité par compte unifiée** (web / Telegram / voix → agenda, listes, mémoire du bon membre).
- **Context Stacker (« fil d'Ariane »)** : mettre une tâche de côté (PUSH) / reprendre (POP),
  avec `docker pause`/`unpause` de la sandbox. Outils `open_context` / `close_context` / `list_contexts`.
- **Conscience situationnelle** (parenthèses ouvertes + pièce courante injectées au run).
- **HITL multi-canal asynchrone** : action sensible via Telegram → run figé + notification
  actionnable (boutons ✅/⛔) + déverrouillage par un clic. Timeout = refus.

### 🔜 Prévu (prochaines briques)
1. **Proactivité événementielle (Event broker)**
   - Entrée d'événements externes (Zabbix / LibreNMS / Home Assistant) via webhook + file asyncio.
   - Un **agent Vigie** intercepte (`disk_almost_full`, `high_temperature_rack`…), synthétise,
     et décide d'alerter ou de préparer un correctif en sandbox **avant** qu'on demande quoi que ce soit.

2. **MCP d'environnement**
   - Serveurs MCP branchés sur Proxmox, le terminal, l'éditeur.
   - Injection d'un **« contexte système invisible »** au début d'une discussion
     (dernières lignes de logs en erreur, charge du cluster) → ne plus avoir à expliquer le problème.

3. **Goal manager (objectifs persistants)**
   - Store d'objectifs (actif / en pause / abandonné) décomposables, relus par une routine.
   - Exécution **déclenchée + validée (HITL)**, jamais d'autonomie non bornée.

### 💡 Idées « effet Jarvis » à creuser
- **Briefing matinal CONTEXTUEL** (pas juste lu à heure fixe) : déclenché quand le capteur de
  présence du bureau/chambre s'active le matin (Home Assistant) **et** s'il n'y a pas d'alerte
  infra critique → Athena lance le briefing (agenda du jour + météo + état infra) de façon fluide
  dès que tu entres. Lie Agenda (§7) + Domotique (§10) + Routines.
- **Scènes domotiques** (« soirée film » → lumières, etc. via Home Assistant).
- **Vision temps réel** (caméra / sonnette : « qui est à la porte ? »).
- **Anticipation par habitudes** (croisement graphe de connaissances + routines).
- **Fiabilité tool-calling avancée** : JSON mode / grammaire GBNF (selon l'endpoint),
  early-terminate en streaming (couper la génération dès qu'on détecte un bla-bla au lieu d'un appel).
- **Voix plus expressive** (TTS émotionnel : XTTS / Fish-Speech).
