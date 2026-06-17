"""Outils Proxmox VE (hyperviseur) — natifs via l'API REST, sans SDK.

- proxmox_status()                : état du cluster (nœuds, VM QEMU, conteneurs LXC).
- proxmox_vm_action(vmid, action) : démarrer / arrêter / redémarrer une VM ou un LXC (SENSIBLE
                                    → confirmation humaine requise / HITL).

Sécurité : net_guard (anti-SSRF) sur chaque URL ; lecture seule (viewer) bloque les actions ;
auth par jeton d'API ; TLS vérifiable (PROXMOX_VERIFY_TLS).
"""
import json

import requests

from core import proxmox
from tools.net_guard import is_blocked_url

_TIMEOUT = 12


def _guard(url: str):
    if is_blocked_url(url):
        return ("Erreur : l'hôte Proxmox est une adresse interne bloquée (anti-SSRF). "
                "Ajoute son hôte à NET_GUARD_ALLOW_HOSTS (Réglages) pour autoriser ce service de confiance.")
    return None


def _not_configured() -> str:
    return ("Proxmox non configuré. Va dans Réglages → Proxmox et renseigne l'URL "
            "(ex. https://192.168.1.20:8006), l'ID de jeton (USER@REALM!TOKENID) et le secret.")


def _get(path: str):
    """GET sur l'API Proxmox. Renvoie (data, None) ou (None, message_erreur)."""
    url = proxmox.api_base() + path
    err = _guard(url)
    if err:
        return None, err
    try:
        r = requests.get(url, headers=proxmox.auth_header(), verify=proxmox.verify_tls(), timeout=_TIMEOUT)
    except Exception as e:
        return None, f"Proxmox injoignable : {e}"
    if r.status_code == 401:
        return None, "Proxmox : jeton refusé (401). Vérifie l'ID de jeton et le secret."
    if r.status_code != 200:
        return None, f"Proxmox a répondu {r.status_code} : {r.text[:160]}"
    try:
        return r.json().get("data"), None
    except Exception:
        return None, "Proxmox : réponse illisible."


def proxmox_status() -> str:
    """
    Donne l'état du cluster Proxmox : nœuds (hôtes physiques) et toutes les VM (QEMU) et
    conteneurs (LXC) avec leur statut (running/stopped), CPU et mémoire. À utiliser pour
    « comment va le serveur / mes VM », avant une action, ou pour diagnostiquer.
    """
    if not proxmox.is_configured():
        return _not_configured()
    res, err = _get("/cluster/resources?type=vm")
    if err:
        return err
    nodes, _ = _get("/nodes")

    lines = []
    if isinstance(nodes, list) and nodes:
        lines.append("🖥️ Nœuds :")
        for n in nodes:
            st = n.get("status", "?")
            cpu = n.get("cpu")
            mem = n.get("mem")
            maxmem = n.get("maxmem")
            extra = ""
            if cpu is not None:
                extra += f" cpu {cpu*100:.0f}%"
            if mem and maxmem:
                extra += f" ram {mem/1e9:.1f}/{maxmem/1e9:.1f} Go"
            lines.append(f"  - {n.get('node')} : {st}{extra}")

    vms = [r for r in (res or []) if r.get("type") in ("qemu", "lxc")]
    if not vms:
        lines.append("Aucune VM/conteneur trouvé.")
    else:
        lines.append("📦 VM & conteneurs :")
        for v in sorted(vms, key=lambda x: (x.get("node", ""), x.get("vmid", 0))):
            kind = "VM" if v.get("type") == "qemu" else "LXC"
            ico = "🟢" if v.get("status") == "running" else "⚪"
            mem = v.get("mem"); maxmem = v.get("maxmem")
            ram = f" ram {mem/1e9:.1f}/{maxmem/1e9:.1f} Go" if (mem and maxmem) else ""
            lines.append(f"  {ico} [{kind} {v.get('vmid')}] {v.get('name','?')} "
                         f"@ {v.get('node','?')} — {v.get('status','?')}{ram}")
    return "\n".join(lines)


def _find_vm(vmid):
    res, err = _get("/cluster/resources?type=vm")
    if err:
        return None, err
    for v in (res or []):
        if str(v.get("vmid")) == str(vmid) and v.get("type") in ("qemu", "lxc"):
            return v, None
    return None, f"VM/conteneur {vmid} introuvable dans le cluster."


def proxmox_vm_action(vmid: str, action: str, user_confirmed: bool = False) -> str:
    """
    Démarre, arrête ou redémarre une VM (QEMU) ou un conteneur (LXC) Proxmox. ACTION SENSIBLE :
    nécessite la confirmation de l'utilisateur.

    Args:
        vmid (str): identifiant numérique de la VM/conteneur (ex. "100").
        action (str): "start", "stop", "shutdown" (extinction propre) ou "reboot".
        user_confirmed (bool): True une fois que l'utilisateur a approuvé.
    Returns:
        str: résultat de l'action.
    """
    if not proxmox.is_configured():
        return _not_configured()
    try:
        from core import projects
        if not projects.can_write():
            return "Erreur : accès en lecture seule — action Proxmox refusée."
    except Exception:
        pass
    action = (action or "").strip().lower()
    if action not in ("start", "stop", "shutdown", "reboot"):
        return "Erreur : action invalide. Utilise start, stop, shutdown ou reboot."

    vm, err = _find_vm(vmid)
    if err:
        return err
    node = vm.get("node")
    vtype = vm.get("type")  # qemu | lxc
    name = vm.get("name", "?")

    if not user_confirmed:
        return (f"⚠️ Action SENSIBLE : « {action} » sur [{vtype} {vmid}] {name} (nœud {node}). "
                "Demande confirmation à l'utilisateur, puis rappelle l'outil avec user_confirmed=True.")

    url = f"{proxmox.api_base()}/nodes/{node}/{vtype}/{vmid}/status/{action}"
    guard = _guard(url)
    if guard:
        return guard
    try:
        r = requests.post(url, headers=proxmox.auth_header(), verify=proxmox.verify_tls(), timeout=_TIMEOUT)
    except Exception as e:
        return f"Proxmox injoignable : {e}"
    if r.status_code in (200, 201):
        return f"✅ Action « {action} » lancée sur [{vtype} {vmid}] {name} (nœud {node})."
    if r.status_code == 401:
        return "Proxmox : jeton refusé (401) ou droits insuffisants pour cette action."
    return f"Erreur Proxmox ({r.status_code}) : {r.text[:200]}"


proxmox_vm_action._requires_approval = True
