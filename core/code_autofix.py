"""Code-Test-Fix : après un run de l'agent Codeur, lance les vérifications du projet ; en cas
d'échec, on renvoie les erreurs au codeur pour qu'il corrige, puis on revérifie (boucle bornée).

Équivalent « code » de l'auto-correction d'AthenaDesign. La boucle elle-même vit dans le flux
console (routers/chat.py) ; ce module fournit les briques TESTABLES : détection de la commande
de vérification, lecture du verdict, et garde-fous (activation, budget).

Variables :
  CODER_AUTOFIX       "true" (défaut) | "false"
  CODER_AUTOFIX_MAX   nb max de corrections (défaut 2)
  CODER_CHECK_CMD     commande de vérif forcée (sinon auto-détection)
"""
import os
import json


def enabled() -> bool:
    return os.getenv("CODER_AUTOFIX", "true").lower() in ("true", "1", "yes")


def max_attempts() -> int:
    try:
        return max(0, int(os.getenv("CODER_AUTOFIX_MAX", "2") or 2))
    except ValueError:
        return 2


def checks_passed(output: str) -> bool:
    """Vrai si le verdict de run_checks est PASS (run_checks préfixe '✅ PASS' / '❌ FAIL')."""
    return (output or "").lstrip().startswith("✅ PASS")


def detect_check_command(cwd: str) -> str:
    """Commande de vérification du projet. CODER_CHECK_CMD prime ; sinon auto-détection :
    npm test (si package.json a un script test), pytest (si projet Python/tests), sinon ''
    (→ pas d'auto-fix, on ne devine pas)."""
    forced = os.getenv("CODER_CHECK_CMD", "").strip()
    if forced:
        return forced
    if not cwd or not os.path.isdir(cwd):
        return ""
    pj = os.path.join(cwd, "package.json")
    if os.path.isfile(pj):
        try:
            with open(pj, "r", encoding="utf-8") as f:
                if ((json.load(f).get("scripts") or {}).get("test")):
                    return "npm test --silent"
        except Exception:
            pass
    for marker in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "tests", "test"):
        if os.path.exists(os.path.join(cwd, marker)):
            return "pytest -q"
    # Fichiers de test à la racine (test_*.py / *_test.py) sans dossier tests/ dédié.
    try:
        import glob as _glob
        if (_glob.glob(os.path.join(cwd, "test_*.py")) or _glob.glob(os.path.join(cwd, "*_test.py"))):
            return "pytest -q"
    except Exception:
        pass
    return ""
