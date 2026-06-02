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

    # SÉCURITÉ : une skill est importée et EXÉCUTÉE dans le processus serveur (hors
    # sandbox). On exige donc une fonction PURE et sûre (imports en liste blanche,
    # aucun eval/exec/open/os/dunder). Une skill plus riche doit être déposée
    # manuellement dans skills/ (action humaine délibérée, hors portée des agents).
    ok, reason = validate_pure_skill(code, skill_name)
    if not ok:
        return (f"Erreur : compétence refusée pour raison de sécurité ({reason}). "
                "Une skill enregistrée par un agent doit être une fonction pure et sûre "
                "(imports autorisés : math, datetime, json, re, statistics, etc. ; "
                "ni eval/exec/open, ni accès système).")

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
