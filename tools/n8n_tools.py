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


# ============================================================================
# API REST n8n (v1) — découverte, exécution, exécutions, gestion (HITL).
# Sécurité : anti-SSRF (net_guard), clé API, mutations = outils SENSIBLES (HITL).
# ============================================================================
_API_TIMEOUT = int(os.getenv("N8N_TIMEOUT", "30"))


def _api(method: str, path: str, json_body=None, params=None):
    """Requête sur l'API n8n. Renvoie (data, None) ou (None, message_erreur)."""
    from core import n8n
    if not n8n.is_configured():
        return None, ("n8n (API) non configuré : Réglages → renseigne N8N_API_URL "
                      "(ex. https://n8n.local) et N8N_API_KEY (n8n → Settings → n8n API).")
    url = n8n.api_base() + path
    try:
        from tools.net_guard import is_blocked_url
        if is_blocked_url(url):
            return None, ("Erreur : l'hôte n8n est une adresse interne bloquée (anti-SSRF). "
                          "Ajoute-le à NET_GUARD_ALLOW_HOSTS (Réglages) pour ce service de confiance.")
    except Exception:
        pass
    try:
        import requests
        r = requests.request(method, url, headers=n8n.auth_header(), json=json_body,
                             params=params, verify=n8n.verify_tls(), timeout=_API_TIMEOUT)
    except Exception as e:
        return None, f"n8n injoignable : {e}"
    if r.status_code == 401:
        return None, "n8n : clé API refusée (401). Vérifie N8N_API_KEY."
    if r.status_code >= 400:
        return None, f"n8n a répondu {r.status_code} : {(r.text or '')[:200]}"
    try:
        return (r.json() if (r.text or "").strip() else {}), None
    except Exception:
        return r.text, None


def _items(data):
    if isinstance(data, dict):
        return data.get("data", []) or []
    return data or []


def _resolve(name_or_id: str):
    """Retrouve un workflow par id exact puis par nom (insensible à la casse)."""
    data, err = _api("GET", "/workflows")
    if err:
        return None, err
    items = _items(data)
    s = (name_or_id or "").strip()
    for w in items:
        if str(w.get("id")) == s:
            return w, None
    for w in items:
        if (w.get("name") or "").strip().lower() == s.lower():
            return w, None
    dispo = ", ".join((w.get("name") or "?") for w in items[:30]) or "(aucun)"
    return None, f"Workflow « {name_or_id} » introuvable. Disponibles : {dispo}."


def _webhook_url(workflow: dict):
    """Déduit l'URL de webhook de PRODUCTION d'un workflow (1er nœud Webhook), ou None."""
    from core import n8n
    for node in (workflow.get("nodes") or []):
        if "webhook" in str(node.get("type", "")).lower():
            p = (node.get("parameters") or {}).get("path")
            if p:
                return n8n.base_url() + "/webhook/" + str(p).lstrip("/")
    return None


def list_n8n_workflows() -> str:
    """Liste les workflows de TON instance n8n (nom, id, actif/inactif) via l'API — découverte
    automatique, pas besoin de les déclarer à la main. Lecture seule."""
    data, err = _api("GET", "/workflows")
    if err:
        return err
    items = _items(data)
    if not items:
        return "Aucun workflow n8n trouvé sur l'instance."
    out = [f"🛠️ {len(items)} workflow(s) n8n :"]
    for w in items:
        out.append(f"- {'🟢 actif' if w.get('active') else '⚪ inactif'} — {w.get('name','?')} "
                   f"(id {w.get('id')})")
    return "\n".join(out)


def get_n8n_workflow(name_or_id: str) -> str:
    """Détaille un workflow n8n : état, nœuds, et son URL de webhook s'il en a une. Lecture seule.
    name_or_id : nom ou identifiant du workflow."""
    w, err = _resolve(name_or_id)
    if err:
        return err
    nodes = w.get("nodes") or []
    types = ", ".join(sorted({str(n.get("type", "")).split(".")[-1] for n in nodes})) or "—"
    hook = _webhook_url(w)
    out = [f"🛠️ Workflow « {w.get('name')} » (id {w.get('id')}) — "
           f"{'🟢 actif' if w.get('active') else '⚪ inactif'}",
           f"- {len(nodes)} nœud(s) : {types}"]
    if hook:
        out.append(f"- Déclencheur webhook : {hook}")
    return "\n".join(out)


def get_n8n_executions(name_or_id: str = "", limit: int = 5) -> str:
    """Dernières EXÉCUTIONS d'un workflow (ou de tous si vide) : statut succès/échec + date.
    Pour vérifier qu'une automatisation a bien tourné. Lecture seule."""
    params = {"limit": max(1, min(int(limit or 5), 20))}
    if (name_or_id or "").strip():
        w, err = _resolve(name_or_id)
        if err:
            return err
        params["workflowId"] = str(w.get("id"))
    data, err = _api("GET", "/executions", params=params)
    if err:
        return err
    items = _items(data)
    if not items:
        return "Aucune exécution récente."
    out = ["🧾 Exécutions récentes :"]
    for e in items:
        status = "✅" if e.get("finished") and not e.get("stoppedAt") is None else "•"
        verdict = "✅ succès" if e.get("finished") else "⏳/❌"
        out.append(f"- {verdict} — wf {e.get('workflowId')} — {(e.get('startedAt') or '')[:19]}")
    return "\n".join(out)


