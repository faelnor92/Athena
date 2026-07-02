# 🔐 Audit de sécurité — Athena (2026-06-22)

Audit complet : scans automatiques (bandit, pip-audit, secrets) + revue manuelle des surfaces
critiques (auth/authz, exécution code/shell/SSH, SSRF, path traversal, injection SQL, XXE, SSE,
secrets) et du code récent (LSP, event bus, design tokens, streaming AthenaDesign, import-code).

## 🔴 Critique — ~~à traiter par l'opérateur~~ **corrigé dans le code (2026-07-02)**
- **`SENSITIVE_TOOLS=""` dans `.env` désactivait TOUTE confirmation HITL.** Avec cet override vide,
  `approvals.sensitive_tool_names()` était vide → `execute_bash_command`, `run_ssh_command`,
  `write_file`/`edit_file`/`apply_patch`, etc. s'exécutaient **sans validation** (même si
  `AUTO_APPROVE_SENSITIVE=false`). Risque réel en cas d'injection de prompt (mail/web/MCP).
  **Correctif (code)** : `SENSITIVE_TOOLS` vide ou absent = **liste par défaut** (sûre) ; la
  désactivation totale se demande désormais **explicitement** avec `SENSITIVE_TOOLS=none`
  (déconseillé hors instance 100 % locale de confiance). Test :
  `tests/test_approvals.py::test_sensitive_tools_vide_ne_desactive_pas_le_hitl`.

## 🟠 Corrigé (code) — durcissements
| Faille | Lieu | Correctif |
|---|---|---|
| **XXE / expansion d'entités** sur les réponses WebDAV/CalDAV/CardDAV | `tools/nextcloud_tools.py` | parsing via **defusedxml** (repli stdlib si absent) |
| **`requests` sans timeout** (blocage de thread / DoS) | `tools/home_assistant.py` ×2 | `timeout=HA_HTTP_TIMEOUT` (défaut 15 s) |
| **Injection SQL par nom de colonne** (latente : `key` interpolé) | `core/state.py` `_update_conv` | **allowlist** stricte des colonnes (valeurs déjà paramétrées) |
| **Couverture HITL incomplète** | `core/approvals.py` | ajout de `run_tool_script`, `self_update`, `nextcloud_write_file/delete_file` aux outils sensibles par défaut |
| **2× SHA1 « pour sécurité »** (B324) | `core/events.py`, `routers/redaction.py` | `usedforsecurity=False` (usage non cryptographique : dédup/cache) — *corrigé v0.27.0* |

## 🟢 Revu — faux positifs (documentés, `# nosec`)
- **`exec`** (`tools/tool_script.py`) : sandboxé — **validation AST** (imports/appels allowlistés,
  `eval`/`exec`/`open` interdits) + **builtins restreints** + budget d'instructions + timeout.
- **paramiko `exec_command`** (`tools/system_tools.py`) : outil `run_ssh_command` **sensible/HITL**,
  gardes blacklist/sudo/lecture-seule (testées), `remote_cwd` via `shlex.quote`.
- **`--tmpfs /tmp` ×2** (`tools/sandbox_runner.py`) : argument **Docker** (tmpfs en conteneur),
  pas un chemin hôte. Sandbox : `--cap-drop ALL`, `--no-new-privileges`, read-only, limites.
- **`urlopen`** (`routers/system.py`, `tools/maintenance.py`) : URL **constantes** (GitHub VERSION,
  Ollama localhost), non contrôlées par l'utilisateur.
- **bind `0.0.0.0`** (B104) : défaut `HOST` — **choix de déploiement** (cf. `docs/DEPLOYMENT.md`) ;
  ici `HOST=127.0.0.1`.

## ✅ Vérifié sain
- **Autorisation** des endpoints récents (`/chat/stream`, `import-code`, `design-system/auto`,
  `/api/todos`, `/api/plan-mode`, `/api/workspace/lint`) : sous `auth_middleware` + `_can_access`
  (404 si projet non accessible) / scope par utilisateur. Pas d'accès inter-comptes.
- **Path traversal** : `code_edit._resolve`, `workspace._safe_workspace_path`,
  `nextcloud._safe_path`, `athenadesign._safe_join`, `design_tokens` (walk borné au workspace).
- **SSRF** : `tools/net_guard` (IP privées + 169.254.169.254 bloquées) sur web_scrape /
  `_fetch_web_styles` / Nextcloud ; `design_tokens` ne lit que des fichiers locaux ; le LSP
  (`basedpyright`) est lancé par `shutil.which` + args fixes (pas d'entrée utilisateur).
- **Secrets** : aucun secret littéral versionné ; `.env` non suivi par git ; logs via
  `redact_secrets` (audit).
- **CI** : `pytest tests/` hermétique + `security_scan.sh` **bloquant** (bandit HIGH/HIGH,
  secrets, `.env` suivi) — pip-audit/bandit-complet informatifs.

## Résiduel / recommandations
- Appliquer la **checklist** `docs/DEPLOYMENT.md` avant toute exposition (HTTPS/reverse-proxy,
  CORS, MFA admin).
- `tool_script`/`exec` reste **in-process** : sûr pour le modèle de menace (AST+builtins), mais
  pour du code non-fiable préférer le sandbox Docker (`execute_python_code`).
- Surveiller les **CVE de dépendances** (pip-audit, informatif) et mettre à jour régulièrement.
