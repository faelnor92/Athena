"""Orchestration par script : l'agent écrit UN script Python qui appelle plusieurs
outils programmatiquement (boucles, conditions) → un pipeline multi-étapes s'exécute
en UN SEUL tour, sans gonfler le contexte (équivalent de l'orchestration RPC d'Hermes).

Sécurité : le script est validé par AST (aucun import dangereux, pas d'eval/exec/open,
pas d'accès dunder, pas de boucle while), exécuté avec des builtins RESTREINTS et un
sous-ensemble d'outils SÛRS exposés, avec timeout. Désactivable via TOOL_SCRIPTS=false.
"""
import ast
import io
import os
import threading
import contextlib
import importlib

# Outils sûrs exposés au script (lecture/recherche/mémoire/inspection/calcul). On EXCLUT
# shell, exécution de code brute, SSH, écriture de fichiers et génération lourde.
SCRIPT_SAFE_TOOLS = {
    # Web / mémoire
    "web_search", "web_scrape", "search_memory", "memorize_fact", "store_document",
    "query_graph", "remember_relation",
    # Agenda / listes / domotique (lecture + mutations légères)
    "get_list_items", "add_list_item", "toggle_list_item",
    "list_calendar_events", "add_calendar_event", "get_ha_state", "get_daily_briefing",
    "get_time", "get_weather",
    # Inspection CODE (lecture seule) — batch d'analyse sans gonfler le contexte
    "read_file", "file_outline", "search_code", "find_definition", "find_references",
    "git_status", "git_diff", "git_log",
    # Documents / e-mails (lecture seule)
    "analyze_document", "read_inbox", "read_email", "search_emails",
    # Édition de documents longs (.docx, romans) : flux open→read→revise→publish en UN script
    # → évite la narration étape par étape (le modèle tentait ces appels en script, qui échouaient).
    "document_open", "document_read", "document_revise", "document_publish",
    "document_autorevise", "document_check_coherence", "document_translate", "document_check_repetitions",
    # Nextcloud (fichiers/tâches/contacts) : lecture + écriture (pas la suppression dans un script).
    "nextcloud_list_files", "nextcloud_read_file", "nextcloud_write_file",
    "nextcloud_list_tasks", "nextcloud_search_contacts",
}

_SAFE_IMPORTS = {"math", "json", "re", "datetime", "statistics", "itertools",
                 "collections", "functools", "decimal", "string", "fractions"}

_FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "open", "globals",
                    "locals", "vars", "getattr", "setattr", "delattr", "input"}

_SAFE_BUILTINS = {
    k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
    for k in ("len", "range", "enumerate", "zip", "sorted", "sum", "min", "max",
              "abs", "round", "all", "any", "map", "filter", "list", "dict", "set",
              "tuple", "str", "int", "float", "bool", "isinstance", "reversed",
              "repr", "format", "print", "sorted", "type", "frozenset", "divmod", "pow")
}


def _safe_import(name, *args, **kwargs):
    """Import restreint à la liste blanche (utilisé comme __import__ du script)."""
    if name.split(".")[0] not in _SAFE_IMPORTS:
        raise ImportError(f"import non autorisé : {name}")
    return importlib.import_module(name)


_SAFE_BUILTINS["__import__"] = _safe_import


def validate_tool_script(code: str):
    """Valide la sûreté d'un script d'orchestration. Renvoie (True, "") ou (False, raison)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"syntaxe invalide : {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _SAFE_IMPORTS:
                    return False, f"import non autorisé : {a.name}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _SAFE_IMPORTS:
                return False, f"import non autorisé : from {node.module}"
        elif isinstance(node, ast.While):
            return False, "boucle 'while' interdite (risque de boucle infinie) ; utilise 'for'"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
            return False, f"appel interdit : {node.func.id}()"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"accès interdit à un attribut dunder : .{node.attr}"
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            return False, f"identifiant interdit : {node.id}"
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            # Les dunders dans une f-string sont vus par l'AST, mais pas ceux d'une chaîne
            # littérale passée à str.format ("{0.__class__...}".format(x)) → on bloque ici.
            return False, "chaîne contenant '__' interdite (anti-évasion sandbox via str.format)"
    return True, ""


def _build_namespace():
    """Construit l'espace de noms exposé au script : outils sûrs + compétences + modules sûrs."""
    import importlib
    ns = {}
    try:
        from core.swarm import AVAILABLE_TOOLS, load_dynamic_skills
        for name, fn in AVAILABLE_TOOLS.items():
            if name in SCRIPT_SAFE_TOOLS:
                ns[name] = fn
        # Les compétences dynamiques (dont auto-induites) sont exposées.
        for name, fn in load_dynamic_skills().items():
            ns[name] = fn
    except Exception:
        pass
    for mod in ("math", "json", "re", "datetime", "statistics"):
        try:
            ns[mod] = importlib.import_module(mod)
        except Exception:
            pass
    return ns


