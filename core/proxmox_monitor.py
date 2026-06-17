"""Moniteur Proxmox — détecte les incidents et POUSSE un événement à la Vigie.

Proxmox ne « pousse » pas l'état de ses VM : il faut l'INTERROGER. Ce moniteur fait un poll
LÉGER (un appel `/cluster/resources` toutes les N minutes, AUCUN LLM) et n'émet un événement
(via core.events) QUE sur incident : VM/LXC qui tombe, nœud offline, RAM/disque au-dessus d'un
seuil. La Vigie (agent) ne se réveille donc que sur problème.

Détection par transition (front montant) → pas de spam : on alerte au passage en panne / au
franchissement du seuil, pas à chaque cycle.

Gating : tourne seulement si la Vigie est activée ET « proxmox_monitor » coché ET Proxmox
configuré. Tourne sous le compte `owner_user` (pour lire la config Proxmox par-utilisateur).
"""
import threading
import time

_started = False
_active = {}        # clé d'alerte -> alerte en cours ? (hystérésis seuils)
_prev_status = {}   # vmid/node -> dernier statut connu (détection de chute)


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="proxmox-monitor").start()
    print("🛰️  [Vigie/Proxmox] moniteur démarré (poll léger, événementiel).")


def _loop():
    from core import events
    while True:
        interval = 300
        try:
            cfg = events.config()
            interval = int(cfg.get("proxmox_interval", 300) or 300)
            if cfg.get("enabled") and cfg.get("proxmox_monitor"):
                _check_once(cfg)
        except Exception as e:
            print(f"[Vigie/Proxmox] erreur : {e}")
        time.sleep(max(60, interval))


def _edge(key: str, active_now: bool) -> bool:
    """Front montant : True seulement quand on passe inactif → actif (alerte une fois)."""
    was = _active.get(key, False)
    _active[key] = active_now
    return active_now and not was


def _check_once(cfg: dict):
    from core import events, proxmox
    from core.state import _current_username
    from tools import proxmox_tools as px

    owner = cfg.get("owner_user") or "local"
    tok = _current_username.set(owner)
    try:
        if not proxmox.is_configured():
            return
        data, err = px._get("/cluster/resources")
        if err or not isinstance(data, list):
            return
        ram_th = float(cfg.get("proxmox_ram_pct", 90) or 90)
        disk_th = float(cfg.get("proxmox_disk_pct", 90) or 90)

        # --- Nœuds : passage en offline ---
        for n in [r for r in data if r.get("type") == "node"]:
            name = n.get("node")
            status = n.get("status")
            prev = _prev_status.get(f"node:{name}")
            _prev_status[f"node:{name}"] = status
            if prev == "online" and status != "online":
                events.submit({"type": "proxmox_node_down", "source": f"pve/{name}",
                               "severity": "critical",
                               "message": f"Le nœud Proxmox « {name} » est passé hors-ligne ({status})."})

        # --- VM / LXC ---
        for v in [r for r in data if r.get("type") in ("qemu", "lxc")]:
            vmid = v.get("vmid"); name = v.get("name", "?"); node = v.get("node")
            typ = v.get("type"); status = v.get("status")
            kind = "VM" if typ == "qemu" else "LXC"
            src = f"pve/{node}/{vmid}"

            # Chute : était running, ne l'est plus.
            prev = _prev_status.get(f"vm:{vmid}")
            _prev_status[f"vm:{vmid}"] = status
            if prev == "running" and status != "running":
                events.submit({"type": "proxmox_vm_down", "source": src, "severity": "critical",
                               "message": f"{kind} {vmid} « {name} » s'est arrêtée (statut {status})."})
                continue
            if status != "running":
                continue

            # RAM au-dessus du seuil.
            mem = v.get("mem"); maxmem = v.get("maxmem")
            if mem and maxmem:
                pct = mem / maxmem * 100
                if _edge(f"vm:{vmid}:ram", pct >= ram_th):
                    events.submit({"type": "proxmox_high_ram", "source": src, "severity": "warning",
                                   "message": f"{kind} {vmid} « {name} » : RAM à {pct:.0f}% "
                                              f"({mem/1e9:.1f}/{maxmem/1e9:.1f} Go, seuil {ram_th:.0f}%)."})

            # Disque réel au-dessus du seuil (QEMU via agent, LXC via cluster).
            dpct = None; det = ""
            if typ == "qemu":
                real = px._vm_real_disk(node, vmid)
                if real and real[1]:
                    dpct = real[0] / real[1] * 100
                    det = f"{real[0]/1e9:.1f}/{real[1]/1e9:.1f} Go"
            else:
                dsk = v.get("disk"); maxdsk = v.get("maxdisk")
                if dsk and maxdsk:
                    dpct = dsk / maxdsk * 100
                    det = f"{dsk/1e9:.1f}/{maxdsk/1e9:.1f} Go"
            if dpct is not None and _edge(f"vm:{vmid}:disk", dpct >= disk_th):
                events.submit({"type": "proxmox_high_disk", "source": src, "severity": "warning",
                               "message": f"{kind} {vmid} « {name} » : disque à {dpct:.0f}% "
                                          f"({det}, seuil {disk_th:.0f}%)."})
    finally:
        _current_username.reset(tok)
