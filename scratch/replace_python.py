import glob
import os

for fpath in glob.glob("**/*.py", recursive=True):
    if not os.path.isfile(fpath): continue
    if "scratch/" in fpath: continue
    
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig = content
    
    # 1. Fallbacks d'orchestrateur dans swarm.py
    content = content.replace('"Athena"', '"Athena"')
    content = content.replace("'Athena'", "'Athena'")
    
    # 2. Textes UI
    content = content.replace("Athena réfléchit", "Athena réfléchit")
    content = content.replace("Notification Athena", "Notification Athena")
    content = content.replace("Alerte Budget Athena", "Alerte Budget Athena")
    
    # 3. Commentaires
    content = content.replace("Athena", "Athena")
    content = content.replace("athena", "athena")
    content = content.replace("ATHENA", "ATHENA")
    
    if content != orig:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {fpath}")

