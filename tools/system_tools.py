import os
import subprocess
import re

# Gardes-fous renforcés : Bloque l'obfuscation, les reverse shells, les téléchargements suspects et les commandes destructrices
BLACKLIST_PATTERNS = [
    r"\brm\b\s+-[rf]*\s+/",         # rm -rf / (destruction racine)
    r"\brm\b\s+-[rf]*\s+~",         # rm -rf ~ (destruction home)
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"\bdd\b\s+",                   # dd (destruction de disques)
    r"\bmkfs\b",                    # formatage de disques
    r"\bchmod\b\s+-[R]*\s+777\s+/", # chmod 777 racine
    r":\(\){\s*:\|:&\s*};:",        # Fork bomb
    r"\bnc\b|\bnetcat\b|\bsocat\b",  # Interdiction des reverse shells classiques
    r"/dev/tcp|/dev/udp",           # Interdiction des sockets bash natifs (reverse shell)
    r"\bbase64\b|\bxxd\b|\bhexdump\b", # Bloquer l'obfuscation de commandes malveillantes
    r"\bsh\b\s+|\bbash\b\s+|\bzsh\b\s+|\bdash\b\s+", # Bloquer l'exécution de sous-interprètes imbriqués pour contourner les filtres
    r"\bcurl\b|\bwget\b",           # Bloquer le téléchargement de charges utiles (payloads) malveillantes de l'extérieur
]


def check_command_blacklist(command: str):
    """Renvoie un message de rejet si la commande contient un motif interdit,
    sinon None. Couche de filtrage partagée par l'outil bash et l'endpoint coder."""
    for pattern in BLACKLIST_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return (
                f"Sécurité : Commande refusée. La commande contient des motifs interdits "
                f"({pattern}) pour prévenir les jailbreaks, l'obfuscation, les reverse shells "
                f"ou la destruction système."
            )
    return None


def _is_private_host(host: str) -> bool:
    """Vrai si l'hôte est sur un réseau LOCAL de confiance (IP privée RFC1918 / loopback /
    lien-local, ou nom .local/.lan/.home/.internal). Sert au TOFU SSH : sur le LAN on fait
    confiance au premier raccordement (comme le client ssh), pas sur Internet."""
    import ipaddress
    import socket
    h = (host or "").strip()
    if not h:
        return False
    name = h.lower().rstrip(".")
    if name in ("localhost",) or name.endswith((".local", ".lan", ".home", ".internal")):
        return True
    # IP littérale ?
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    # Nom d'hôte : on résout en IP (sans bloquer longtemps) et on teste.
    try:
        socket.setdefaulttimeout(2)
        ip = ipaddress.ip_address(socket.gethostbyname(h))
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except Exception:
        return False
    finally:
        socket.setdefaulttimeout(None)


