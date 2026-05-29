#!/usr/bin/env bash
# =========================================================================
# INSTALLATEUR DE DÉPLOIEMENT PROFESSIONNEL - JARVIS v2
# Compatible : Linux & macOS (Darwin)
# =========================================================================

# Couleurs ANSI Cyber-Néon
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Détection de l'OS
OS_TYPE="$(uname -s)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

clear
echo -e "${CYAN}${BOLD}"
echo "========================================================================="
echo "        __                 _                 ___ "
# shellcheck disable=SC1001
echo "     / /  ___ _ ______  __(_)__  __  __     |_  |"
# shellcheck disable=SC1001
echo "  _ / /  / _ \`/ __/ _ \/ / (_&-<  | |/ /    / __/ "
# shellcheck disable=SC1001
echo "  \___/   \_,_/_/  /_//_/_/ /___/  |___/    /____/ "
echo "                                                 "
echo "        CLI SYSTEM & SERVICE DEPLOYMENT ENGINE (UNIX)"
echo "=========================================================================${NC}"
echo -e "📦 Système détecté : ${MAGENTA}${BOLD}${OS_TYPE}${NC}"
echo ""

# -------------------------------------------------------------------------
# ÉTAPE 1 : Dépendances Système
# -------------------------------------------------------------------------
echo -e "${YELLOW}🔄 Étape 1 : Vérification des dépendances système...${NC}"

# Python3 check
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Erreur : python3 est requis mais introuvable.${NC}"
    if [ "$OS_TYPE" == "Darwin" ]; then
        echo -e "Installez-le avec : ${BOLD}brew install python${NC}"
    else
        echo -e "Installez-le avec : ${BOLD}sudo apt install python3 python3-pip python3-venv${NC}"
    fi
    exit 1
fi
echo -e "${GREEN}✔ Python 3 est disponible : $(python3 --version)${NC}"

# -------------------------------------------------------------------------
# ÉTAPE 2 : Environnement Virtuel Python
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 2 : Configuration de l'environnement virtuel Python (.venv)...${NC}"
if [ ! -d ".venv" ]; then
    echo -e "Création du dossier de l'environnement virtuel (.venv)..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Erreur lors de la création de .venv. Installez python3-venv ou vérifiez vos permissions.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✔ Environnement virtuel créé avec succès !${NC}"
else
    echo -e "${GREEN}✔ Environnement virtuel (.venv) déjà présent.${NC}"
fi

# -------------------------------------------------------------------------
# ÉTAPE 3 : Dépendances Python
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 3 : Installation des dépendances Python (requirements.txt)...${NC}"
source .venv/bin/activate
echo -e "Mise à niveau de pip..."
pip install --upgrade pip &> /dev/null

echo -e "Installation des paquets requis..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Erreur lors de l'installation des dépendances.${NC}"
    exit 1
fi
echo -e "${GREEN}✔ Toutes les dépendances Python ont été installées avec succès !${NC}"

# -------------------------------------------------------------------------
# ÉTAPE 4 : Fichier .env
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 4 : Configuration des variables d'environnement (.env)...${NC}"
if [ ! -f ".env" ]; then
    echo -e "Création du fichier .env à partir de .env.example..."
    cp .env.example .env
    echo -e "${GREEN}✔ Fichier .env créé !${NC}"
else
    echo -e "${GREEN}✔ Le fichier de configuration .env existe déjà (non modifié).${NC}"
fi

# -------------------------------------------------------------------------
# ÉTAPE 5 : Génération du CLI Exécutable Global ("jarvis")
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 5 : Création de la commande CLI globale 'jarvis'...${NC}"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

CLI_FILE="$BIN_DIR/jarvis"
cat << EOF > "$CLI_FILE"
#!/usr/bin/env bash
# =========================================================================
# COMMANDE DE CONTROLE JARVIS MULTI-AGENT
# =========================================================================
APP_DIR="$SCRIPT_DIR"

cd "\$APP_DIR" || exit 1