def run_tool_script(code: str) -> str:
    """
    Exécute UN script Python qui appelle PLUSIEURS outils en un seul tour (boucles,
    conditions, agrégation). À PRÉFÉRER dès qu'une tâche enchaîne/filtre/agrège des
    résultats : seule la sortie finale revient → énorme économie de contexte/tokens.

    Outils appelables dans le script (lecture/recherche/inspection + mutations légères) :
      web_search, web_scrape, search_memory, store_document, memorize_fact, query_graph,
      remember_relation, get_list_items, add_list_item, toggle_list_item,
      list_calendar_events, add_calendar_event, get_ha_state, get_daily_briefing,
      get_time, get_weather, read_file, file_outline, search_code, find_definition,
      find_references, git_status, git_diff, git_log, analyze_document, read_inbox,
      read_email — ainsi que toutes les compétences. Modules : math, json, re, datetime,
      statistics. Affecte le résultat final à 'result' OU utilise print().
    Sûreté : pas d'écriture de fichier/shell/SSH/exec, pas d'import système, pas de while.
    Exemple : for q in ["a","b","c"]: print(web_search(q))   # 3 recherches en 1 tour.
    code: Le script Python à exécuter.
    """
    if os.getenv("TOOL_SCRIPTS", "true").lower() not in ("true", "1", "yes"):
        return "Erreur : l'orchestration par script est désactivée (TOOL_SCRIPTS=false)."
    ok, reason = validate_tool_script(code)
    if not ok:
        # Redirection utile : le modèle tente souvent subprocess/os/paramiko pour faire du
        # SSH ou du shell → ça ne passera JAMAIS le bac à sable. On le réoriente vers l'outil
        # dédié plutôt que de le laisser boucler sur des refus.
        low = (code or "").lower()
        if any(k in low for k in ("subprocess", "import os", "paramiko", "ssh ", "os.system", "popen")):
            return (f"Script refusé (sûreté) : {reason}. ⛔ N'utilise PAS run_tool_script pour du "
                    "SSH/shell. Appelle DIRECTEMENT l'outil `execute_bash_command(command=\"...\", "
                    "host=\"<label du serveur>\")` (il gère le SSH lui-même). Pour la liste des "
                    "serveurs : `list_ssh_hosts()`.")
        return f"Script refusé (sûreté) : {reason}"

    ns = _build_namespace()
    ns["__builtins__"] = _SAFE_BUILTINS
    out = io.StringIO()
    result_holder = {"err": None}
    timeout = float(os.getenv("TOOL_SCRIPT_TIMEOUT", "30") or 30)
    # Budget d'instructions : interrompt RÉELLEMENT une boucle CPU-bound (les `for`
    # sont autorisés) — le simple join() ne tue pas un thread bloqué en calcul.
    max_steps = int(os.getenv("TOOL_SCRIPT_MAX_STEPS", "5000000") or 5000000)

    def _run():
        import sys as _sys
        steps = [0]

        def _tracer(frame, event, arg):
            if event == "line":
                steps[0] += 1
                if steps[0] > max_steps:
                    raise RuntimeError(f"budget d'instructions dépassé ({max_steps})")
            return _tracer

        try:
            _sys.settrace(_tracer)
            with contextlib.redirect_stdout(out):
                exec(code, ns)  # nosec B102 — code validé par AST (imports/appels allowlistés, eval/exec/open interdits) + builtins restreints + budget d'instructions
        except Exception as e:
            result_holder["err"] = e
        finally:
            _sys.settrace(None)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return f"Erreur : script interrompu (dépassement du délai de {timeout:.0f}s)."
    if result_holder["err"] is not None:
        return f"Erreur d'exécution du script : {result_holder['err']}"

    printed = out.getvalue().strip()
    result = ns.get("result")
    parts = []
    if printed:
        parts.append(printed)
    if result is not None:
        parts.append(f"result = {result}")
    return "\n".join(parts) if parts else "Script exécuté (aucune sortie ; définis 'result' ou utilise print())."
