"""Outils de développement : exécution de tests / linters / build avec une sortie
CENTRÉE SUR LES ERREURS, pour alimenter une boucle autonome Code-Test-Fix.

run_checks lance une commande (pytest, npm test, ruff, tsc…) dans le workspace, via
la sandbox Docker si disponible (sinon repli hôte), et renvoie un résumé compact :
verdict PASS/FAIL + extrait priorisant les lignes d'erreur (Traceback, FAILED, Error…),
plutôt que des centaines de lignes de bruit. L'agent peut alors corriger puis relancer.
"""
import os

_ERR_HINTS = ("error", "erreur", "failed", "fail", "traceback", "exception",
              "assert", "✗", "✖", "panic", "cannot find", "undefined", "not found",
              "syntaxerror", "typeerror", "warning")

_MAX_OUT = 6000


def _is_error_line(line: str) -> bool:
    low = line.lower()
    return any(h in low for h in _ERR_HINTS)


def _focus_output(text: str, max_chars: int = _MAX_OUT) -> str:
    """Tronque en gardant les lignes pertinentes : début + lignes d'erreur + fin."""
    text = text or ""
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    head = lines[:25]
    tail = lines[-40:]
    errs = [l for l in lines[25:-40] if _is_error_line(l)]
    merged = head + (["…"] if errs or len(lines) > 65 else [])
    merged += errs[:120]
    merged += (["…"] if errs else []) + tail
    out = "\n".join(merged)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n… [tronqué]"
    return out


def run_checks(command: str, timeout: int = 120) -> str:
    """
    Lance une commande de TEST / LINT / BUILD dans le workspace (pytest, npm test, ruff,
    tsc, make…) et renvoie un verdict PASS/FAIL avec un extrait centré sur les erreurs,
    prêt pour une boucle de correction automatique. Exécute en sandbox Docker si
    disponible (réseau coupé), sinon sur l'hôte.
    command: la commande shell complète (ex: 'pytest -q', 'ruff check .', 'npm test').
    timeout: délai max en secondes (défaut 120).
    """
    command = (command or "").strip()
    if not command:
        return "Erreur : commande vide (ex: 'pytest -q', 'ruff check .', 'npm test')."

    # Lecture seule : un membre « viewer » d'un projet partagé ne lance pas de commandes
    # (elles peuvent modifier le projet).
    try:
        from core import projects
        if not projects.can_write():
            return "Erreur : projet en LECTURE SEULE (rôle lecteur) — exécution de commandes refusée."
    except Exception:
        pass

    from tools.system_tools import check_command_blacklist
    rejection = check_command_blacklist(command)
    if rejection:
        return rejection

    timeout = max(5, min(int(timeout or 120), 900))

    from tools import sandbox_runner
    rc = None
    try:
        if sandbox_runner.sandbox_mode() != "off" and sandbox_runner.docker_available():
            stdout, stderr, rc = sandbox_runner.run_bash(command, timeout=timeout)
            where = "sandbox Docker"
        else:
            import subprocess
            try:
                from core.state import get_workspace_dir
                cwd = get_workspace_dir()
            except Exception:
                cwd = os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd())
            shell = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"
            # -c (non-login) : évite le bruit des profils ; l'agent active un venv via
            # « source .venv/bin/activate && … » si nécessaire.
            res = subprocess.run([shell, "-c", command], capture_output=True, text=True,
                                 timeout=timeout, cwd=cwd)
            stdout, stderr, rc = res.stdout, res.stderr, res.returncode
            where = "hôte"
    except Exception as e:
        # TimeoutExpired et autres : message clair pour la boucle.
        name = type(e).__name__
        if "Timeout" in name:
            return f"⏳ ÉCHEC : délai de {timeout}s dépassé (commande trop longue ou bloquée)."
        return f"Erreur d'exécution : {e}"

    combined = ""
    if stdout:
        combined += stdout
    if stderr:
        combined += ("\n" if combined else "") + stderr
    focused = _focus_output(combined).strip() or "(aucune sortie)"

    verdict = "✅ PASS" if rc == 0 else f"❌ FAIL (code {rc})"
    return (f"{verdict} — `{command}` [{where}]\n"
            f"{'—' * 40}\n{focused}")


def run_tests() -> str:
    """Lance les TESTS du projet actif et renvoie un verdict PASS/FAIL. La commande est
    DÉTECTÉE automatiquement (pytest, npm test…) — tu n'as RIEN à passer.

    À utiliser pour VÉRIFIER après une correction. N'écris JAMAIS toi-même un script de test ou
    de vérification regex ad hoc, et ne lance pas pytest « à la main » via bash : appelle run_tests.
    """
    try:
        from core.state import get_workspace_dir
        from core import code_autofix
        cmd = code_autofix.detect_check_command(get_workspace_dir())
    except Exception as e:  # noqa: BLE001
        return f"Impossible de déterminer la commande de test : {e}"
    if not cmd:
        return ("Aucune commande de test détectée (ni pytest/tests/ ni package.json). Si un fichier "
                "de test existe, lance-le explicitement via run_checks (ex. run_checks('pytest -q'))."
                " N'invente pas de script de vérification.")
    return run_checks(cmd)


def request_code_review() -> str:
    """Fais RELIRE tes modifications récentes (revue SÉCURITÉ + qualité) → liste de points à
    corriger, ou « RAS » si rien.

    À appeler APRÈS run_tests vert, AVANT de conclure : ça rattrape les angles morts qu'une passe
    unique laisse (faille subtile, secret en dur, CRYPTO faible comme un sel STATIQUE, régression).
    Corrige les points renvoyés, relance run_tests, puis conclus. Si un agent d'audit/sécurité
    existe, tu peux aussi lui déléguer (delegate_to_…)."""
    from core import code_review
    return code_review.review_current()


def remember_project_note(note: str) -> str:
    """Mémorise un FAIT DURABLE sur CE projet → réutilisé AUTOMATIQUEMENT aux prochaines sessions
    (la mémoire est ré-injectée dans ton contexte au début de chaque session de code).

    À utiliser quand tu DÉCOUVRES quelque chose de non évident qui te ferait re-perdre du temps
    plus tard : convention de code, décision d'architecture, COMMANDE de test/build, piège récurrent,
    structure/où-se-trouve-quoi. Une note = un fait court. N'y mets JAMAIS de secret/clé.
    """
    from core import project_memory
    return project_memory.remember(note)