case "\$1" in
    start)
        echo -e "\033[0;36m🚀 Démarrage de l'orchestrateur Jarvis v2...\033[0m"
        source .venv/bin/activate
        nohup python3 server.py > server.log 2>&1 &
        PID=\$!
        echo \$PID > server.pid
        echo -e "\033[0;32m✔ Jarvis démarré en tâche de fond ! (PID: \$PID)\033[0m"
        echo -e "\033[0;35m👉 Console d'administration disponible sur : http://localhost:8000/\033[0m"
        ;;
    stop)
        if [ -f server.pid ]; then
            PID=\$(cat server.pid)
            echo -e "\033[0;33m🛑 Arrêt du serveur Jarvis (PID: \$PID)...\033[0m"
            kill \$PID &> /dev/null
            rm -f server.pid
            echo -e "\033[0;32m✔ Jarvis arrêté avec succès.\033[0m"
        else
            # Tenter de tuer par nom de processus au cas où
            PIDS=\$(pgrep -f "server.py")
            if [ -n "\$PIDS" ]; then
                echo -e "\033[0;33m🛑 Arrêt des processus Jarvis en cours...\033[0m"
                kill \$PIDS &> /dev/null
                echo -e "\033[0;32m✔ Jarvis arrêté.\033[0m"
            else
                echo -e "\033[0;31m❌ Aucun serveur Jarvis en cours d'exécution.\033[0m"
            fi
        fi
        ;;
    status)
        if pgrep -f "server.py" > /dev/null; then
            PID=\$(pgrep -f "server.py" | head -n 1)
            echo -e "\033[0;32m● Jarvis est ACTIF et en cours d'exécution (PID: \$PID)\033[0m"
            echo -e "👉 Visitez : http://localhost:8000/"
        else
            echo -e "\033[0;31m● Jarvis est INACTIF (Arrêté)\033[0m"
        fi
        ;;
    restart)
        \$0 stop
        sleep 1
        \$0 start
        ;;
    logs)
        if [ -f server.log ]; then
            tail -n 50 -f server.log
        else
            echo -e "\033[0;31m❌ Aucun fichier de log trouvé.\033[0m"
        fi
        ;;
    *)
        echo -e "\033[1;36mOutil de gestion Jarvis Swarm v2\033[0m"
        echo -e "Usage: jarvis {start|stop|restart|status|logs}"
        ;;
esac
EOF

chmod +x "$CLI_FILE"
echo -e "${GREEN}✔ Commande installée dans : ${BOLD}$CLI_FILE${NC}"

# Suggestion PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${YELLOW}👉 Note : Pour utiliser la commande 'jarvis' directement de n'importe où,${NC}"
    echo -e "   ajoutez cette ligne à votre fichier ${BOLD}~/.bashrc${NC} ou ${BOLD}~/.zshrc${NC} :"
    echo -e "   ${MAGENTA}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi

# -------------------------------------------------------------------------
# ÉTAPE 6 : Raccourcis Bureau & Services
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 6 : Intégration Système & Raccourcis d'Application...${NC}"

# Création du lanceur local run.sh
cat << EOF > run.sh
#!/usr/bin/env bash
source "$SCRIPT_DIR/.venv/bin/activate"
python3 "$SCRIPT_DIR/server.py"
EOF
chmod +x run.sh

if [ "$OS_TYPE" == "Darwin" ]; then
    # MAC OS - Intégration LaunchAgent & Raccourci Finder Bundle
    echo -e "Configuration macOS détectée..."
    
    # launchd plist configuration
    PLIST_FILE="$HOME/Library/LaunchAgents/fr.unistra.jarvis.plist"
    cat << EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>fr.unistra.jarvis</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/run.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/server.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/server.log</string>
</dict>
</plist>
EOF
    echo -e "${GREEN}✔ Agent de démarrage automatique créé : ${BOLD}~/Library/LaunchAgents/fr.unistra.jarvis.plist${NC}"
    echo -e "   Pour activer le lancement automatique au démarrage de session :"
    echo -e "   ${CYAN}launchctl load $PLIST_FILE${NC}"

    # macOS .app Shortcut Bundle wrapper
    APP_DIR="$HOME/Desktop/Jarvis.app"
    mkdir -p "$APP_DIR/Contents/MacOS"
    cat << EOF > "$APP_DIR/Contents/MacOS/Jarvis"
