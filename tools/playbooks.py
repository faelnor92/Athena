"""Playbooks Markdown — « Agent Skills » façon Anthropic / Hermes.

Complément des skills Python : ceux-ci CALCULENT (fonctions pures déterministes),
les playbooks portent du SAVOIR-FAIRE PROCÉDURAL (« comment faire X » : workflow,
checklist, conventions métier) que l'agent SUIT.

Disclosure progressive (économie de tokens) : un INDEX compact (nom + description,
une ligne chacun) est toujours visible dans le contexte de l'agent ; le CORPS complet
n'est chargé qu'à la demande via l'outil `load_playbook(name)` quand un playbook est
pertinent. Stockage : fichiers `playbooks/*.md`, avec frontmatter optionnel
(`name:` / `description:`).
"""
import os
import re
import glob

PLAYBOOKS_DIR = os.getenv("PLAYBOOKS_DIR", "playbooks")

_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    name = os.path.splitext(os.path.basename(path))[0]
    desc, body = "", txt
    m = _FRONT_RE.match(txt)
    if m:
        front, body = m.group(1), m.group(2)
        for line in front.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if k == "name" and v:
                    name = v
                elif k == "description" and v:
                    desc = v
    if not desc:
        for line in body.splitlines():
            s = line.strip().lstrip("#").strip()
            if s:
                desc = s[:140]
                break
    return {"name": name, "description": desc, "body": body.strip(), "path": path}


def _all():
    if not os.path.isdir(PLAYBOOKS_DIR):
        return []
    out = []
    for p in sorted(glob.glob(os.path.join(PLAYBOOKS_DIR, "*.md"))):
        pb = _parse(p)
        if pb:
            out.append(pb)
    return out


def list_playbooks():
    """Index compact (nom + description), sans le corps — pour l'UI et le prompt."""
    return [{"name": p["name"], "description": p["description"]} for p in _all()]


def index_prompt() -> str:
    """Bloc à injecter dans le system_prompt : l'index des playbooks disponibles. STABLE
    (ne change que si on ajoute/retire un playbook) → reste cacheable. '' si aucun."""
    pbs = list_playbooks()
    if not pbs:
        return ""
    lines = "\n".join(f"- {p['name']} — {p['description']}" for p in pbs)
    return ("\n\n=== PLAYBOOKS DISPONIBLES (savoir-faire procédural) ===\n"
            "Si l'un d'eux correspond à la tâche demandée, CHARGE-le AVANT d'agir via "
            "`load_playbook('<nom>')`, puis suis ses étapes.\n" + lines + "\n")


def load_playbook(name: str) -> str:
    """Charge le CONTENU COMPLET d'un playbook (procédure / savoir-faire) par son nom, pour
    en suivre les étapes. Consulte la liste « PLAYBOOKS DISPONIBLES » fournie dans ton
    contexte pour connaître les noms valides.
    name: le nom du playbook (ex. 'deployer-un-site-statique').
    """
    target = (name or "").strip().lower()
    if not target:
        return "Erreur : nom de playbook requis."
    pbs = _all()
    best = None
    for pb in pbs:
        fname = os.path.splitext(os.path.basename(pb["path"]))[0].lower()
        if pb["name"].lower() == target or fname == target:
            best = pb
            break
        if best is None and (target in pb["name"].lower() or target in fname):
            best = pb
    if not best:
        avail = ", ".join(p["name"] for p in pbs) or "(aucun)"
        return f"Playbook « {name} » introuvable. Disponibles : {avail}."
    return f"# Playbook : {best['name']}\n\n{best['body']}"