def run_n8n_workflow(name_or_id: str, payload: str = "", user_confirmed: bool = False) -> str:
    """Déclenche un workflow n8n par son NOM/ID via son webhook (découvert par l'API) et renvoie
    la réponse. Action externe → SENSIBLE (validation). payload : JSON ou texte.
    Astuce : si le workflow n'a pas de nœud Webhook, utilise trigger_workflow (allowlist) à la place."""
    w, err = _resolve(name_or_id)
    if err:
        return err
    hook = _webhook_url(w)
    if not hook:
        return (f"Le workflow « {w.get('name')} » n'a pas de déclencheur Webhook → impossible à "
                "lancer par API. Ajoute un nœud Webhook, ou déclare son URL dans N8N_WORKFLOWS "
                "et utilise trigger_workflow.")
    body = (payload or "").strip()
    try:
        data = json.loads(body) if body else {}
        if not isinstance(data, (dict, list)):
            data = {"text": body}
    except Exception:
        data = {"text": body}
    try:
        import requests
        from core import n8n
        r = requests.post(hook, json=data, verify=n8n.verify_tls(), timeout=_API_TIMEOUT)
    except Exception as e:
        return f"Erreur : webhook « {w.get('name')} » injoignable ({e})."
    out = (r.text or "").strip()[:2000]
    verdict = "déclenché ✅" if r.status_code < 400 else f"erreur HTTP {r.status_code}"
    return f"Workflow « {w.get('name')} » {verdict}." + (f"\nRéponse : {out}" if out else "")


def set_n8n_workflow_active(name_or_id: str, active: bool = True, user_confirmed: bool = False) -> str:
    """Active ou désactive un workflow n8n. SENSIBLE (validation). active=True pour activer."""
    w, err = _resolve(name_or_id)
    if err:
        return err
    verb = "activate" if active else "deactivate"
    _data, err = _api("POST", f"/workflows/{w.get('id')}/{verb}")
    if err:
        return err
    return f"Workflow « {w.get('name')} » {'activé 🟢' if active else 'désactivé ⚪'}."


def _validate_workflow_json(definition_json: str):
    """Parse + valide grossièrement un workflow n8n. Renvoie (objet, None) ou (None, message)."""
    try:
        obj = json.loads(definition_json) if isinstance(definition_json, str) else definition_json
    except Exception as e:
        return None, ("❌ JSON n8n invalide (" + str(e) + "). Le format des workflows n8n est "
                      "complexe : pour le GÉNÉRER de façon fiable, utilise un MODÈLE COSTAUD "
                      "(Claude/GPT/un gros coder) en CODE_MODEL/chat, ou crée-le à la main dans n8n.")
    if not isinstance(obj, dict) or not obj.get("name") or "nodes" not in obj:
        return None, ("❌ Workflow incomplet : il faut au moins { name, nodes, connections }. "
                      "Génère un JSON n8n complet (un modèle costaud est recommandé pour ça).")
    obj.setdefault("connections", {})
    obj.setdefault("settings", {})
    return obj, None


def create_n8n_workflow(definition_json: str, user_confirmed: bool = False) -> str:
    """CRÉE un workflow n8n à partir d'un JSON complet ({name, nodes, connections}). SENSIBLE
    (validation). Le JSON n8n est complexe : si la génération échoue, l'outil PRÉVIENT qu'un
    modèle costaud est nécessaire (il ne casse rien). Le workflow est créé INACTIF par sécurité."""
    obj, err = _validate_workflow_json(definition_json)
    if err:
        return err
    data, err = _api("POST", "/workflows", json_body=obj)
    if err:
        return ("Création refusée par n8n : " + err + "\n(Si c'est un souci de format, un MODÈLE "
                "COSTAUD est recommandé pour générer un workflow n8n valide.)")
    wid = (data or {}).get("id") if isinstance(data, dict) else None
    return (f"✅ Workflow « {obj.get('name')} » créé (id {wid}), INACTIF. "
            "Vérifie-le dans n8n puis active-le (set_n8n_workflow_active).")


def update_n8n_workflow(name_or_id: str, definition_json: str, user_confirmed: bool = False) -> str:
    """MET À JOUR un workflow n8n existant avec un nouveau JSON complet. SENSIBLE (validation)."""
    w, err = _resolve(name_or_id)
    if err:
        return err
    obj, err = _validate_workflow_json(definition_json)
    if err:
        return err
    _data, err = _api("PUT", f"/workflows/{w.get('id')}", json_body=obj)
    if err:
        return "Mise à jour refusée par n8n : " + err
    return f"✅ Workflow « {w.get('name')} » (id {w.get('id')}) mis à jour."


def delete_n8n_workflow(name_or_id: str, user_confirmed: bool = False) -> str:
    """SUPPRIME un workflow n8n. SENSIBLE (validation) — irréversible."""
    w, err = _resolve(name_or_id)
    if err:
        return err
    _data, err = _api("DELETE", f"/workflows/{w.get('id')}")
    if err:
        return "Suppression refusée par n8n : " + err
    return f"🗑️ Workflow « {w.get('name')} » (id {w.get('id')}) supprimé."


# Mutations = actions sensibles → HITL (validation utilisateur avant exécution).
for _f in (run_n8n_workflow, set_n8n_workflow_active, create_n8n_workflow,
           update_n8n_workflow, delete_n8n_workflow):
    _f._requires_approval = True
