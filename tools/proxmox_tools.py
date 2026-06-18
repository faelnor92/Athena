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


def _go(n):
    try:
        return f"{n/1e9:.1f}"
    except Exception:
        return "?"


def proxmox_status() -> str:
    """
    Donne l'état du cluster Proxmox : nœuds (hôtes physiques), VM (QEMU) et conteneurs (LXC)
    avec statut (running/stopped) et leur charge — **CPU, RAM et disque** — ainsi que l'espace
    des stockages (datastores). À utiliser pour « comment vont mes VM / le serveur », surveiller
    la charge, ou avant une action.

    NB : pour une VM QEMU, l'usage disque RÉEL est récupéré via l'agent invité (qemu-guest-agent)
    s'il est installé/activé ; sinon c'est la taille provisionnée (« alloué ») qui s'affiche. Les
    conteneurs LXC montrent toujours l'usage réel. CPU/RAM sont toujours disponibles.
    """
    if not proxmox.is_configured():
        return _not_configured()
    res, err = _get("/cluster/resources")          # tout : node, qemu, lxc, storage
    if err:
        return err
    res = res or []
    nodes = [r for r in res if r.get("type") == "node"]
    vms = [r for r in res if r.get("type") in ("qemu", "lxc")]
    stores = [r for r in res if r.get("type") == "storage"]

    lines = []
    if nodes:
        lines.append("🖥️ Nœuds :")
        for n in sorted(nodes, key=lambda x: x.get("node", "")):
            cpu = n.get("cpu"); mem = n.get("mem"); maxmem = n.get("maxmem")
            dsk = n.get("disk"); maxdsk = n.get("maxdisk")
            parts = [n.get("status", "?")]
            if cpu is not None:
                parts.append(f"cpu {cpu*100:.0f}%")
            if mem and maxmem:
                parts.append(f"ram {_go(mem)}/{_go(maxmem)} Go ({mem/maxmem*100:.0f}%)")
            if dsk and maxdsk:
                parts.append(f"disque root {_go(dsk)}/{_go(maxdsk)} Go ({dsk/maxdsk*100:.0f}%)")
            lines.append(f"  - {n.get('node')} : " + " · ".join(parts))

    if not vms:
        lines.append("Aucune VM/conteneur trouvé.")
    else:
        lines.append("📦 VM & conteneurs :")
        for v in sorted(vms, key=lambda x: (x.get("node", ""), x.get("vmid", 0))):
            kind = "VM" if v.get("type") == "qemu" else "LXC"
            running = v.get("status") == "running"
            ico = "🟢" if running else "⚪"
            head = f"  {ico} [{kind} {v.get('vmid')}] {v.get('name','?')} @ {v.get('node','?')} — {v.get('status','?')}"
            metr = []
            cpu = v.get("cpu"); mem = v.get("mem"); maxmem = v.get("maxmem")
            dsk = v.get("disk"); maxdsk = v.get("maxdisk")
            if running and cpu is not None:
                metr.append(f"cpu {cpu*100:.0f}%")
            if running and mem and maxmem:
                metr.append(f"ram {_go(mem)}/{_go(maxmem)} Go ({mem/maxmem*100:.0f}%)")
            if maxdsk:
                real = None
                if running and v.get("type") == "qemu":
                    real = _vm_real_disk(v.get("node"), v.get("vmid"))  # via agent invité
                if real:
                    u, t = real
                    metr.append(f"disque {_go(u)}/{_go(t)} Go ({u/t*100:.0f}%) réel")
                elif dsk:
                    # LXC : usage réel ; QEMU : usage si dispo via cluster/resources.
                    metr.append(f"disque {_go(dsk)}/{_go(maxdsk)} Go ({dsk/maxdsk*100:.0f}%)")
                else:
                    metr.append(f"disque {_go(maxdsk)} Go (alloué)")
            lines.append(head + (("  · " + " · ".join(metr)) if metr else ""))

    if stores:
        lines.append("💽 Stockages (jauge Proxmox) :")
        seen = set()
        for s in sorted(stores, key=lambda x: x.get("storage", "")):
            key = s.get("storage")
            if key in seen:   # un stockage partagé apparaît par nœud → une seule ligne
                continue
            seen.add(key)
            ptype = s.get("plugintype", "") or s.get("type", "")
            used = s.get("disk"); total = s.get("maxdisk")
            tag = f" [{ptype}]" if ptype else ""
            if total:
                pct = f" ({used/total*100:.0f}%)" if used else ""
                lines.append(f"  - {key}{tag} : {_go(used or 0)}/{_go(total)} Go{pct}")
            else:
                lines.append(f"  - {key}{tag} : {s.get('status','?')}")
        lines.append("  ℹ️ Chiffres = jauge Proxmox (espace alloué/réservé au niveau du pool/FS). "
                     "Sur ZFS/LVM-thin — y compris un stockage « dir » posé sur un pool ZFS — "
                     "l'espace RÉELLEMENT écrit peut être bien inférieur. Pour le réel : `zfs list` / `df` sur le nœud.")
        lines.append("  [Consigne assistant : NE présente PAS ces pourcentages comme « presque plein » "
                     "ou « critique » ; précise toujours qu'il s'agit d'espace ALLOUÉ/provisionné au pool, "
                     "pas de l'écrit réel — sauf si l'utilisateur a demandé l'usage réel via zfs list/df.]")
    lines.append("[Consigne assistant : restitue les valeurs ABSOLUES en Go ET les pourcentages "
                 "(ex. « RAM 1.0/2.0 Go (54%) · disque 12.3/32 Go (38%) »), ne réduis PAS aux seuls %.]")
    return "\n".join(lines)


