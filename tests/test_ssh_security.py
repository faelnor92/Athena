"""Sécurité SSH : garde-fous (blacklist, sudo, lecture seule) appliqués DANS
run_ssh_command (donc même pour la console codeur qui l'appelle en direct), et registre
multi-hôtes (résolution + repli .env)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ws = tempfile.mkdtemp(prefix="athena_ssh_")
os.environ["ACTIVE_WORKSPACE_DIR"] = _ws
os.environ["STATE_DB_PATH"] = os.path.join(_ws, "state.sqlite3")
for _k in ("SSH_HOST", "SSH_USERNAME", "SSH_PORT", "ALLOW_SUDO_ON_VPS"):
    os.environ.pop(_k, None)

from tools.system_tools import run_ssh_command  # noqa: E402
from tools import ssh_hosts  # noqa: E402


def test_blacklist_blocks_before_connect():
    out, err, rc = run_ssh_command("rm -rf /")
    assert rc == 1 and "refus" in err.lower()      # bloqué AVANT toute connexion


def test_sudo_blocked_by_default():
    out, err, rc = run_ssh_command("sudo apt-get update")
    assert rc == 1 and "sudo" in err.lower()


def test_no_host_configured_is_graceful():
    # Commande propre mais aucun hôte (ni env ni registre) → erreur claire, pas de crash.
    out, err, rc = run_ssh_command("ls -la")
    assert rc == 1 and "hôte SSH" in err


def test_registry_resolve_and_remove():
    e = ssh_hosts.add_host("Prod", "10.0.0.9", username="root", key_path="~/.ssh/id_ed")
    cfg = ssh_hosts.resolve(e["id"])
    assert cfg["host"] == "10.0.0.9" and cfg["username"] == "root"
    # masquage du secret dans la liste
    assert all(h.get("password") in ("", "***") for h in ssh_hosts.list_hosts())
    assert ssh_hosts.remove_host(e["id"]) is True


def test_active_host_contextvar():
    e = ssh_hosts.add_host("Bkp", "10.0.0.10", username="ops")
    tok = ssh_hosts.set_active(e["id"])
    try:
        assert ssh_hosts.resolve()["host"] == "10.0.0.10"   # résolu via l'hôte actif
    finally:
        ssh_hosts.reset_active(tok)
        ssh_hosts.remove_host(e["id"])


def test_per_host_cwd_independent():
    a = ssh_hosts.add_host("A", "10.0.0.1", username="root")
    b = ssh_hosts.add_host("B", "10.0.0.2", username="root")
    ssh_hosts.set_cwd("/var/www", a["id"])
    ssh_hosts.set_cwd("/etc", b["id"])
    assert ssh_hosts.get_cwd(a["id"]) == "/var/www"
    assert ssh_hosts.get_cwd(b["id"]) == "/etc"             # cd indépendant par serveur
    assert ssh_hosts.resolve(a["id"])["remote_cwd"] == "/var/www"   # prime sur la config
    assert ssh_hosts.resolve(b["id"])["remote_cwd"] == "/etc"
    ssh_hosts.remove_host(a["id"]); ssh_hosts.remove_host(b["id"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests sécurité SSH passent.")
