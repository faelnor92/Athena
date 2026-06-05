#!/usr/bin/env python3
"""Assistant d'installation interactif de Athena (cross-platform).

Appelé par install.sh / install.ps1 APRÈS la création du venv et l'installation du
cœur (requirements.txt). Il propose :
  1. d'installer (ou non) les composants OPTIONNELS (voix, transcription de réunions) ;
  2. de configurer l'essentiel du .env (fournisseur LLM, mot de passe admin).

Objectif : installation quasi clef-en-main pour des utilisateurs non initiés. Tout
l'optionnel est désactivé par défaut (on opte-in) → un simple Entrée donne une install
minimale fonctionnelle. Lancer avec --auto pour tout accepter par défaut (sans question).

Les paquets s'installent avec le Python courant (sys.executable) : appelé via le python
du venv, ils vont donc dans le venv.
"""
import os
import sys
import subprocess
import shutil

C = {"cyan": "\033[0;36m", "green": "\033[0;32m", "yellow": "\033[0;33m",
     "red": "\033[0;31m", "bold": "\033[1m", "nc": "\033[0m"}
if os.name == "nt" or not sys.stdout.isatty():
    C = {k: "" for k in C}  # pas de couleurs hors TTY/Windows

AUTO = "--auto" in sys.argv
INTERACTIVE = sys.stdin.isatty() and not AUTO


def say(msg, color="nc"):
    print(f"{C.get(color,'')}{msg}{C['nc']}")


def ask_yes_no(question, default=False):
    """Renvoie un booléen. En mode non interactif : `default` (ou True si --auto)."""
    if AUTO:
        return True
    if not INTERACTIVE:
        return default
    suffix = " [O/n] " if default else " [o/N] "
    try:
        ans = input(f"{C['cyan']}{question}{C['nc']}{suffix}").strip().lower()
    except EOFError:
        return default
    if not ans:
        return default
    return ans in ("o", "oui", "y", "yes")


def ask_text(question, default=""):
    if not INTERACTIVE:
        return default
    try:
        ans = input(f"{C['cyan']}{question}{C['nc']} ").strip()
    except EOFError:
        return default
    return ans or default


def pip_install(*args):
    cmd = [sys.executable, "-m", "pip", "install", *args]
    say(f"  → {' '.join(cmd[3:])}", "yellow")
    return subprocess.call(cmd) == 0


# --- .env --------------------------------------------------------------------
def _read_env_lines():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            return f.readlines()
    return []


def set_env_var(key, value):
    """Crée/met à jour KEY=value dans .env en préservant le reste."""
    lines = _read_env_lines()
    out, found = [], False
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"#{key}="):
            out.append(f"{key}={value}\n")
            found = True
        else:
            out.append(line)
    if not found:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key}={value}\n")
    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(out)


def ensure_env_file():
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", ".env")
            say("✔ .env créé à partir de .env.example.", "green")
        else:
            open(".env", "a").close()


# --- Étapes ------------------------------------------------------------------
def step_optional_components():
    say("\n— Composants optionnels —", "bold")
    say("Tout est désactivé par défaut : réponds 'o' uniquement pour ce dont tu as besoin.\n")

    # 1. Assistant vocal (STT/TTS/wake word + satellites ESP32)
    if ask_yes_no("Installer l'assistant VOCAL (micro/voix, wake word, satellites ESP32) ?", default=False):
        if os.path.exists("requirements-voice.txt"):
            ok = pip_install("-r", "requirements-voice.txt")
            say("✔ Pipeline vocal installé." if ok else "⚠ Échec d'installation du vocal.",
                "green" if ok else "red")
            
            if ok and ask_yes_no("  → Installer le serveur TTS 'Kokoro' via Docker (voix expressives ultra-rapides) ?", default=False):
                if shutil.which("docker"):
                    say("    Téléchargement et lancement de Kokoro-FastAPI (port 8880)...", "cyan")
                    # --restart unless-stopped pour qu'il survive aux redémarrages
                    cmd = ["docker", "run", "-d", "-p", "8880:8880", "--restart", "unless-stopped", "--name", "kokoro-tts", "ghcr.io/remsky/kokoro-fastapi-cpu:latest"]
                    if subprocess.call(cmd) == 0:
                        say("    ✔ Serveur Kokoro lancé en arrière-plan.", "green")
                        set_env_var("VOICE_TTS_HTTP_URL", "http://127.0.0.1:8880/v1/audio/speech")
                        set_env_var("VOICE_TTS_ENGINE", "http")
                    else:
                        say("    ⚠ Erreur lors du lancement Docker. Le conteneur existe peut-être déjà.", "yellow")
                else:
                    say("    ⚠ Docker n'est pas installé. Installation ignorée.", "red")
            else:
                say("  Note : tu pourras configurer la synthèse vocale plus tard dans ton .env (VOICE_TTS_ENGINE).", "yellow")
        else:
            say("⚠ requirements-voice.txt introuvable.", "red")

    # 2. Transcription de réunions (Whisper, très lourd)
    if ask_yes_no("Installer la TRANSCRIPTION de réunions (OpenAI Whisper, ~2 Go, lourd) ?", default=False):
        ok = pip_install("openai-whisper")
        say("✔ Whisper installé." if ok else "⚠ Échec d'installation de Whisper.",
            "green" if ok else "red")

    # 3bis. OBSERVABILITÉ LLM (optionnelle) : traçage OpenInference → OpenTelemetry → Phoenix.
    if ask_yes_no("Installer l'OBSERVABILITÉ LLM (traçage des appels/agents → Phoenix) ?", default=False):
        if os.path.exists("requirements-observability.txt"):
            ok = pip_install("-r", "requirements-observability.txt")
            if ok:
                set_env_var("OPENINFERENCE_ENABLED", "true")
                set_env_var("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006/v1/traces")
                say("✔ Observabilité installée et activée (OPENINFERENCE_ENABLED=true).", "green")
                # Collecteur Phoenix via Docker (comme Kokoro) : optionnel.
                if ask_yes_no("  → Lancer le collecteur Phoenix via Docker (UI sur http://localhost:6006) ?", default=False):
                    if shutil.which("docker"):
                        cmd = ["docker", "run", "-d", "-p", "6006:6006", "-p", "4317:4317",
                               "--restart", "unless-stopped", "--name", "phoenix",
                               "arizephoenix/phoenix:latest"]
                        if subprocess.call(cmd) == 0:
                            say("    ✔ Phoenix lancé (UI : http://localhost:6006).", "green")
                        else:
                            say("    ⚠ Erreur Docker (le conteneur 'phoenix' existe peut-être déjà).", "yellow")
                    else:
                        say("    ⚠ Docker non installé — lance un collecteur Phoenix toi-même.", "red")
            else:
                say("⚠ Échec d'installation de l'observabilité.", "red")
        else:
            say("⚠ requirements-observability.txt introuvable.", "red")

    # 3. Docker (sandbox) — non installable via pip, on détecte/conseille.
    if shutil.which("docker"):
        say("✔ Docker détecté : l'exécution de code sera isolée (sandbox).", "green")
    else:
        say("ℹ Docker non détecté. Sans lui, l'exécution de code n'est PAS isolée.", "yellow")
        say("  Installe Docker (https://docs.docker.com/get-docker/) pour activer le sandbox,", "yellow")
        say("  ou mets SANDBOX_MODE=off dans .env pour exécuter en local (non isolé).", "yellow")


