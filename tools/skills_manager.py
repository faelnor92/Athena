import os
import re
import ast

# Imports autorisés dans une compétence AUTO-INDUITE (fonctions pures, sans I/O).
# Une skill créée manuellement par l'utilisateur n'est pas restreinte ; ce garde-fou
# ne s'applique qu'à l'auto-apprentissage non supervisé (cf. validate_pure_skill).
_SAFE_IMPORTS = {
    "math", "datetime", "json", "re", "statistics", "itertools", "collections",
    "functools", "typing", "decimal", "random", "string", "textwrap",
    "unicodedata", "fractions", "calendar", "html", "base64", "hashlib",
}


# Compétence créée À LA DEMANDE (save_new_skill) : VALIDÉE PAR L'HUMAIN avant enregistrement →
# on autorise RÉSEAU et FICHIER, mais on BRIDE le SYSTÈME (exécution shell/processus).
_IO_IMPORTS = _SAFE_IMPORTS | {
    # réseau
    "requests", "urllib", "http", "httpx", "ssl", "ftplib", "smtplib", "imaplib", "email",
    # fichiers / données
    "os", "io", "pathlib", "shutil", "glob", "tempfile", "csv", "configparser", "mimetypes",
    "zipfile", "tarfile", "gzip", "pickle", "sqlite3", "time", "uuid", "logging",
}
# Modules SYSTÈME interdits même en mode assoupli (exécution de processus / bas niveau / RCE).
_BLOCKED_IMPORTS = {
    "subprocess", "socket", "ctypes", "pty", "multiprocessing", "signal", "resource",
    "fcntl", "mmap", "importlib", "builtins", "posix", "nt", "sys", "platform", "winreg",
}
# Appels os.* dangereux (lancer un programme / privilèges) — os.path, os.environ… restent OK.
_BLOCKED_OS_ATTR = {"system", "popen", "fork", "forkpty", "kill", "killpg", "chroot",
                    "setuid", "setgid", "seteuid", "setegid", "abort"}