def run_ssh_command(command: str, host_id: str = None) -> tuple[str, str, int]:
    """
    Exécute une commande de manière sécurisée sur une machine distante via SSH (Paramiko).

    host_id : identifiant d'un hôte du registre multi-hôtes (admin). None = hôte actif du
    contexte (console) puis, à défaut, l'hôte unique du .env (rétro-compatible).
    """
    # GARDE-FOUS (défense en profondeur) : ce point d'entrée est appelé par l'outil agent
    # `execute_bash_command` (déjà filtré) MAIS AUSSI EN DIRECT par la console codeur
    # (bash `$ …`). On applique donc ici les mêmes protections, pour qu'aucun chemin ne
    # contourne le filtrage sur l'hôte distant.
    try:
        from core import projects
        if not projects.can_write():
            return "", "Erreur : projet en LECTURE SEULE (rôle lecteur) — commande SSH refusée.", 1
    except Exception:
        pass
    rejection = check_command_blacklist(command)
    if rejection:
        return "", rejection, 1
    # sudo/su sur l'hôte distant : interdit sauf politique explicite (élévation de privilèges).
    if re.search(r"\bsudo\b|\bsu\b", command, re.IGNORECASE) and \
            os.getenv("ALLOW_SUDO_ON_VPS", "False").lower() not in ("true", "1", "yes"):
        return "", ("Sécurité : 'sudo'/'su' est désactivé (élévation de privilèges). "
                    "Définis ALLOW_SUDO_ON_VPS=true pour l'autoriser."), 1

    import paramiko
    import shlex

    # Résolution de l'HÔTE : registre multi-hôtes (admin) si fourni, sinon config .env (hôte
    # unique historique). Voir ssh_hosts.resolve() — fusionne registre + défauts .env.
    from tools import ssh_hosts
    cfg = ssh_hosts.resolve(host_id)
    host = cfg.get("host")
    port = int(cfg.get("port") or 22)
    username = cfg.get("username")
    password = cfg.get("password")
    key_path = cfg.get("key_path")
    if not host:
        return "", "Erreur : aucun hôte SSH configuré (SSH_HOST ou registre d'hôtes).", 1

    ssh = paramiko.SSHClient()
    # Vérification des clés d'hôte connues (anti-MITM). On charge le known_hosts système
    # puis, si fourni, un fichier dédié (par hôte ou via SSH_KNOWN_HOSTS).
    ssh.load_system_host_keys()
    known_hosts = cfg.get("known_hosts")
    if known_hosts:
        expanded_known = os.path.expanduser(known_hosts)
        if os.path.exists(expanded_known):
            try:
                ssh.load_host_keys(expanded_known)
            except Exception:
                pass
    # Politique de clé d'hôte. Par défaut on REFUSE un hôte inconnu (anti-MITM). MAIS sur un
    # réseau LOCAL de confiance (IP privée RFC1918 / .local), on applique le TOFU « trust on
    # first use » comme le client ssh classique (premier raccordement d'un homelab) : sinon
    # l'assistant ne peut JAMAIS joindre un NAS/serveur LAN sans pré-amorcer known_hosts à la
    # main. Les hôtes PUBLICS restent en RejectPolicy sauf auto_add explicite.
    _auto_optin = str(cfg.get("auto_add") or "").lower() in ("true", "1", "yes")
    _is_lan = _is_private_host(host)
    if _auto_optin or _is_lan:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507 — opt-in/LAN de confiance
    else:
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    
    try:
        # 1. Connexion SSH
        if key_path:
            expanded_key = os.path.expanduser(key_path)
            try:
                key = paramiko.RSAKey.from_private_key_file(expanded_key)
            except Exception:
                try:
                    key = paramiko.Ed25519Key.from_private_key_file(expanded_key)
                except Exception as e:
                    return "", f"Erreur chargement clé SSH private key ({expanded_key}) : {str(e)}", 1
            ssh.connect(host, port=port, username=username, pkey=key, timeout=10)
        elif password:
            ssh.connect(host, port=port, username=username, password=password, timeout=10)
        else:
            ssh.connect(host, port=port, username=username, timeout=10)
            
        # 2. Gestion du dossier distant de travail (par hôte ; repli sur SSH_REMOTE_CWD)
        remote_cwd = cfg.get("remote_cwd")
        if remote_cwd:
            # remote_cwd est échappé ; `command` reste une commande shell complète.
            full_command = f"cd {shlex.quote(remote_cwd)} && {command}"
        else:
            full_command = command
            
        # 3. Exécution de la commande (outil run_ssh_command : SENSIBLE/HITL ; gardes blacklist
        # commandes, sudo, lecture seule appliquées en amont ; remote_cwd échappé via shlex.quote).
        stdin, stdout, stderr = ssh.exec_command(full_command, timeout=15)  # nosec B601
        stdout_str = stdout.read().decode('utf-8', errors='ignore')
        stderr_str = stderr.read().decode('utf-8', errors='ignore')
        return_code = stdout.channel.recv_exit_status()
        
        return stdout_str, stderr_str, return_code
    except Exception as e:
        msg = str(e)
        if "not found in known_hosts" in msg or "not found" in msg.lower():
            return "", (f"Clé d'hôte SSH inconnue pour {host} (hôte non vérifié). "
                        "C'est un hôte public : active l'auto-ajout de la clé (TOFU) pour cet "
                        "hôte dans Réglages → SSH (auto_add), ou ajoute-le à known_hosts. "
                        "Les hôtes du réseau local sont acceptés automatiquement."), 1
        return "", f"Erreur de connexion/exécution SSH sur {host} : {msg}", 1
    finally:
        ssh.close()

