# Athena — Notes de développement (mémoire projet)

> Fichier de référence **persistant** : vision, règles dures, particularités d'archi, bugs
> connus et plan de refonte. À tenir à jour à chaque décision importante.

## 🎯 Vision
Framework multi-agent auto-hébergé, **niveau pro**, utilisable par les **foyers ET les
entreprises**. Objectif : qualité comparable aux meilleurs (Claude Code, OpenClaw…) côté
code, tout en restant **user-friendly** (tout dans l'UI, install simple).

## ⛔ Règles dures (obligations)
- **Secrets** : ne JAMAIS committer `.env`, clés, tokens. `.env` + données par-user gitignorés.
- **Git** : commits locaux ; l'utilisateur pousse lui-même (ou demande explicitement). Auteur = faelnor92@gmail.com. Co-Authored-By: Claude.
- **Config locale** : `agents.yaml`, `routines.json`, etc. sont **gitignorés** (config/état runtime). Les correctifs de config doivent aller dans `agents.default.yaml` / `agents.example.yaml` (suivis) pour les nouvelles installs.
- **Prompts d'agents** : le `system_prompt` d'un agent = sa **personnalité**, ÉDITABLE par l'utilisateur. Les **règles système** (honnêteté outils, chemins relatifs, etc.) NE doivent PAS y être écrites en dur : elles vivent dans le **préambule système** injecté par `core/swarm.py` (adapté aux outils de l'agent).
- **Agents dynamiques** : SEUL l'**orchestrateur** (Athena) est fixe. Tous les autres peuvent être créés / supprimés / recréés avec d'autres métiers/prompts → ne jamais coder en supposant qu'un agent précis (« Codeur », etc.) existe.
- **Outils** : les outils cochés sont exposés au modèle via leur **schéma** (docstring) — ne pas redécrire les outils dans les prompts.
- **Tests** : `for t in tests/test_*.py; do python3 "$t"` + `tests/test_api_smoke.py` (baseline des routes). Régénérer la baseline après ajout intentionnel de routes.

## 🧩 Particularités d'architecture
- **Multi-tenant** : tout est par-utilisateur (mémoire, RAG `um_<user>`, agenda, listes, quotas, config). Bucket `local` en mode sans auth.
- **État partagé multi-worker** : `core/shared_store.py` (SQLite WAL, atomique) pour comptes/quotas/sessions/routines/invites/projets/config — cohérent en `uvicorn --workers N`.
- **Projets** : un projet = un dossier. Projet actif (par-user) → `get_workspace_dir()` → scope des outils code + explorateur. Override de contexte (`projects.set_override`) pour que la **console** cible un projet différent du chat/voix.
- **Sandbox** : `tools/sandbox_runner.py` (Docker, image `python:3.11-slim`, réseau coupé, `-v projet:/work`). `tool_script` = exec Python en-process sandboxé par AST. Garde `can_write()` (viewer = lecture seule) sur tous les outils d'écriture.
- **Sécurité** : auth Bearer + middleware authz centralisé, throttle login partagé, 2FA TOTP, chiffrement au repos (Fernet) conv+traces, SSRF `net_guard` (web + iCal/CalDAV), en-têtes CSP, rate-limit, audit (`/api/audit`), validation admin des automatisations.

