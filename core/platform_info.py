"""Détection de la plateforme hôte et de l'environnement d'exécution.

Sert à :
  - informer les agents de l'OS réel (Linux / Windows / macOS) et du shell ;
  - distinguer l'hôte de l'environnement d'EXÉCUTION (la sandbox Docker tourne
    sous Linux quel que soit l'hôte) pour que les agents génèrent les bonnes
    commandes.
"""
import os
import platform
import shutil


def get_version() -> str:
    try:
        ver_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")
        with open(ver_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "unknown"

def get_platform_info() -> dict:
    system = platform.system()  # 'Linux', 'Windows', 'Darwin'
    os_name = {"Linux": "Linux", "Windows": "Windows", "Darwin": "macOS"}.get(system, system)
    if system == "Windows":
        shell = "PowerShell"
    elif system == "Darwin":
        shell = "zsh"
    else:
        shell = "bash"
    return {
        "system": system,
        "os": os_name,
        "release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "shell": shell,
        "is_windows": system == "Windows",
        "docker": shutil.which("docker") is not None,
    }


def sandbox_active() -> bool:
    """Vrai si les commandes/code s'exécutent dans la sandbox Docker (Linux)."""
    mode = os.getenv("SANDBOX_MODE", "docker").strip().lower()
    return mode != "off" and shutil.which("docker") is not None


def execution_env_hint() -> str:
    """Phrase à injecter dans le system prompt pour guider les agents."""
    p = get_platform_info()
    if sandbox_active():
        return (
            f"\n[ENVIRONNEMENT] Hôte : {p['os']} ({p['arch']}). "
            "Le code et les commandes shell s'exécutent dans une SANDBOX Docker LINUX isolée "
            "(shell bash, réseau coupé) : utilise des commandes Linux/bash, pas celles de l'hôte.\n"
        )
    return (
        f"\n[ENVIRONNEMENT] Le code et les commandes s'exécutent directement sur l'hôte "
        f"{p['os']} ({p['arch']}), shell : {p['shell']}. Adapte tes commandes à cet OS "
        f"(PowerShell sur Windows, bash/zsh sur Linux/macOS).\n"
    )
