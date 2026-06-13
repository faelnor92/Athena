#!/usr/bin/env bash
# =========================================================================
# INSTALLATEUR DE DÉPLOIEMENT PROFESSIONNEL - ATHENA v2
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
# PRIVILÈGES + GESTIONNAIRE DE PAQUETS
#   Sur un système NU (conteneur LXC/Docker Debian lancé en root), `sudo` peut
#   manquer. On exécute sans sudo si on est déjà root, sinon via sudo.
# -------------------------------------------------------------------------
_have() { command -v "$1" &> /dev/null; }
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
if [ -n "$SUDO" ] && ! _have sudo; then
    echo -e "${RED}❌ Tu n'es pas root et 'sudo' est absent. Relance en root, ou installe sudo d'abord.${NC}"
    exit 1
fi
PKG=""
if _have apt-get; then PKG="apt"; elif _have dnf; then PKG="dnf"; elif _have pacman; then PKG="pacman"; elif _have brew; then PKG="brew"; fi

# -------------------------------------------------------------------------
# ÉTAPE 0 : Paquets de BASE (système nu)
#   Tout ce qui n'est PAS garanti sur une base Debian/conteneur : sudo, git,
#   curl, gnupg, outils de build + en-têtes Python (compilation de wheels).
# -------------------------------------------------------------------------
echo -e "${YELLOW}🔄 Étape 0 : Paquets système de base...${NC}"
case "$PKG" in
    apt)
        $SUDO apt-get update -qq
        $SUDO apt-get install -y --no-install-recommends \
            sudo ca-certificates curl gnupg git build-essential \
            python3 python3-venv python3-pip python3-dev ;;
    dnf)
        $SUDO dnf install -y ca-certificates curl gnupg2 git make gcc \
            python3 python3-pip python3-devel ;;
    pacman)
        $SUDO pacman -Sy --noconfirm ca-certificates curl gnupg git base-devel python python-pip ;;
    brew)
        _have git || brew install git
        _have curl || brew install curl ;;
    *)
        echo -e "${YELLOW}⚠ Gestionnaire de paquets non reconnu — installe manuellement : git, curl, build tools.${NC}" ;;
esac
_have git || { echo -e "${RED}❌ git toujours absent après bootstrap. Abandon.${NC}"; exit 1; }
echo -e "${GREEN}✔ Paquets de base prêts.${NC}"
echo ""

# Support pour l'installation en 1 ligne (curl | bash)
if [ ! -f "server.py" ]; then
    echo -e "${YELLOW}🔄 Installation distante détectée. Clonage du dépôt dans 'athena'...${NC}"
    git clone https://github.com/faelnor92/athena.git athena
    cd athena || exit 1
    chmod +x install.sh
    exec ./install.sh
fi

# -------------------------------------------------------------------------
# ÉTAPE 1 : Python 3.13 via uv
#   Athena exige Python 3.13 (sinon chromadb trop ancien). Or Debian 12 livre
#   3.11 → on installe `uv` qui provisionne 3.13 indépendamment du système, sans
#   compiler ni casser le python système.
# -------------------------------------------------------------------------
echo -e "${YELLOW}🔄 Étape 1 : Python 3.13 (via uv)...${NC}"
if ! _have uv; then
    echo -e "Installation de uv (gestionnaire Python rapide)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
# uv s'installe dans ~/.local/bin (ou ~/.cargo/bin selon la version) → on les ajoute au PATH.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! _have uv; then
    echo -e "${RED}❌ uv introuvable après installation. Vérifie ton accès réseau.${NC}"
    exit 1
fi
echo -e "Récupération de Python 3.13..."
uv python install 3.13
echo -e "${GREEN}✔ uv prêt — Python 3.13 disponible.${NC}"

# -------------------------------------------------------------------------
# ÉTAPE 1b : Navigateur headless (Chromium) + Docker
#   Requis pour AthenaDesign : export PDF (Chromium) et exécution sandboxée du code généré
#   + conteneur dev (Docker). Installation best-effort selon le gestionnaire de paquets.
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 1b : Navigateur headless + Docker (AthenaDesign)...${NC}"
# (_have, SUDO et PKG sont définis plus haut dans le bootstrap.)