def list_ssh_hosts() -> str:
    """Liste les SERVEURS SSH enregistrés (VM / machines distantes) que tu peux piloter.

    Appelle cet outil quand l'utilisateur te demande d'agir sur une machine par son nom
    (ex. « va sur Immich », « redémarre Home Assistant ») afin de connaître le LABEL exact à
    passer ensuite au paramètre `host` de execute_bash_command — ex.
    execute_bash_command("docker restart immich_server", host="Immich").

    Returns:
        str: la liste des hôtes (label — utilisateur@hôte:port), ou un message si aucun.
    """
    from tools import ssh_hosts
    hosts = ssh_hosts.list_hosts(mask=True)
    if not hosts:
        return "Aucun serveur SSH enregistré. (Réglages → SSH pour en ajouter.)"
    lines = []
    for h in hosts:
        label = h.get("label") or h.get("host") or h.get("id")
        user = h.get("username") or ""
        tgt = f"{user + '@' if user else ''}{h.get('host', '')}:{h.get('port', 22)}"
        lines.append(f"- {label}  ({tgt})")
    return ("Serveurs SSH disponibles (utilise le LABEL comme paramètre `host` de "
            "execute_bash_command) :\n" + "\n".join(lines))


def reset_sandbox() -> str:
    """
    Réinitialise l'environnement d'exécution sandbox (conteneur Docker du codeur). Utile si un
    script a cassé l'environnement, saturé le disque, ou laissé un processus en boucle.

    Les fichiers du workspace (montés depuis l'hôte) sont CONSERVÉS ; seuls les paquets installés
    DANS le conteneur et les processus en cours sont perdus. Un environnement propre est recréé à
    la commande suivante.

    Returns:
        str: Message de confirmation.
    """
    try:
        from core import projects
        if not projects.can_write():
            return "Erreur : projet en LECTURE SEULE — réinitialisation refusée."
    except Exception:
        pass
    try:
        from tools import dev_container, sandbox_runner
        if not sandbox_runner.docker_available():
            return "Pas de sandbox Docker (exécution locale directe) — rien à réinitialiser."
        key = dev_container.active_key()
        if key:
            ok = dev_container.stop(key)
            return ("✅ Sandbox réinitialisée : un environnement propre sera recréé à la prochaine "
                    "commande (les fichiers du workspace sont conservés)." if ok else
                    "Aucun conteneur persistant à réinitialiser (déjà propre).")
        present = dev_container.list_containers()
        return ("La sandbox est éphémère (un conteneur jetable par commande) — rien à réinitialiser. "
                + (f"Conteneurs dev présents : {', '.join(present)}." if present else ""))
    except Exception as e:
        return f"Erreur lors de la réinitialisation de la sandbox : {e}"


def self_update(user_confirmed: bool = False) -> str:
    """
    Met Athena à jour : récupère le code (git pull), met à jour les dépendances et redémarre le
    service. Le script tourne en arrière-plan DÉTACHÉ, donc Athena redémarre juste après (sans se
    couper en pleine commande). ACTION SENSIBLE → confirmation utilisateur requise.

    NE PAS lancer update.sh via execute_bash_command (le redémarrage tuerait Athena en plein run) —
    utiliser CET outil, prévu pour survivre au redémarrage.

    Args:
        user_confirmed (bool): True une fois l'utilisateur d'accord.
    Returns:
        str: message de confirmation (Athena redémarre ensuite).
    """
    if not user_confirmed:
        return ("⚠️ Mise à jour d'Athena (git pull + dépendances + REDÉMARRAGE). Demande "
                "confirmation à l'utilisateur, puis rappelle l'outil avec user_confirmed=True.")
    import subprocess
    from core.platform_info import get_platform_info
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        if get_platform_info().get("is_windows"):
            script = os.path.join(root_dir, "update.ps1")
            kwargs = {}
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", script],
                             cwd=root_dir, start_new_session=True, **kwargs)
        else:
            script = os.path.join(root_dir, "update.sh")
            log_f = open(os.path.join(root_dir, "update.log"), "w", encoding="utf-8")
            subprocess.Popen(["bash", script], cwd=root_dir, start_new_session=True,
                             preexec_fn=os.setsid, stdout=log_f, stderr=subprocess.STDOUT)
        return ("🔄 Mise à jour lancée (git pull + dépendances + redémarrage), journal dans update.log. "
                "Je vais redémarrer dans un instant — reparle-moi après pour vérifier la nouvelle version.")
    except Exception as e:
        return f"Erreur lors du lancement de la mise à jour : {e}"


self_update._requires_approval = True