def step_env_essentials():
    say("\n— Configuration essentielle (.env) —", "bold")
    ensure_env_file()
    if not INTERACTIVE:
        say("Mode non interactif : .env laissé tel quel (édite-le manuellement).", "yellow")
        return

    say("Quel fournisseur de modèle (LLM) veux-tu utiliser ?")
    say("  1) OpenAI (clé API)")
    say("  2) Endpoint personnalisé compatible OpenAI (vLLM, LM Studio, Open WebUI…)")
    say("  3) Ollama local (gratuit)")
    say("  4) Plus tard / je configure moi-même")
    choice = ask_text("Ton choix [1-4] :", default="4")

    if choice == "1":
        key = ask_text("Clé API OpenAI (sk-…) :")
        if key:
            set_env_var("OPENAI_API_KEY", key)
            say("✔ Clé OpenAI enregistrée.", "green")
    elif choice == "2":
        base = ask_text("URL de l'endpoint (ex: https://mon-serveur/v1) :")
        key = ask_text("Clé API (laisse vide si aucune) :", default="placeholder-key")
        if base:
            set_env_var("CUSTOM_LLM_API_BASE", base)
            set_env_var("CUSTOM_LLM_API_KEY", key or "placeholder-key")
            say("✔ Endpoint personnalisé enregistré.", "green")
    elif choice == "3":
        set_env_var("OLLAMA_API_BASE", ask_text("URL Ollama :", default="http://localhost:11434"))
        say("✔ Ollama configuré. Pense à `ollama pull <modèle>` (ex: qwen2.5-coder:1.5b).", "green")

    # Mot de passe admin (protège l'UI + les outils sensibles).
    if ask_yes_no("Protéger l'accès par un mot de passe admin ?", default=False):
        pwd = ask_text("Mot de passe admin :")
        if pwd:
            set_env_var("ADMIN_PASSWORD", pwd)
            say("✔ Mot de passe admin défini.", "green")


def step_starting_team():
    """Par défaut, l'app démarre avec l'orchestrateur SEUL ; l'utilisateur ajoute ses
    agents ensuite (UI / création par Athena). Option : démarrer avec l'équipe d'exemple."""
    if os.path.exists("agents.yaml"):
        return  # config déjà présente : on n'y touche pas
    say("\n— Agents au démarrage —", "bold")
    say("Par défaut, l'application démarre avec l'orchestrateur SEUL ; tu ajoutes tes")
    say("propres agents ensuite (bouton « Créer un agent » ou en le demandant à Athena).")
    if os.path.exists("agents.example.yaml") and ask_yes_no(
            "Préférer démarrer avec une ÉQUIPE d'exemple (Codeur, Auteur, Traducteur…) ?", default=False):
        shutil.copy("agents.example.yaml", "agents.yaml")
        say("✔ Équipe d'exemple installée (modifiable dans Réglages → Agents).", "green")
    else:
        say("→ Démarrage avec l'orchestrateur seul.", "green")


def main():
    say(f"\n{C['bold']}🔧 Assistant de configuration Athena{C['nc']}")
    if AUTO:
        say("(mode --auto : tout l'optionnel est installé sans question)", "yellow")
    elif not INTERACTIVE:
        say("(mode non interactif : install minimale, .env inchangé)", "yellow")
    try:
        step_optional_components()
        step_starting_team()
        step_env_essentials()
    except KeyboardInterrupt:
        say("\nConfiguration interrompue — tu pourras relancer `python setup_wizard.py`.", "yellow")
        return
    say("\n✅ Configuration terminée.", "green")


if __name__ == "__main__":
    main()