# --- Navigateur headless (Chromium / Chrome) ---
if _have chromium || _have chromium-browser || _have google-chrome || _have google-chrome-stable || _have chrome; then
    echo -e "${GREEN}✔ Navigateur headless détecté.${NC}"
else
    echo -e "Installation d'un navigateur headless (Chromium)..."
    case "$PKG" in
        apt) $SUDO apt-get update -qq && { $SUDO apt-get install -y chromium || $SUDO apt-get install -y chromium-browser; } ;;
        dnf) $SUDO dnf install -y chromium ;;
        pacman) $SUDO pacman -S --noconfirm chromium ;;
        brew) brew install --cask chromium 2>/dev/null || brew install chromium 2>/dev/null || true ;;
        *) echo -e "${YELLOW}⚠ Gestionnaire de paquets non détecté — installe Chromium/Chrome manuellement.${NC}" ;;
    esac
    if _have chromium || _have chromium-browser || _have google-chrome || _have chrome; then
        echo -e "${GREEN}✔ Navigateur headless installé.${NC}"
    else
        echo -e "${YELLOW}⚠ Navigateur headless absent → export PDF AthenaDesign indisponible (sinon, pointe CHROMIUM_BIN).${NC}"
    fi
fi

# --- Docker (sandbox d'exécution + dev container) — MÉTHODE OFFICIELLE ---
#   On utilise le script officiel get.docker.com (docker-ce + containerd),
#   PAS le paquet distro `docker.io` (souvent ancien/incomplet).
if _have docker && docker info &> /dev/null; then
    echo -e "${GREEN}✔ Docker opérationnel.${NC}"
elif _have docker; then
    echo -e "${YELLOW}⚠ Docker installé mais le démon ne répond pas. Démarre-le : ${BOLD}${SUDO} systemctl start docker${NC}"
    $SUDO systemctl start docker 2>/dev/null || $SUDO service docker start 2>/dev/null || true
else
    if [ "$OS_TYPE" == "Darwin" ]; then
        echo -e "${YELLOW}⚠ macOS : installe Docker Desktop → https://www.docker.com/products/docker-desktop/${NC}"
    else
        echo -e "Installation de Docker (script officiel get.docker.com)..."
        curl -fsSL https://get.docker.com | $SUDO sh
        if _have docker; then
            $SUDO systemctl enable --now docker 2>/dev/null || $SUDO service docker start 2>/dev/null || true
            # Ajoute l'utilisateur courant au groupe docker (inutile si on est root).
            if [ -n "$SUDO" ] && [ -n "$USER" ]; then
                $SUDO usermod -aG docker "$USER" 2>/dev/null || true
                echo -e "${GREEN}✔ Docker installé (reconnecte-toi pour appliquer le groupe 'docker').${NC}"
            else
                echo -e "${GREEN}✔ Docker installé.${NC}"
            fi
        else
            echo -e "${YELLOW}⚠ Échec d'installation de Docker → l'exécution du code AthenaDesign basculera en mode local NON isolé.${NC}"
        fi
    fi
fi

# -------------------------------------------------------------------------
# ÉTAPE 2 : Environnement Virtuel Python
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 2 : Environnement virtuel Python 3.13 (.venv via uv)...${NC}"
if [ ! -d ".venv" ]; then
    echo -e "Création de .venv en Python 3.13..."
    uv venv --python 3.13 .venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Erreur lors de la création de .venv (uv). Vérifie l'installation de uv / Python 3.13.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✔ Environnement virtuel Python 3.13 créé !${NC}"
else
    echo -e "${GREEN}✔ Environnement virtuel (.venv) déjà présent.${NC}"
fi

# -------------------------------------------------------------------------
# ÉTAPE 3 : Dépendances Python
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 3 : Installation des dépendances Python (requirements.txt)...${NC}"
source .venv/bin/activate
echo -e "Installation des paquets requis (uv pip)..."
uv pip install -r requirements.txt
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
# ÉTAPE 4b : Assistant interactif (composants optionnels + configuration .env)
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 4b : Choix des composants optionnels & configuration...${NC}"
# Le venv est déjà activé : python3 = python du venv → les paquets optionnels y vont.
python3 "$SCRIPT_DIR/setup_wizard.py"

