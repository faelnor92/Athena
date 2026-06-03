import glob
import os

for fpath in glob.glob("evals/*", recursive=True) + glob.glob("scratch/*", recursive=True):
    if not os.path.isfile(fpath): continue
    
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig = content
    content = content.replace("Athena", "Athena").replace("athena", "athena").replace("ATHENA", "ATHENA")
    
    if content != orig:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {fpath}")
