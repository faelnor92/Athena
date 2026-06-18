#!/usr/bin/env python3
"""Diagnostic MCP — état réel des serveurs (connexion, erreurs, outils), secrets MASQUÉS.

Usage (depuis la racine du projet) :
    .venv/bin/python scripts/diag_mcp.py

Ne modifie RIEN. Démarre les serveurs MCP comme le fait Athena au boot, attend la
connexion, puis affiche : config (tokens masqués), serveurs connectés/en erreur,
nombre d'outils par serveur, et combien d'outils Home Assistant seraient exposés à
l'agent pour une requête domotique type (pour distinguer « pas connecté » de
« connecté mais masqué par le filtre de pertinence »)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mask(v, key=""):
    if isinstance(v, str) and ("TOKEN" in key.upper() or "KEY" in key.upper() or "PASS" in key.upper()):
        return f"[masqué len={len(v)}]"
    return v


def main():
    from tools.mcp_manager import mcp_manager

    print("=== CONFIG MCP (telle que chargée, après consolidation HA) ===")
    cfg = mcp_manager._load_config()
    for name, conf in cfg.items():
        env = conf.get("env", {}) or {}
        cmd = str(conf.get("command", "") or "")
        bin_ok = os.path.exists(cmd) if cmd else None
        url = env.get("HOMEASSISTANT_URL") or conf.get("url") or ""
        tok = env.get("HOMEASSISTANT_TOKEN", "") or ""
        print(f"  • {name!r}: disabled={conf.get('disabled')} | command_existe={bin_ok} "
              f"| url={url!r} | token_len={len(tok)}")

    print("\n=== DÉMARRAGE des serveurs MCP (12 s d'attente) ===")
    mcp_manager.start()
    time.sleep(12)

    st = mcp_manager.status()
    print("serveurs configurés :", st.get("configured_servers"))
    print("serveurs CONNECTÉS  :", st.get("connected_servers"))
    print("outils MCP au total :", st.get("tool_count"))
    errs = st.get("errors") or {}
    if errs:
        print("\n=== ERREURS DE CONNEXION (la cause du point rouge) ===")
        for srv, e in errs.items():
            print(f"  ✗ {srv}: {e}")
    else:
        print("\n(aucune erreur de connexion enregistrée)")

    tools = getattr(mcp_manager, "_tools", {})
    by_server = {}
    for tname, meta in tools.items():
        srv = (meta.get("server", "?") if isinstance(meta, dict) else "?")
        by_server.setdefault(srv, []).append(tname)
    print("\n=== OUTILS PAR SERVEUR ===")
    for srv, names in by_server.items():
        print(f"  {srv}: {len(names)} outils (ex: {names[:5]})")

    # Le filtre de pertinence voit-il les outils HA pour une requête domotique ?
    ha_names = [n for n, m in tools.items()
                if isinstance(m, dict) and str(m.get("server", "")).lower()
                in ("homeassistant", "home-assistant", "ha")]
    print(f"\n=== Outils Home Assistant enregistrés : {len(ha_names)} ===")
    if ha_names:
        print("→ HA EST connecté. Si Athena dit « pas de MCP », c'est le FILTRE DE PERTINENCE")
        print("  (noms ha_* en anglais) qui les masque hors requête domotique.")
    else:
        print("→ HA n'expose AUCUN outil : voir les erreurs ci-dessus (token/réseau/binaire).")


if __name__ == "__main__":
    main()
