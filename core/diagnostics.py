"""Auto-diagnostic partagé (utilisé par l'API /api/doctor ET le CLI /doctor)."""
import os
import shutil


def run_diagnostics(swarm=None) -> list:
    """Renvoie une liste de vérifications [{name, ok, detail}]."""
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    add("Endpoint LLM custom", bool(os.getenv("CUSTOM_LLM_API_BASE")),
        os.getenv("CUSTOM_LLM_API_BASE", "(non défini)"))
    add("Clé OpenAI", bool(os.getenv("OPENAI_API_KEY")))
    add("Clé Anthropic", bool(os.getenv("ANTHROPIC_API_KEY")))
    if swarm is not None:
        add("Agents chargés", bool(getattr(swarm, "agents", None)), f"{len(swarm.agents)} agent(s)")
    add("Docker (sandbox d'exécution)", shutil.which("docker") is not None,
        "présent" if shutil.which("docker") else "absent — exécution non isolée")
    try:
        from tools.mcp_manager import mcp_manager
        add("MCP", True, mcp_manager.status())
    except Exception as e:
        add("MCP", False, e)
    for mod, label in [("faster_whisper", "STT"), ("aioesphomeapi", "Satellites ESPHome"),
                       ("openwakeword", "Wake word serveur")]:
        try:
            __import__(mod)
            add(f"Voix : {label}", True)
        except Exception:
            add(f"Voix : {label}", False, f"{mod} non installé (requirements-voice.txt)")
    try:
        from tools.memory_tools import semantic_mem
        add("Mémoire sémantique (Chroma)", True, f"{semantic_mem.count()} document(s)")
    except Exception as e:
        add("Mémoire sémantique (Chroma)", False, e)
    try:
        from core.notifications import configured_channels
        ch = configured_channels()
        add("Messageries configurées", bool(ch), ", ".join(ch) if ch else "aucune")
    except Exception as e:
        add("Messageries configurées", False, e)
    try:
        from voice.esphome_satellites import manager as sat_mgr
        st = sat_mgr.status()
        add("Satellites", True,
            f"{st.get('configured', 0)} configuré(s), {len(st.get('connected', []))} connecté(s)")
    except Exception as e:
        add("Satellites", False, e)
    return checks
