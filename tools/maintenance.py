import ast
import os
import shutil
import urllib.request
import urllib.error
import json

def _check_ollama_available(model="qwen2.5:0.5b"):
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                models = [m.get("name") for m in data.get("models", [])]
                return model in models or f"{model}:latest" in models
    except Exception:
        pass
    return False

def _ask_ollama_to_fix(filepath, code, error_msg, model="qwen2.5:0.5b"):
    prompt = f"The following python script has a syntax or logic error:\n{error_msg}\n\nCode:\n```python\n{code}\n```\n\nPlease reply with ONLY the corrected python code, no markdown wrappers."
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            fixed_code = result.get("response", "").strip()
            if fixed_code.startswith("```python"):
                fixed_code = fixed_code[9:]
            if fixed_code.endswith("```"):
                fixed_code = fixed_code[:-3]
            
            # Verify the fixed code with AST
            ast.parse(fixed_code)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(fixed_code.strip() + "\n")
            return True
    except Exception as e:
        print(f"[Maintenance] Failed to repair with Ollama: {e}")
        return False

def cleanup_skills():
    """
    Scanne le dossier skills/, vérifie la syntaxe AST des fichiers Python.
    Tente de réparer les fichiers corrompus via un modèle local Ollama.
    Archive les fichiers impossibles à réparer.
    """
    skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
    archive_dir = os.path.join(skills_dir, "archive")
    
    if not os.path.exists(skills_dir):
        return "Le dossier skills/ n'existe pas."
        
    os.makedirs(archive_dir, exist_ok=True)
    
    report = []
    ollama_ready = _check_ollama_available()
    
    for filename in os.listdir(skills_dir):
        if not filename.endswith(".py") or filename == "__init__.py":
            continue
            
        filepath = os.path.join(skills_dir, filename)
        
        # Read file
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            continue
            
        # Check AST
        try:
            ast.parse(code)
            report.append(f"✅ {filename} : OK")
        except SyntaxError as e:
            error_msg = str(e)
            report.append(f"❌ {filename} : Erreur de syntaxe ({error_msg})")
            
            repaired = False
            if ollama_ready:
                report.append(f"  -> Tentative de réparation locale via Ollama (qwen2.5:0.5b)...")
                if _ask_ollama_to_fix(filepath, code, error_msg):
                    report.append(f"  -> 🎉 Réparation réussie pour {filename} !")
                    repaired = True
                else:
                    report.append(f"  -> ⚠️ Échec de la réparation IA.")
            
            if not repaired:
                report.append(f"  -> 📦 Déplacement vers skills/archive/{filename}")
                shutil.move(filepath, os.path.join(archive_dir, filename))
                
    return "\n".join(report) if report else "Aucune compétence à nettoyer."
