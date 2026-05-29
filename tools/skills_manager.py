import os
import re

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