# -------------------------------------------------------------------------
# ÉTAPE 5 : Génération du CLI Exécutable Global ("athena")
# -------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}🔄 Étape 5 : Création de la commande CLI globale 'athena'...${NC}"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

CLI_FILE="$BIN_DIR/athena"
cat << EOF > "$CLI_FILE"
#!/usr/bin/env bash
# =========================================================================
# COMMANDE DE CONTROLE ATHENA MULTI-AGENT
# =========================================================================
APP_DIR="$SCRIPT_DIR"

cd "\$APP_DIR" || exit 1

case "\$1" in
    start)
        echo -e "\033[0;36m🚀 Démarrage de l'orchestrateur Athena v2...\033[0m"
        source .venv/bin/activate
        nohup python3 server.py > server.log 2>&1 &
        PID=\$!
        echo \$PID > server.pid
        echo -e "\033[0;32m✔ Athena démarré en tâche de fond ! (PID: \$PID)\033[0m"
        echo -e "\033[0;35m👉 Console d'administration disponible sur : http://localhost:8000/\033[0m"
        # Ouvre l'UI dans le navigateur (best-effort, après un court délai de démarrage).
        ( sleep 2; (command -v xdg-open >/dev/null && xdg-open http://localhost:8000/ >/dev/null 2>&1) || (command -v open >/dev/null && open http://localhost:8000/ >/dev/null 2>&1) ) &
        ;;
    stop)
        if [ -f server.pid ]; then
            PID=\$(cat server.pid)
            echo -e "\033[0;33m🛑 Arrêt du serveur Athena (PID: \$PID)...\033[0m"
            kill \$PID &> /dev/null
            rm -f server.pid
            echo -e "\033[0;32m✔ Athena arrêté avec succès.\033[0m"
        else
            # Tenter de tuer par nom de processus au cas où
            PIDS=\$(pgrep -f "server.py")
            if [ -n "\$PIDS" ]; then
                echo -e "\033[0;33m🛑 Arrêt des processus Athena en cours...\033[0m"
                kill \$PIDS &> /dev/null
                echo -e "\033[0;32m✔ Athena arrêté.\033[0m"
            else
                echo -e "\033[0;31m❌ Aucun serveur Athena en cours d'exécution.\033[0m"
            fi
        fi
        ;;
    status)
        if pgrep -f "server.py" > /dev/null; then
            PID=\$(pgrep -f "server.py" | head -n 1)
            echo -e "\033[0;32m● Athena est ACTIF et en cours d'exécution (PID: \$PID)\033[0m"
            echo -e "👉 Visitez : http://localhost:8000/"
        else
            echo -e "\033[0;31m● Athena est INACTIF (Arrêté)\033[0m"
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
        echo -e "\033[1;36mOutil de gestion Athena Swarm v2\033[0m"
        echo -e "Usage: athena {start|stop|restart|status|logs}"
        ;;
esac
EOF

chmod +x "$CLI_FILE"
echo -e "${GREEN}✔ Commande installée dans : ${BOLD}$CLI_FILE${NC}"

# Suggestion PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${YELLOW}👉 Note : Pour utiliser la commande 'athena' directement de n'importe où,${NC}"
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
    PLIST_FILE="$HOME/Library/LaunchAgents/fr.unistra.athena.plist"
    cat << EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>fr.unistra.athena</string>
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
    echo -e "${GREEN}✔ Agent de démarrage automatique créé : ${BOLD}~/Library/LaunchAgents/fr.unistra.athena.plist${NC}"
    echo -e "   Pour activer le lancement automatique au démarrage de session :"
    echo -e "   ${CYAN}launchctl load $PLIST_FILE${NC}"

    # macOS .app Shortcut Bundle wrapper
    APP_DIR="$HOME/Desktop/Athena.app"
    mkdir -p "$APP_DIR/Contents/MacOS"
    cat << EOF > "$APP_DIR/Contents/MacOS/Athena"
