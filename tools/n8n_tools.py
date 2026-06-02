"""Déclenchement de workflows n8n (ou tout webhook entrant) — « n8n as a tool ».

Sécurité : l'agent n'appelle PAS une URL arbitraire (risque SSRF / effets de bord).
Il invoque un workflow par NOM, parmi une allowlist configurée par l'utilisateur :
  N8N_WORKFLOWS = {"creer_devis": "https://n8n.local/webhook/abc", ...}   (JSON)
  ou un fichier N8N_WORKFLOWS_PATH (JSON {nom: url}).
L'outil est marqué « sensible » (approbation) car il agit sur des systèmes externes.
"""
import os
import json


def _load_workflows() -> dict:
    raw = os.getenv("N8N_WORKFLOWS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
    path = os.getenv("N8N_WORKFLOWS_PATH", "").strip()
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
    return {}


def trigger_workflow(name: str, payload: str = "", user_confirmed: bool = False) -> str:
    """
    Déclenche un workflow d'automatisation n8n (ou un webhook) préalablement déclaré par
    l'utilisateur, en l'appelant par son NOM. À utiliser pour lancer une action externe
    (ex. « créer un devis », « publier sur le CRM »).
    name: nom du workflow tel que configuré (allowlist N8N_WORKFLOWS).
    payload: données à envoyer — JSON (objet) ou texte simple (envoyé comme {"text": ...}).
    """
    workflows = _load_workflows()
    if not workflows:
        return ("Aucun workflow n8n configuré. Définis N8N_WORKFLOWS (JSON {nom: url}) "
                "ou N8N_WORKFLOWS_PATH pour autoriser des workflows.")
    name = (name or "").strip()
    if name not in workflows:
        return (f"Workflow « {name} » inconnu. Workflows disponibles : "
                + ", ".join(sorted(workflows)) + ".")
    url = workflows[name]

    body = (payload or "").strip()
    if body:
        try:
            data = json.loads(body)
            if not isinstance(data, (dict, list)):
                data = {"text": body}
        except Exception:
            data = {"text": body}
    else:
        data = {}

    try:
        import requests
        r = requests.post(url, json=data, timeout=int(os.getenv("N8N_TIMEOUT", "30")))
    except Exception as e:
        return f"Erreur : workflow « {name} » injoignable ({e})."
    out = (r.text or "").strip()
    if len(out) > 2000:
        out = out[:2000] + "… [tronqué]"
    verdict = "déclenché ✅" if r.status_code < 400 else f"erreur HTTP {r.status_code}"
    return f"Workflow « {name} » {verdict}." + (f"\nRéponse : {out}" if out else "")
