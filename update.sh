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
source .venv/bin/activate
pip install -r requirements.txt --quiet

echo -e "\033[0;36m🚀 Redémarrage du serveur Jarvis...\033[0m"
if command -v jarvis &> /dev/null; then
    jarvis restart
else
    # Si le CLI n'est pas dans le PATH global
    if [ -f "$HOME/.local/bin/jarvis" ]; then
        "$HOME/.local/bin/jarvis" restart
    else
        echo -e "\033[0;33m⚠️ Commande 'jarvis' introuvable. Si le serveur tournait, veuillez le relancer manuellement avec 'python3 server.py'.\033[0m"
    fi
fi

echo -e "\033[0;32m✔ Mise à jour terminée !\033[0m"
