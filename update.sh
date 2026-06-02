#!/usr/bin/env bash
# =========================================================================
# UPDATE SCRIPT - JARVIS SWARM
# =========================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo -e "\033[0;36m🔄 Recherche de mises à jour (git pull)...\033[0m"
git pull origin main

if [ -f "VERSION" ]; then
    VERSION=$(cat VERSION)
    echo -e "\033[0;32m✔ Version locale actuelle : v$VERSION\033[0m"
fi

echo -e "\033[0;33m🔄 Installation des éventuelles nouvelles dépendances...\033[0m"
source venv/bin/activate
pip install -r requirements.txt --quiet

echo -e "\033[0;36m🚀 Redémarrage du serveur Jarvis...\033[0m"
if command -v jarvis &> /dev/null; then
    jarvis restart
else
    if [ -f "$HOME/.local/bin/jarvis" ]; then
        "$HOME/.local/bin/jarvis" restart
    else
        echo -e "\033[0;33m⚠️ Relance manuelle du serveur...\033[0m"
        pkill -f "python.*server.py" || true
        nohup python3 server.py > server.log 2>&1 &
        echo -e "\033[0;32m✔ Serveur relancé en arrière-plan (PID $!).\033[0m"
    fi
fi

echo -e "\033[0;32m✔ Mise à jour terminée !\033[0m"