def validate_skill(code: str, skill_name: str):
    """Validation ASSOUPLIE pour une compétence créée À LA DEMANDE (confirmée par l'humain) :
    réseau et fichier AUTORISÉS, SYSTÈME bridé. Le module ne doit contenir que des imports +
    la fonction (aucun effet de bord à l'import). Renvoie (True, "") ou (False, raison)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"syntaxe invalide : {e}"
    found_def = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name == skill_name:
                found_def = True
        elif isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root in _BLOCKED_IMPORTS:
                    return False, f"import SYSTÈME interdit : {a.name}"
                if root not in _IO_IMPORTS:
                    return False, f"import non autorisé : {a.name}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _BLOCKED_IMPORTS:
                return False, f"import SYSTÈME interdit : from {node.module}"
            if root not in _IO_IMPORTS:
                return False, f"import non autorisé : from {node.module}"
        elif isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            continue
        else:
            return False, "le module ne doit contenir que des imports + la fonction (aucun code au niveau module)"
    if not found_def:
        return False, f"la fonction 'def {skill_name}(...)' est absente"
    # eval/exec/__import__/getattr… restent interdits (RCE / évasion). `open` est AUTORISÉ (fichier).
    forbidden_calls = {"eval", "exec", "compile", "__import__", "globals", "locals", "vars",
                       "getattr", "setattr", "delattr", "input"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
            return False, f"appel interdit : {node.func.id}()"
        # os.system / os.popen / os.exec* / os.spawn* → système bridé.
        if isinstance(node, ast.Attribute) and (
                node.attr in _BLOCKED_OS_ATTR or node.attr.startswith(("exec", "spawn"))):
            return False, f"appel SYSTÈME interdit : .{node.attr}()"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"accès interdit à un attribut dunder : .{node.attr}"
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return False, f"identifiant interdit : {node.id}"
    return True, ""


def validate_pure_skill(code: str, skill_name: str):
    """Vérifie qu'une compétence auto-induite est une FONCTION PURE et sûre :
    - le module ne contient que des imports (liste blanche) + la def de la fonction ;
    - aucun effet de bord au niveau module, aucun appel dangereux (eval/exec/open/os…),
      aucun accès à un attribut dunder (anti-évasion).
    Renvoie (True, "") si sûr, sinon (False, raison)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"syntaxe invalide : {e}"

    found_def = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.name == skill_name:
                found_def = True
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _SAFE_IMPORTS:
                    return False, f"import non autorisé : {a.name}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _SAFE_IMPORTS:
                return False, f"import non autorisé : from {node.module}"
        elif isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            continue  # docstring module : toléré
        else:
            return False, "le module ne doit contenir que des imports sûrs et la fonction (aucun code au niveau module)"

    if not found_def:
        return False, f"la fonction 'def {skill_name}(...)' est absente"

    forbidden_calls = {"eval", "exec", "compile", "__import__", "open", "globals",
                       "locals", "vars", "getattr", "setattr", "delattr", "input"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
            return False, f"appel interdit : {node.func.id}()"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"accès interdit à un attribut dunder : .{node.attr}"
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return False, f"identifiant interdit : {node.id}"
    return True, ""


def save_new_skill(skill_name: str, code: str, description: str) -> str:
    """
    Enregistre une nouvelle compétence (Skill) permanente sous forme de fichier Python.
    La compétence deviendra immédiatement disponible pour tous les agents dans les requêtes suivantes !
    Le code doit obligatoirement définir une fonction nommée exactement '{skill_name}'.
    
    Le RÉSEAU (requests, urllib…) et les FICHIERS (open, pathlib, shutil…) sont AUTORISÉS ;
    le SYSTÈME est interdit (subprocess, os.system, socket, eval/exec) — pour exécuter des
    commandes serveur, utilise execute_bash_command. Création soumise à CONFIRMATION utilisateur.

    Args:
        skill_name (str): Nom de la compétence, en minuscules avec des underscores (ex: "calculer_tva", "formater_nom")
        code (str): Le code Python complet de la fonction. Doit être propre, autonome et définir 'def {skill_name}(...)'.
        description (str): Description claire de ce que fait la compétence pour guider les agents.
        
    Returns:
        str: Message de succès ou d'erreur.
    """
    # Validation du nom de fichier et de fonction (snake_case)
    if not re.match(r"^[a-z0-9_]+$", skill_name):
        return "Erreur : Le nom de la compétence doit être composé uniquement de lettres minuscules, chiffres et underscores (snake_case)."
        
    # Vérification que le code définit bien la fonction attendue
    if f"def {skill_name}" not in code:
        return f"Erreur : Le code fourni doit obligatoirement contenir la définition de la fonction 'def {skill_name}(...)'."

    # SÉCURITÉ : une skill est importée et EXÉCUTÉE dans le processus serveur (hors sandbox).
    # save_new_skill étant CONFIRMÉ par l'humain (outil sensible), on autorise RÉSEAU et FICHIER
    # mais on BRIDE le SYSTÈME (exécution de processus / shell). La validation reste OBLIGATOIRE.
    ok, reason = validate_skill(code, skill_name)
    if not ok:
        return (f"Erreur : compétence refusée pour raison de sécurité ({reason}). "
                "Réseau et fichier sont autorisés ; le SYSTÈME (subprocess, os.system, socket…) "
                "est interdit — pour exécuter des commandes serveur, utilise execute_bash_command.")

    os.makedirs("skills", exist_ok=True)
    filepath = os.path.join("skills", f"{skill_name}.py")
    
    try:
        # Écriture du code dans le fichier
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            
        return f"Succès : La compétence '{skill_name}' a été sauvegardée dans {filepath}. Elle sera automatiquement intégrée à la liste des outils."
    except Exception as e:
        return f"Erreur lors de l'enregistrement de la compétence : {str(e)}"

def delete_skill(skill_name: str) -> str:
    """
    Supprime définitivement une compétence personnalisée (Skill) existante.
    
    Args:
        skill_name (str): Nom exact de la compétence à supprimer (ex: "basic_math_tests")
        
    Returns:
        str: Message de succès ou d'erreur.
    """
    if not re.match(r"^[a-z0-9_]+$", skill_name):
        return "Erreur : Le nom de la compétence est invalide."
        
    filepath = os.path.join("skills", f"{skill_name}.py")
    if not os.path.exists(filepath):
        return f"Erreur : La compétence '{skill_name}' n'existe pas ou a déjà été supprimée."
        
    try:
        os.remove(filepath)
        return f"Succès : La compétence '{skill_name}' a été supprimée avec succès du système."
    except Exception as e:
        return f"Erreur lors de la suppression de la compétence : {str(e)}"