_FS_SKIP = {"tmpfs", "devtmpfs", "overlay", "overlayfs", "squashfs", "iso9660",
            "ramfs", "efivarfs", "autofs", "fuse.gvfsd-fuse", "proc", "sysfs"}


def _vm_real_disk(node, vmid):
    """Usage disque RÉEL (écrit) à l'intérieur d'une VM QEMU via l'agent invité
    (qemu-guest-agent). Renvoie (used_bytes, total_bytes) ou None si l'agent est absent."""
    data, err = _get(f"/nodes/{node}/qemu/{vmid}/agent/get-fsinfo")
    if err or not isinstance(data, dict):
        return None
    used = total = 0
    seen = set()
    for f in (data.get("result") or []):
        t = (f.get("type") or "").lower()
        mp = f.get("mountpoint") or ""
        tb = f.get("total-bytes") or 0
        ub = f.get("used-bytes") or 0
        if t in _FS_SKIP or tb <= 0 or mp in seen:
            continue
        seen.add(mp)
        total += tb
        used += ub
    return (used, total) if total > 0 else None


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


def proxmox_vm_exec(vmid: str, command: str, user_confirmed: bool = False) -> str:
    """
    Exécute une commande SHELL À L'INTÉRIEUR d'une VM QEMU via l'agent invité
    (qemu-guest-agent), sans SSH. ACTION TRÈS SENSIBLE → confirmation utilisateur obligatoire.

    Args:
        vmid (str): identifiant de la VM (ex. "104").
        command (str): la commande shell à exécuter dans la VM (ex. "df -h").
        user_confirmed (bool): True une fois l'utilisateur d'accord.
    Returns:
        str: sortie standard / erreur / code de retour de la commande.
    """
    if not proxmox.is_configured():
        return _not_configured()
    try:
        from core import projects
        if not projects.can_write():
            return "Erreur : accès en lecture seule — exécution refusée."
    except Exception:
        pass
    command = (command or "").strip()
    if not command:
        return "Erreur : commande vide."

    vm, err = _find_vm(vmid)
    if err:
        return err
    if vm.get("type") != "qemu":
        return "Erreur : l'exécution via agent invité ne concerne que les VM QEMU (pour un LXC, utilise SSH)."
    if vm.get("status") != "running":
        return f"Erreur : la VM {vmid} n'est pas en marche."
    node = vm.get("node"); name = vm.get("name", "?")

    if not user_confirmed:
        return (f"⚠️ Action TRÈS SENSIBLE : exécuter « {command} » DANS la VM [{vmid}] {name} (nœud {node}). "
                "Demande confirmation à l'utilisateur, puis rappelle l'outil avec user_confirmed=True.")

    base = f"{proxmox.api_base()}/nodes/{node}/qemu/{vmid}/agent"
    g = _guard(base)
    if g:
        return g
    # 1) Lancer la commande (l'agent exécute program+args ; on passe par bash -c).
    try:
        r = requests.post(base + "/exec", headers=proxmox.auth_header(), verify=proxmox.verify_tls(),
                          json={"command": ["/bin/bash", "-c", command]}, timeout=_TIMEOUT)
    except Exception as e:
        return f"Proxmox injoignable : {e}"
    if r.status_code == 403:
        return ("Refusé (403) : le jeton n'a pas le droit d'exécuter dans la VM (il faut "
                "VM.GuestAgent.* / rôle PVEAdmin).")
    if r.status_code not in (200, 201):
        low = r.text.lower()
        if "disabled" in low or "guest-exec" in low:
            return ("L'exécution est DÉSACTIVÉE dans l'agent invité de cette VM (qemu-guest-agent "
                    "bloque guest-exec par défaut pour la sécurité). Active-la dans la VM, ou utilise SSH.")
        return f"Erreur Proxmox ({r.status_code}) : {r.text[:200]}"
    try:
        pid = (r.json().get("data") or {}).get("pid")
    except Exception:
        pid = None
    if not pid:
        return "Erreur : l'agent n'a pas renvoyé d'identifiant de processus."

    # 2) Attendre la fin (poll exec-status), borné.
    import time as _t
    deadline = _t.time() + 45
    while _t.time() < deadline:
        st, serr = _get(f"/nodes/{node}/qemu/{vmid}/agent/exec-status?pid={pid}")
        if serr:
            return serr
        if isinstance(st, dict) and st.get("exited"):
            out = (st.get("out-data") or "").strip()
            errd = (st.get("err-data") or "").strip()
            code = st.get("exitcode")
            res = f"Commande exécutée dans [{vmid}] {name} (code {code}).\n"
            if out:
                res += f"--- sortie ---\n{out[:4000]}\n"
            if errd:
                res += f"--- erreur ---\n{errd[:2000]}\n"
            if not out and not errd:
                res += "(aucune sortie)"
            return res
        _t.sleep(1)
    return f"⏳ Commande lancée dans [{vmid}] {name} mais pas terminée à temps (pid {pid})."


