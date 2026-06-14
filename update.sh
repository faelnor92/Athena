#!/usr/bin/env bash
# =========================================================================
# UPDATE SCRIPT - ATHENA SWARM
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
# Le venv est .venv (créé par install.sh). On utilise SON python directement → pas de
# bascule sur le python système (qui déclenche « externally-managed-environment » sur Debian).
if [ -x ".venv/bin/python" ]; then
    .venv/bin/python -m pip install -r requirements.txt --quiet
else
    echo -e "\033[0;31m⚠️ .venv introuvable — relance ./install.sh.\033[0m"
fi

# Serveur MCP Home Assistant (ha-mcp) : son .venv est un artefact de build gitignoré → on le
# construit s'il manque (sinon HA reste en repli HTTP 127.0.0.1 et ne fonctionne pas).
HA_MCP_DIR="$SCRIPT_DIR/tools/mcp-servers/ha-mcp"
if [ -f "$HA_MCP_DIR/pyproject.toml" ] && [ ! -x "$HA_MCP_DIR/.venv/bin/ha-mcp" ]; then
    echo -e "\033[0;33m🔄 Construction du serveur MCP Home Assistant (ha-mcp)...\033[0m"
    if command -v uv >/dev/null 2>&1; then
        ( cd "$HA_MCP_DIR" && uv venv .venv --python 3.13 >/dev/null 2>&1 \
          && uv pip install --python .venv/bin/python . >/dev/null 2>&1 ) \
          && echo -e "\033[0;32m✔ ha-mcp construit.\033[0m" \
          || echo -e "\033[0;33m⚠️ Build ha-mcp échoué — HA restera en repli HTTP.\033[0m"
    else
        echo -e "\033[0;33m⚠️ uv introuvable — impossible de construire ha-mcp (relance ./install.sh).\033[0m"
    fi
fi

echo -e "\033[0;36m🚀 Redémarrage du serveur Athena...\033[0m"
# Priorité au service systemd s'il pilote Athena : un seul gestionnaire de process,
# pas de double instance (le nohup + Restart=always se battraient sur le port 8000).
SVC_ACTIVE=""
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet athena-swarm.service 2>/dev/null; then
    SVC_ACTIVE="1"
fi

if [ -n "$SVC_ACTIVE" ]; then
    # On tente un restart propre (OK si root) ; sinon on tue le process et on laisse
    # Restart=always relancer avec le nouveau code (fonctionne même sans droits root).
    if systemctl restart athena-swarm.service 2>/dev/null || sudo systemctl restart athena-swarm.service 2>/dev/null; then
        echo -e "\033[0;32m✔ Service athena-swarm redémarré (systemd).\033[0m"
    else
        echo -e "\033[0;33m⚠️ Restart systemd sans droits — kill + relance auto par Restart=always...\033[0m"
        pkill -f "python.*server.py" || true
    fi
elif command -v athena &> /dev/null; then
    athena restart
elif [ -f "$HOME/.local/bin/athena" ]; then
    "$HOME/.local/bin/athena" restart
else
    echo -e "\033[0;33m⚠️ Relance manuelle du serveur...\033[0m"
    pkill -f "python.*server.py" || true
    nohup .venv/bin/python server.py > server.log 2>&1 &
    echo -e "\033[0;32m✔ Serveur relancé en arrière-plan (PID $!).\033[0m"
fi

echo -e "\033[0;32m✔ Mise à jour terminée !\033[0m"