#!/usr/bin/env bash
open "http://localhost:8000/"
$BIN_DIR/jarvis start
EOF
    chmod +x "$APP_DIR/Contents/MacOS/Jarvis"
    echo -e "${GREEN}✔ Lanceur d'application généré sur votre Bureau : ${BOLD}$APP_DIR${NC}"

else
    # LINUX - Raccourci Desktop Entry & Option Service Systemd
    echo -e "Configuration Linux détectée..."
    
    # Desktop Entry (.desktop)
    DESKTOP_FILE="$HOME/.local/share/applications/jarvis.desktop"
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=2.0
Name=Jarvis Multi-Agent Swarm
Comment=Bureau Virtuel Multi-Agent & Cockpit No-Code
Exec=bash -c "$BIN_DIR/jarvis start && xdg-open http://localhost:8000/"
Icon=system-run
Terminal=false
Type=Application
Categories=Development;Office;
EOF
    chmod +x "$DESKTOP_FILE"
    
    # Copie sur le bureau si existant
    if [ -d "$HOME/Desktop" ]; then
        cp "$DESKTOP_FILE" "$HOME/Desktop/"
        chmod +x "$HOME/Desktop/jarvis.desktop"
        echo -e "${GREEN}✔ Raccourci d'application de bureau créé : ${BOLD}~/Desktop/jarvis.desktop${NC}"
    fi
    echo -e "${GREEN}✔ Raccourci d'application système enregistré !${NC}"

    # Suggestion Service Systemd
    echo -e "${CYAN}💡 Option Service d'arrière-plan (Systemd) :${NC}"
    echo -e "   Pour exécuter Jarvis en arrière-plan permanent sur votre serveur Linux, tapez :"
    echo -e "   ${MAGENTA}sudo cp $SCRIPT_DIR/jarvis-swarm.service /etc/systemd/system/${NC}"
    echo -e "   ${MAGENTA}sudo systemctl enable --now jarvis-swarm.service${NC}"
fi

# -------------------------------------------------------------------------
# ÉTAPE 7 : Découverte Ollama
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 7 : Détection de l'intégration locale Ollama...${NC}"
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✔ Ollama est installé localement !${NC}"
    echo -e "Modèles installés :"
    ollama list | tail -n +2 | awk '{print " - " $1}'
    
    # Proposer de pull un modèle léger si aucun modèle de code/texte n'est détecté
    if ! ollama list | grep -qE "llama|qwen|mistral|phi"; then
        echo -e "${YELLOW}⚠ Aucun modèle adapté aux agents n'a été détecté dans Ollama.${NC}"
        echo -e "   Il est fortement recommandé de télécharger un modèle compact (ex: Qwen 2.5 Coder 1.5B)."
        echo -e "   Pour le faire automatiquement en arrière-plan :"
        echo -e "   👉 ${CYAN}ollama pull qwen2.5-coder:1.5b${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Note : Ollama n'est pas détecté. Si vous souhaitez faire tourner vos agents${NC}"
    echo -e "   en 100% local et gratuit (sans clés API cloud), installez Ollama : ${BOLD}https://ollama.com${NC}"
fi

# -------------------------------------------------------------------------
# FIN D'INSTALLATION
# -------------------------------------------------------------------------
echo ""
echo -e "${CYAN}${BOLD}========================================================================="
echo " 🎉 INSTALLATION TERMINÉE AVEC SUCCÈS !"
echo "=========================================================================${NC}"
echo -e "Pour démarrer votre bureau virtuel multi-agent, vous pouvez :"
echo -e " 1. Double-cliquer sur le raccourci ${GREEN}Jarvis${NC} créé sur votre Bureau."
echo -e " 2. Ou démarrer dans votre terminal en tapant :"
echo -e "    👉 ${GREEN}${BOLD}jarvis start${NC}"
echo ""
echo -e "Ouvrez ensuite votre navigateur sur : ${CYAN}${BOLD}http://localhost:8000/${NC}"
echo ""