#!/usr/bin/env bash
open "http://localhost:8000/"
$BIN_DIR/athena start
EOF
    chmod +x "$APP_DIR/Contents/MacOS/Athena"
    echo -e "${GREEN}✔ Lanceur d'application généré sur votre Bureau : ${BOLD}$APP_DIR${NC}"

else
    # LINUX - Raccourci Desktop Entry & Option Service Systemd
    echo -e "Configuration Linux détectée..."
    
    # Desktop Entry (.desktop)
    DESKTOP_FILE="$HOME/.local/share/applications/athena.desktop"
    mkdir -p "$(dirname "$DESKTOP_FILE")"
    cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=2.0
Name=Athena Multi-Agent Swarm
Comment=Bureau Virtuel Multi-Agent & Cockpit No-Code
Exec=bash -c "$BIN_DIR/athena start && xdg-open http://localhost:8000/"
Icon=system-run
Terminal=false
Type=Application
Categories=Development;Office;
EOF
    chmod +x "$DESKTOP_FILE"
    
    # Copie sur le bureau si existant
    if [ -d "$HOME/Desktop" ]; then
        cp "$DESKTOP_FILE" "$HOME/Desktop/"
        chmod +x "$HOME/Desktop/athena.desktop"
        echo -e "${GREEN}✔ Raccourci d'application de bureau créé : ${BOLD}~/Desktop/athena.desktop${NC}"
    fi
    echo -e "${GREEN}✔ Raccourci d'application système enregistré !${NC}"

    # Suggestion Service Systemd
    echo -e "${CYAN}💡 Option Service d'arrière-plan (Systemd) :${NC}"
    echo -e "   Pour exécuter Athena en arrière-plan permanent sur votre serveur Linux, tapez :"
    echo -e "   ${MAGENTA}sudo cp $SCRIPT_DIR/athena-swarm.service /etc/systemd/system/${NC}"
    echo -e "   ${MAGENTA}sudo systemctl enable --now athena-swarm.service${NC}"
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
    
    if ! ollama list | grep -q "qwen2.5:0.5b"; then
        echo -e "${YELLOW}⚠ Le modèle de maintenance (qwen2.5:0.5b) n'est pas détecté.${NC}"
        read -p "Voulez-vous le télécharger pour activer l'Agent de Nuit Gratuit ? (o/n) : " INSTALL_MODEL
        if [[ "$INSTALL_MODEL" =~ ^[OoYy] ]]; then
            echo -e "${CYAN}Téléchargement de qwen2.5:0.5b...${NC}"
            ollama pull qwen2.5:0.5b
        fi
    fi
else
    echo -e "${YELLOW}⚠ Note : Ollama n'est pas détecté.${NC}"
    echo -e "Ollama est recommandé pour faire tourner l'Agent de Maintenance de Nuit gratuitement."
    read -p "Voulez-vous installer Ollama maintenant ? (o/n) : " INSTALL_OLLAMA
    if [[ "$INSTALL_OLLAMA" =~ ^[OoYy] ]]; then
        echo -e "${CYAN}Installation d'Ollama...${NC}"
        curl -fsSL https://ollama.com/install.sh | sh
        echo -e "${CYAN}Téléchargement du modèle de maintenance (qwen2.5:0.5b)...${NC}"
        ollama pull qwen2.5:0.5b
    else
        echo -e "Vous pouvez l'installer plus tard via : ${BOLD}https://ollama.com${NC}"
    fi
fi

# -------------------------------------------------------------------------
# FIN D'INSTALLATION
# -------------------------------------------------------------------------
echo ""
echo -e "${CYAN}${BOLD}========================================================================="
echo " 🎉 INSTALLATION TERMINÉE AVEC SUCCÈS !"
echo "=========================================================================${NC}"
echo -e "Pour démarrer votre bureau virtuel multi-agent, vous pouvez :"
echo -e " 1. Double-cliquer sur le raccourci ${GREEN}Athena${NC} créé sur votre Bureau."
echo -e " 2. Ou démarrer dans votre terminal en tapant :"
echo -e "    👉 ${GREEN}${BOLD}athena start${NC}"
echo ""
echo -e "Ouvrez ensuite votre navigateur sur : ${CYAN}${BOLD}http://localhost:8000/${NC}"
echo ""