def execute_bash_command(command: str, user_confirmed: bool = False, host: str = "") -> str:
    """
    Exécute une commande système Bash sécurisée (locale, ou distante via SSH).

    Les commandes d'administration (sudo, su), de téléchargement externe, d'obfuscation
    et de création de reverse-shells sont strictement bloquées et surveillées pour la sécurité.

    Args:
        command (str): La commande Bash complète à exécuter.
        user_confirmed (bool): Indique si l'utilisateur a approuvé la commande.
        host (str): Nom/label d'un SERVEUR SSH du registre pour exécuter À DISTANCE (ex: 'prod'). Vide = exécution locale (ou hôte .env unique s'il est configuré).

    Returns:
        str: La sortie de la console.
    """
    # 0. Projet en LECTURE SEULE (membre « viewer ») : aucune commande (elle pourrait
    #    écrire dans le projet partagé).
    try:
        from core import projects
        if not projects.can_write():
            return "Erreur : projet en LECTURE SEULE (rôle lecteur) — exécution de commandes refusée."
    except Exception:
        pass

    # 1. Application des gardes-fous absolus renforcés (couche partagée)
    rejection = check_command_blacklist(command)
    if rejection:
        return rejection

    # 2. Gestion stricte des privilèges root (sudo/su) via variables d'environnement
    requires_sudo = bool(re.search(r"\bsudo\b|\bsu\b", command, re.IGNORECASE))
    if requires_sudo:
        # Lire la politique de sécurité du .env (par défaut : interdiction absolue de sudo sur VPS)
        allow_sudo_policy = os.getenv("ALLOW_SUDO_ON_VPS", "False").lower() in ("true", "1", "yes")
        if not allow_sudo_policy:
            return "Sécurité : Commande refusée. L'utilisation de 'sudo' ou 'su' est strictement désactivée sur ce serveur pour prévenir les élévations de privilèges."
            
        if not user_confirmed:
            return (
                f"Sécurité : La commande '{command}' nécessite des droits d'administration (sudo/su).\n"
                "Tu dois OBLIGATOIREMENT interrompre ton exécution et demander explicitement "
                "la confirmation à l'utilisateur dans ton message texte en lui affichant la commande exacte.\n"
                "Une fois que l'utilisateur t'a répondu par l'affirmative, rappelle cet outil avec "
                "le paramètre 'user_confirmed=True'."
            )
            
    # 3. Routage SSH : hôte nommé du registre (param `host`), hôte actif du contexte, ou
    #    hôte unique du .env. Sinon, exécution locale (étape 4).
    from tools import ssh_hosts
    host_id = None
    if host and host.strip():
        host_id = ssh_hosts.find(host)
        if not host_id:
            return f"Erreur : serveur SSH « {host} » introuvable. Disponibles : {ssh_hosts.labels()}."
    if host_id or ssh_hosts.active_host() or os.getenv("SSH_HOST"):
        stdout, stderr, rc = run_ssh_command(command, host_id=host_id)
        output = ""
        if stdout:
            output += f"--- SORTIE DISTANTE SSH (stdout) ---\n{stdout}\n"
        if stderr:
            output += f"--- ERREUR DISTANTE SSH (stderr) ---\n{stderr}\n"
        if not output:
            output = "Commande SSH exécutée avec succès (aucune sortie)."
        return output
        
    # 4. Exécution locale : isolée en sandbox Docker si possible, sinon repli local.
    from tools import sandbox_runner
    try:
        if sandbox_runner.sandbox_mode() != "off" and sandbox_runner.docker_available():
            stdout, stderr, _rc = sandbox_runner.run_bash(command, timeout=15)
        else:
            # Repli local : choix du shell selon l'OS hôte (portabilité Win/Mac/Linux).
            import platform
            try:
                from core.state import get_workspace_dir
                cwd = get_workspace_dir()
            except Exception:
                cwd = os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd())
            if platform.system() == "Windows":
                argv = ["powershell", "-NoProfile", "-Command", command]
            else:
                shell = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"
                argv = [shell, "-c", command]
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=cwd
            )
            stdout, stderr = result.stdout, result.stderr

        output = ""
        if stdout:
            output += f"--- SORTIE (stdout) ---\n{stdout}\n"
        if stderr:
            output += f"--- ERREUR (stderr) ---\n{stderr}\n"

        if not output:
            output = "Commande exécutée avec succès (aucune sortie)."

        return output
    except subprocess.TimeoutExpired:
        return "Erreur : Temps d'exécution de la commande dépassé (Timeout de 15 secondes)."
    except Exception as e:
        return f"Erreur lors de l'exécution de la commande : {str(e)}"
