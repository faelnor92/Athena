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

def run_ssh_command(command: str) -> tuple[str, str, int]:
    """
    Exécute une commande de manière sécurisée sur une machine distante via SSH (Paramiko).
    """
    import paramiko
    import shlex

    host = os.getenv("SSH_HOST")
    port = int(os.getenv("SSH_PORT", "22"))
    username = os.getenv("SSH_USERNAME")
    password = os.getenv("SSH_PASSWORD")
    key_path = os.getenv("SSH_KEY_PATH")

    ssh = paramiko.SSHClient()
    # Vérification des clés d'hôte connues (anti-MITM). On charge le known_hosts
    # système puis, si fourni, un fichier dédié via SSH_KNOWN_HOSTS.
    ssh.load_system_host_keys()
    known_hosts = os.getenv("SSH_KNOWN_HOSTS")
    if known_hosts:
        expanded_known = os.path.expanduser(known_hosts)
        if os.path.exists(expanded_known):
            try:
                ssh.load_host_keys(expanded_known)
            except Exception:
                pass
    # Politique stricte par défaut : on REFUSE un hôte inconnu plutôt que de
    # l'ajouter aveuglément (AutoAddPolicy était vulnérable au MITM).
    # Opt-in explicite et documenté pour le premier raccordement.
    if os.getenv("SSH_AUTO_ADD_HOST_KEYS", "False").lower() in ("true", "1", "yes"):
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
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
            
        # 2. Gestion du dossier distant de travail
        remote_cwd = os.getenv("SSH_REMOTE_CWD")
        if remote_cwd:
            # remote_cwd est échappé ; `command` reste une commande shell complète.
            full_command = f"cd {shlex.quote(remote_cwd)} && {command}"
        else:
            full_command = command
            
        # 3. Exécution de la commande
        stdin, stdout, stderr = ssh.exec_command(full_command, timeout=15)
        stdout_str = stdout.read().decode('utf-8', errors='ignore')
        stderr_str = stderr.read().decode('utf-8', errors='ignore')
        return_code = stdout.channel.recv_exit_status()
        
        return stdout_str, stderr_str, return_code
    except Exception as e:
        return "", f"Erreur de connexion/exécution SSH sur {host} : {str(e)}", 1
    finally:
        ssh.close()

def execute_bash_command(command: str, user_confirmed: bool = False) -> str:
    """
    Exécute une commande système Bash sécurisée (locale ou distante via SSH si configuré).
    
    Les commandes d'administration (sudo, su), de téléchargement externe, d'obfuscation
    et de création de reverse-shells sont strictement bloquées et surveillées pour la sécurité.
    
    Args:
        command (str): La commande Bash complète à exécuter.
        user_confirmed (bool): Indique si l'utilisateur a approuvé la commande.
        
    Returns:
        str: La sortie de la console.
    """
    # 1. Application des gardes-fous absolus renforcés
    for pattern in BLACKLIST_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Sécurité : Commande refusée. La commande contient des motifs interdits ({pattern}) pour prévenir les jailbreaks, l'obfuscation, les reverse shells ou la destruction système."
            
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
            
    # 3. Routage SSH si SSH_HOST est configuré
    if os.getenv("SSH_HOST"):
        stdout, stderr, rc = run_ssh_command(command)
        output = ""
        if stdout:
            output += f"--- SORTIE DISTANTE SSH (stdout) ---\n{stdout}\n"
        if stderr:
            output += f"--- ERREUR DISTANTE SSH (stderr) ---\n{stderr}\n"
        if not output:
            output = "Commande SSH exécutée avec succès (aucune sortie)."
        return output
        
    # 4. Exécution locale classique par défaut
    try:
        cwd = os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd())
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=cwd
        )
        
        output = ""
        if result.stdout:
            output += f"--- SORTIE (stdout) ---\n{result.stdout}\n"
        if result.stderr:
            output += f"--- ERREUR (stderr) ---\n{result.stderr}\n"
            
        if not output:
            output = "Commande exécutée avec succès (aucune sortie)."
            
        return output
    except subprocess.TimeoutExpired:
        return "Erreur : Temps d'exécution de la commande dépassé (Timeout de 15 secondes)."
    except Exception as e:
        return f"Erreur lors de l'exécution de la commande : {str(e)}"
