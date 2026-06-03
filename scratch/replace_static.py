import glob
import os

for fpath in glob.glob("static/*", recursive=True):
    if not os.path.isfile(fpath): continue
    if not (fpath.endswith(".js") or fpath.endswith(".css") or fpath.endswith(".html")): continue
    
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig = content
    
    # We replace Athena -> Athena, athena -> athena, ATHENA -> ATHENA
    content = content.replace("Athena", "Athena")
    content = content.replace("athena", "athena")
    content = content.replace("ATHENA", "ATHENA")
    
    if content != orig:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {fpath}")