proxmox_vm_exec._requires_approval = True


def proxmox_vm_logs(vmid: str, lines: int = 20) -> str:
    """Pourquoi une VM/conteneur s'est arrêté(e) ou a un souci : liste les dernières TÂCHES
    Proxmox la concernant (démarrage, arrêt, extinction, redémarrage, sauvegarde, erreurs) avec
    QUI les a lancées, QUAND et le RÉSULTAT. À utiliser quand une VM est tombée : ça distingue
    un arrêt MANUEL (qmstop par un utilisateur), un CRASH/échec de démarrage (tâche en erreur),
    ou une extinction propre. Lecture seule. Si la VM tourne et que tu veux ses logs INTERNES,
    utilise plutôt proxmox_vm_exec avec « journalctl -n 50 ».

    Args:
        vmid (str): identifiant numérique de la VM/conteneur (ex. "100").
        lines (int): nombre de tâches récentes à afficher (défaut 20).
    """
    if not proxmox.is_configured():
        return _not_configured()
    vm, err = _find_vm(vmid)
    if err:
        return err
    node = vm.get("node")
    name = vm.get("name", "")
    out = [f"VM/CT {vmid} « {name} » sur le nœud {node} — statut actuel : {vm.get('status', '?')}"]
    try:
        n = max(1, min(int(lines), 100))
    except Exception:
        n = 20
    data, err = _get(f"/nodes/{node}/tasks?vmid={vmid}&limit={n}&source=all")
    if err:  # certaines versions n'acceptent pas source=all
        data, err = _get(f"/nodes/{node}/tasks?vmid={vmid}&limit={n}")
    if err:
        return out[0] + "\n⚠️ " + err
    tasks = data or []
    if not tasks:
        out.append("Aucune tâche récente enregistrée pour cette VM (Proxmox a peut-être "
                   "purgé son journal de tâches, ou l'arrêt vient de l'hôte/OS lui-même).")
        return "\n".join(out)
    import datetime as _dt
    out.append(f"\n🗒️ {len(tasks)} dernières tâches Proxmox :")
    for t in tasks:
        ttype = t.get("type", "?")
        end = t.get("endtime")
        status = t.get("status") or ("en cours" if not end else "?")
        who = t.get("user", "") or ""
        ts = t.get("starttime")
        try:
            when = _dt.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M") if ts else "?"
        except Exception:
            when = str(ts)
        ok = (str(status).upper() == "OK")
        flag = "✅" if ok else ("⏳" if status == "en cours" else "❌")
        line = f"  {flag} {when} — {ttype}" + (f" par {who}" if who else "") + f" → {status}"
        out.append(line)
    out.append("\nIndice : un `qmstop`/`vzstop` ✅ par un utilisateur = arrêt volontaire ; une tâche "
               "❌ (souvent `qmstart`) = échec/crash ; aucun arrêt listé = extinction interne à la VM.")
    return "\n".join(out)
