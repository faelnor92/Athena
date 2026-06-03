#!/usr/bin/env bash
# =========================================================================
# ATHENA SWARM - LANCEUR INTERACTIF EN DIRECT
# =========================================================================
CYAN='\033[0;36m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

clear
echo -e "${CYAN}${BOLD}"
echo "========================================================================="
echo "   🚀 DEMARRAGE EN DIRECT DE L'ORCHESTRATEUR ATHENA SWARM v2"
echo "========================================================================="
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Ouvrir le navigateur automatiquement après 2 secondes
echo -e "${GREEN}👉 La console d'administration sera ouverte sur http://localhost:8000/${NC}"
(sleep 2 && xdg-open "http://localhost:8000" &> /dev/null) &

# Démarrer le serveur en premier plan visible avec le python système
echo -e "${CYAN}Affichage des logs système en temps réel :${NC}\n"
python3 server.py
