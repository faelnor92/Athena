import os
import glob
import re

files_to_process = [
    "README.md", "API_DOCS.md", "SETUP.md",
    "agents.default.yaml", "agents.example.yaml",
    "Dockerfile", "docker-compose.yml", "install.sh", "install.ps1", "run.sh", "update.sh", "update.ps1",
    "docs/esphome-satellite.yaml",
    "athena-swarm.service",
    ".env.example"
]

# also add all tests
files_to_process.extend(glob.glob("tests/*.py"))
files_to_process.extend(glob.glob("tests/*.json"))

for fpath in files_to_process:
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Replace Athena -> Athena, athena -> athena, ATHENA -> ATHENA
        new_content = content.replace("Athena", "Athena")
        new_content = new_content.replace("athena", "athena")
        new_content = new_content.replace("ATHENA", "ATHENA")
        
        if new_content != content:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Updated {fpath}")
