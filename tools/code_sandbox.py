import sys
import subprocess
import tempfile
import os

def execute_python_code(code: str) -> str:
    """
    Exécute de manière autonome un script Python dans un sous-processus sécurisé (sandbox locale)
    et capture la sortie standard (stdout) et les erreurs (stderr).
    Utile pour tester tes fonctions et valider qu'elles marchent avant de répondre à l'utilisateur.
    
    Args:
        code (str): Le code Python complet à exécuter.
        
    Returns:
        str: Le résultat de l'exécution (stdout ou les erreurs stderr).
    """
    # Crée un fichier temporaire pour stocker le code
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name
        
    try:
        # Exécution avec un timeout de 5 secondes dans le dossier actif
        cwd = os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd())
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd
        )
        
        output = ""
        if result.stdout:
            output += f"--- SORTIE (stdout) ---\n{result.stdout}\n"
        if result.stderr:
            output += f"--- ERREUR (stderr) ---\n{result.stderr}\n"
            
        if not output:
            output = "Code exécuté avec succès (aucune sortie)."
            
        return output
    except subprocess.TimeoutExpired:
        return "Erreur: Temps d'exécution dépassé (Timeout de 5 secondes)."
    except Exception as e:
        return f"Erreur lors de l'exécution: {str(e)}"
    finally:
        # Nettoie le fichier temporaire
        if os.path.exists(temp_path):
            os.remove(temp_path)