## 🐛 Bugs / limites connus (remontés à l'usage — 2026-06-04)
1. **Code médiocre** : `model: coder-qwen` (petit modèle local) → hallucine, boucle, ignore les outils. **Le modèle est LE facteur #1** ; viser un modèle frontier pour le code.
2. **Boucle inefficace** : atteint `max_turns` sans converger (narration, re-lectures). Besoin d'une vraie boucle agentique plan→act→observe→iterate.
3. **Orchestrateur fait du code** même si l'agent code est restreint (routage qui fuit).
4. **Sandbox trop fermée** : pas de réseau (pip/npm échouent en DNS), pas de `git` dans l'image.
5. **Fuite de workspace** : les projets vivent SOUS le workspace de base (`projects/local/<id>/`) → l'explorateur du workspace de base montre TOUS les projets. À isoler.
6. **Images non affichées** dans l'explorateur de projet (vue Fichiers).
7. **SSH** : un seul host (config admin) ; pas de `net_guard` ni filtre de commande dessus ; pas de garde `can_write`. À cadrer.
8. **Hallucination d'outil** : l'agent prétend avoir lancé git / lu un dossier sans le faire (atténué par le préambule système « ne jamais inventer un résultat d'outil » + auto-approve console).

## 🚧 Refonte « partie code » (en cours de décision)
Direction pressentie (à valider) :
- **Sous-système de code séparé du swarm conversationnel** : un agent de code dédié (indépendant des agents dynamiques) avec une **boucle agentique** propre (lire/écrire/éditer/exécuter/tester/itérer), sur un **modèle fort**.
- **Console + explorateur + IDE FUSIONNÉS** en un seul espace de code.
- **Chat principal** = workspaces généraux (notes/docs) ; **code** = projets distincts (dépôts git), stockés HORS du workspace de base (plus de fuite).
- **Sandbox dev** : image avec git + toolchains + réseau contrôlé pour les installs.
- S'inspirer des projets open-source éprouvés (Aider, OpenHands…) pour la boucle.

### Étude open-source (2026-06-04) — patterns retenus
- **Aider** : édition par **blocs search/replace** (le modèle ne renvoie QUE les sections changées) — fiable/efficace vs réécriture complète ; **format d'édition adapté au modèle** (faible → whole, fort → diff) ; **mode architect** (1 modèle raisonne le changement, 1 applique) ; **repo-map** (tree-sitter + ranking de dépendances dans un budget de tokens) pour donner le contexte codebase sans tout lire.
- **OpenHands** : boucle **Action/Observation** via EventStream → Runtime (Docker/local/remote : bash/python/browser) → arrêt sur **finish action** ou max itérations ; **condensation d'historique** ; séparation nette **planification ↔ exécution sandboxée**.
- **OpenClaw** : **Gateway** control plane ; **sandbox + allowlist d'outils PAR SESSION** (session principale = hôte ; canaux = Docker/SSH restreint).
- **Hermes** (NousResearch — Athena s'en inspire déjà) : boucle jusqu'à **max_iterations = 90** + budget ; **toolsets** activables par plateforme ; **skills** = docs Markdown (agentskills.io) + **Curator** qui archive les obsolètes ; backends d'exécution local/Docker/SSH/Modal/Daytona ; **smart_model_routing** (modèle choisi par capacité : reasoning/coding/vision + fallback) ; `read_file/patch/write_file` workspace-aware ; **delegate_task** = sous-agents isolés ; prompt caching.

### Architecture proposée — sous-système Code Athena (v1, à valider)
1. **Agent code dédié + boucle serrée** (hors swarm conversationnel) : plan → agir → **observer la vraie sortie** → itérer ; budget élevé (≈60–90 itérations, pas 30) ; fin sur action « terminé » ou budget. Indépendant des agents dynamiques.
2. **Modèle FORT pour le code** via routing par capacité « coding » (défaut = meilleur modèle configuré ; local en repli). ← levier #1 de qualité.
3. **Édition fiable** : outil **search/replace** (style Aider) en mécanisme principal + `write_file` pour les nouveaux fichiers ; format adapté à la force du modèle.
4. **Repo-map** tree-sitter (réutiliser `code_nav`: file_outline/find_definition + ranking) injecté comme contexte (budget tokens).
5. **Sandbox dev réelle** : image avec git + python + node + build ; **réseau contrôlé** pour les installs.
6. **Projets HORS workspace de base** (fin de la fuite) ; chat = workspaces généraux, code = projets.
7. **UI fusionnée** explorateur + IDE = un espace « Code » (arbre auto-refresh + éditeur), alimenté par la boucle.
8. (Option Aider) **architect/editor split** : modèle fort planifie le diff, applicateur déterministe/léger applique — utile si le modèle d'édition est faible.

Sources étudiées : aider.chat/docs, github.com/All-Hands-AI/OpenHands, github.com/openclaw/openclaw, github.com/NousResearch/hermes-agent.

### Décisions (2026-06-04)
- **Modèle de code = choisi par l'UTILISATEUR** (configurable par-agent/par-user, défaut = meilleur dispo). On NE force pas un modèle ; on rend le plomberie impeccable pour qu'il branche le sien.
- **Inspiration ciblée** : **OpenClaw pour le code** (réputé pour ça : allowlist d'outils + sandbox par session, gateway), **Hermes pour la mémoire + les agents** (déjà reproduit par Athena : skills, routing, delegate).
- On garde le **swarm conversationnel** (Hermes-like) ET on ajoute un **sous-système Code dédié** (OpenClaw-like) séparé.

### Plan de build incrémental (le sous-système code)
Ordre proposé (chaque étape = valeur + testable) :
1. **Quick wins / bugs** : budget de tours ↑ (≈90, configurable) ; **projets hors workspace de base** (fin de la fuite) ; **images affichées** dans l'explorateur ; **sandbox dev** (git + réseau contrôlé pour pip/npm).
2. **Édition fiable** : outil **search/replace** (Aider-like) + format selon le modèle.
3. **Repo-map** (contexte codebase) via code_nav.
4. **Boucle de code dédiée** (plan→agir→observer→itérer, finish/budget) — séparée du swarm.
5. **UI** : fusion explorateur + IDE (espace « Code »).
6. **Sécurité code** : allowlist d'outils par session (OpenClaw), garde-fous SSH.
