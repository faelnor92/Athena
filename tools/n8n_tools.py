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


# ============================================================================
# TEMPLATES de workflows — création FIABLE sans génération de JSON par l'IA.
# Le modèle choisit un modèle + remplit des paramètres → JSON n8n valide garanti.
# (Ciblent une version n8n récente ; un détail peut nécessiter un ajustement dans n8n.)
# ============================================================================
import uuid as _uuid


def _node(name, ntype, params, pos, tv=1):
    return {"id": _uuid.uuid4().hex, "name": name, "type": ntype,
            "typeVersion": tv, "position": pos, "parameters": params}


def _conn(src, dst):
    return {src: {"main": [[{"node": dst, "type": "main", "index": 0}]]}}


def _tmpl_webhook_to_http(name, p):
    wh = _node("Webhook", "n8n-nodes-base.webhook",
               {"httpMethod": "POST", "path": str(p["path"]).lstrip("/"), "responseMode": "onReceived"},
               [240, 300], 1)
    http = _node("HTTP Request", "n8n-nodes-base.httpRequest",
                 {"method": (p.get("method") or "POST").upper(), "url": p["url"],
                  "sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json }}", "options": {}},
                 [480, 300], 4)
    return {"name": name, "nodes": [wh, http], "connections": _conn("Webhook", "HTTP Request"), "settings": {}}


def _tmpl_schedule_to_http(name, p):
    hrs = int(p.get("hours_interval") or 1)
    sch = _node("Schedule", "n8n-nodes-base.scheduleTrigger",
                {"rule": {"interval": [{"field": "hours", "hoursInterval": hrs}]}}, [240, 300], 1.1)
    http = _node("HTTP Request", "n8n-nodes-base.httpRequest",
                 {"method": (p.get("method") or "GET").upper(), "url": p["url"], "options": {}}, [480, 300], 4)
    return {"name": name, "nodes": [sch, http], "connections": _conn("Schedule", "HTTP Request"), "settings": {}}


def _tmpl_webhook_to_athena(name, p):
    """n8n → Athena : un webhook pousse un événement sur /api/events (pont bidirectionnel)."""
    token = p.get("event_token") or ""
    if not token:
        try:
            from core import events
            token = (events.config().get("ingest_token") or "")
        except Exception:
            token = ""
    athena = (p.get("athena_url") or "").rstrip("/")
    wh = _node("Webhook", "n8n-nodes-base.webhook",
               {"httpMethod": "POST", "path": str(p.get("path") or "to-athena").lstrip("/"),
                "responseMode": "onReceived"}, [240, 300], 1)
    http = _node("HTTP Request → Athena", "n8n-nodes-base.httpRequest",
                 {"method": "POST", "url": athena + "/api/events",
                  "sendHeaders": True,
                  "headerParameters": {"parameters": [{"name": "X-Event-Token", "value": token}]},
                  "sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json }}", "options": {}},
                 [480, 300], 4)
    return {"name": name, "nodes": [wh, http], "connections": _conn("Webhook", "HTTP Request → Athena"), "settings": {}}


_TEMPLATES = {
    "webhook_to_http": (_tmpl_webhook_to_http,
                        "Reçoit un appel (webhook) et le relaie en POST JSON vers une API.",
                        ["path", "url", "method?"]),
    "schedule_to_http": (_tmpl_schedule_to_http,
                         "Appelle une URL périodiquement (toutes les N heures).",
                         ["url", "hours_interval?", "method?"]),
    "webhook_to_athena_event": (_tmpl_webhook_to_athena,
                                "Pont n8n→Athena : un webhook pousse un événement à la Vigie d'Athena "
                                "(POST /api/events). Renseigne athena_url (+ event_token si connu).",
                                ["athena_url", "path?", "event_token?"]),
}


def list_n8n_templates() -> str:
    """Liste les TEMPLATES de workflows n8n prêts à l'emploi. Préfère-les à la génération de JSON :
    tu n'as qu'à remplir des paramètres → workflow VALIDE garanti (fiable avec tout modèle)."""
    out = ["🧩 Templates de workflows n8n (création fiable) :"]
    for k, (_fn, desc, params) in _TEMPLATES.items():
        out.append(f"- **{k}** — {desc}\n  params : {', '.join(params)} (un nom suivi de ? est optionnel)")
    out.append("\nUtilise create_n8n_workflow_from_template(template, name, params_json).")
    return "\n".join(out)


def create_n8n_workflow_from_template(template: str, name: str, params: str = "",
                                      user_confirmed: bool = False) -> str:
    """CRÉE un workflow n8n à partir d'un TEMPLATE prêt à l'emploi (JSON valide garanti, sans
    génération par l'IA). SENSIBLE (validation). Préféré à create_n8n_workflow pour les cas courants.

    template : clé parmi list_n8n_templates (ex. "webhook_to_http").
    name : nom du workflow à créer.
    params : JSON des paramètres du template (ex. {"path":"mon-hook","url":"https://api…"}).
    Le workflow est créé INACTIF."""
    tk = (template or "").strip()
    if tk not in _TEMPLATES:
        return f"Template inconnu « {template} ». Disponibles : {', '.join(_TEMPLATES)}."
    fn, _desc, plist = _TEMPLATES[tk]
    try:
        p = json.loads(params) if (params or "").strip() else {}
        if not isinstance(p, dict):
            return "params doit être un objet JSON (ex. {\"url\":\"https://…\"})."
    except Exception as e:
        return f"params JSON invalide : {e}"
    required = [x for x in plist if not x.endswith("?")]
    missing = [x for x in required if not str(p.get(x) or "").strip()]
    if missing:
        return f"Paramètres manquants pour « {tk} » : {', '.join(missing)}."
    try:
        wf = fn((name or tk).strip(), p)
    except Exception as e:
        return f"Échec de construction du template : {e}"
    data, err = _api("POST", "/workflows", json_body=wf)
    if err:
        return "Création refusée par n8n : " + err
    wid = (data or {}).get("id") if isinstance(data, dict) else None
    hook = _webhook_url(wf)
    msg = f"✅ Workflow « {wf.get('name')} » créé depuis le template « {tk} » (id {wid}), INACTIF."
    if hook:
        msg += f"\nWebhook : {hook}"
    msg += "\nVérifie dans n8n puis active-le (set_n8n_workflow_active)."
    return msg


create_n8n_workflow_from_template._requires_approval = True


# ============================================================================
# BLINDAGE : constructeur GÉNÉRIQUE (n'importe quel nœud/topologie) + export (clone/adapt).
# La partie fragile (id, positions, typeVersion, câblage connections, enveloppe) est gérée
# CÔTÉ SERVEUR → le modèle ne fournit que des nœuds {name,type,params} + des liens.
# ============================================================================

# typeVersion par défaut pour les nœuds n8n courants (nom court ou complet accepté).
_NODE_TV = {
    "webhook": 1, "scheduleTrigger": 1.1, "cron": 1, "manualTrigger": 1, "httpRequest": 4,
    "respondToWebhook": 1, "set": 3.4, "code": 2, "function": 1, "if": 2, "switch": 3,
    "merge": 3, "filter": 2, "noOp": 1, "splitInBatches": 3, "itemLists": 3, "wait": 1.1,
    "emailSend": 2.1, "emailReadImap": 2, "telegram": 1.2, "slack": 2.2, "discord": 2,
    "googleSheets": 4.4, "postgres": 2.5, "mySql": 2.4, "redis": 1, "mongoDb": 1.1,
    "openAi": 1.6, "rssFeedRead": 1, "executeWorkflow": 1, "stickyNote": 1, "htmlExtract": 1,
}


def _full_type(t: str) -> str:
    t = (t or "").strip()
    if not t or "." in t:
        return t
    return "n8n-nodes-base." + t


def create_n8n_workflow_from_spec(name: str, nodes: str, edges: str = "",
                                  user_confirmed: bool = False) -> str:
    """Construit un workflow n8n ARBITRAIRE à partir d'une spec SIMPLIFIÉE — couvre n'importe quel
    type de nœud et n'importe quelle topologie. Le serveur assemble un JSON n8n VALIDE (id, positions,
    typeVersion, connexions) : tu n'as PAS à gérer l'enveloppe fragile. SENSIBLE (HITL). Créé INACTIF.

    nodes : JSON liste de nœuds — [{"name":"Webhook","type":"webhook","params":{...}},
            {"name":"HTTP","type":"httpRequest","params":{"method":"POST","url":"…"}}]. Le `type` peut
            être court ("httpRequest", "set", "if", "telegram"…) ou complet ("n8n-nodes-base.httpRequest").
    edges : JSON liste de liens [["Webhook","HTTP"], …] (par NOM de nœud). BRANCHEMENT : ajoute un 3e
            élément = index de SORTIE du nœud source — IF → [["IF","SiVrai"], ["IF","SiFaux",1]] ;
            Switch → 0,1,2… selon les sorties.
    Note : les nœuds avec identifiants (Telegram, e-mail, BDD…) nécessitent d'attacher la CREDENTIAL
    correspondante dans n8n après création."""
    try:
        ns = json.loads(nodes) if isinstance(nodes, str) else nodes
    except Exception as e:
        return f"nodes JSON invalide : {e}"
    if not isinstance(ns, list) or not ns:
        return "nodes doit être une LISTE non vide de {name, type, params}."
    try:
        es = json.loads(edges) if (edges or "").strip() else []
    except Exception as e:
        return f"edges JSON invalide : {e}"
    built, names = [], set()
    for i, n in enumerate(ns):
        if not isinstance(n, dict) or not n.get("name") or not n.get("type"):
            return "Chaque nœud doit avoir au moins { name, type }."
        nm = str(n["name"]).strip()
        if nm in names:
            return f"Nom de nœud dupliqué : « {nm} » (les noms doivent être uniques)."
        names.add(nm)
        ft = _full_type(n["type"])
        short = ft.split(".")[-1]
        tv = n.get("typeVersion") or _NODE_TV.get(short, 1)
        node = _node(nm, ft, n.get("params") or {}, [240 + i * 220, 300], tv)
        if isinstance(n.get("credentials"), dict):
            node["credentials"] = n["credentials"]  # ex. {"telegramApi": {"id":"…","name":"…"}}
        built.append(node)
    conns = {}
    for e in es:
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            continue
        a, b = str(e[0]), str(e[1])
        # 3e élément optionnel = index de SORTIE du nœud source (branchement) :
        # IF → 0 = vrai, 1 = faux ; Switch → 0,1,2… selon les sorties. Défaut 0.
        try:
            out_idx = int(e[2]) if len(e) >= 3 else 0
        except Exception:
            out_idx = 0
        if a not in names or b not in names:
            return f"Lien invalide (nœud inconnu) : {e}. Nœuds définis : {', '.join(sorted(names))}."
        main = conns.setdefault(a, {"main": []})["main"]
        while len(main) <= out_idx:
            main.append([])
        main[out_idx].append({"node": b, "type": "main", "index": 0})
    wf = {"name": (name or "Workflow").strip(), "nodes": built, "connections": conns, "settings": {}}
    data, err = _api("POST", "/workflows", json_body=wf)
    if err:
        return ("Création refusée par n8n : " + err + "\n(Si ce sont les PARAMÈTRES d'un nœud qui "
                "coincent, un modèle costaud aide à les renseigner correctement.)")
    wid = (data or {}).get("id") if isinstance(data, dict) else None
    hook = _webhook_url(wf)
    return (f"✅ Workflow « {wf['name']} » créé depuis spec ({len(built)} nœud(s)), id {wid}, INACTIF."
            + (f"\nWebhook : {hook}" if hook else "")
            + "\nPense à attacher les credentials nécessaires dans n8n, puis active-le.")


create_n8n_workflow_from_spec._requires_approval = True


def export_n8n_workflow(name_or_id: str) -> str:
    """Renvoie le JSON COMPLET d'un workflow n8n existant — pour le CLONER/ADAPTER puis recréer
    (create_n8n_workflow) ou mettre à jour (update_n8n_workflow). Lecture seule."""
    w, err = _resolve(name_or_id)
    if err:
        return err
    data, err = _api("GET", f"/workflows/{w.get('id')}")
    if err:
        return err
    full = data if isinstance(data, dict) else w
    # On ne garde que les clés utiles à une recréation (n8n rejette certains champs en lecture).
    slim = {k: full.get(k) for k in ("name", "nodes", "connections", "settings") if k in full}
    dump = json.dumps(slim, ensure_ascii=False, indent=2)
    if len(dump) > 6000:
        dump = dump[:6000] + "\n… [tronqué — workflow volumineux]"
    return f"JSON du workflow « {full.get('name')} » :\n```json\n{dump}\n```"


def _tmpl_telegram(name, p):
    msg = _node("Webhook", "n8n-nodes-base.webhook",
                {"httpMethod": "POST", "path": str(p.get("path") or "tg").lstrip("/"),
                 "responseMode": "onReceived"}, [240, 300], 1)
    tg = _node("Telegram", "n8n-nodes-base.telegram",
               {"resource": "message", "operation": "sendMessage",
                "chatId": str(p.get("chat_id") or ""), "text": p.get("text") or "={{ $json.text }}"},
               [480, 300], 1.2)
    return {"name": name, "nodes": [msg, tg], "connections": _conn("Webhook", "Telegram"), "settings": {}}


def _tmpl_email(name, p):
    wh = _node("Webhook", "n8n-nodes-base.webhook",
               {"httpMethod": "POST", "path": str(p.get("path") or "mail").lstrip("/"),
                "responseMode": "onReceived"}, [240, 300], 1)
    em = _node("Email", "n8n-nodes-base.emailSend",
               {"fromEmail": p.get("from") or "", "toEmail": p["to"],
                "subject": p.get("subject") or "Notification Athena", "text": p.get("text") or "={{ $json.text }}"},
               [480, 300], 2.1)
    return {"name": name, "nodes": [wh, em], "connections": _conn("Webhook", "Email"), "settings": {}}


_TEMPLATES["webhook_to_telegram"] = (
    _tmpl_telegram, "Webhook → message Telegram (attache la credential Telegram dans n8n).",
    ["chat_id", "path?", "text?"])
_TEMPLATES["webhook_to_email"] = (
    _tmpl_email, "Webhook → e-mail (attache la credential SMTP/Email dans n8n).",
    ["to", "from?", "subject?", "path?", "text?"])


# ============================================================================
# #2 Détail d'exécution (debug) + #1 Credentials (HITL).
# ============================================================================
def get_n8n_execution(execution_id: str) -> str:
    """Détail d'UNE exécution n8n (id obtenu via get_n8n_executions) : statut + ERREUR précise du
    nœud en cas d'échec → pour diagnostiquer/corriger. Lecture seule."""
    data, err = _api("GET", f"/executions/{execution_id}", params={"includeData": "true"})
    if err:
        return err
    if not isinstance(data, dict):
        return "Exécution introuvable."
    fin = data.get("finished")
    status = data.get("status") or ("success" if fin else "en cours/inconnu")
    out = [f"🧾 Exécution {data.get('id')} — workflow {data.get('workflowId')} — {status}",
           f"- démarrée : {(data.get('startedAt') or '')[:19]} · arrêtée : {(data.get('stoppedAt') or '')[:19]}"]
    rd = (data.get("data") or {}).get("resultData") or {}
    errors = []
    eo = rd.get("error")
    if eo:
        node = eo.get("node")
        node = node.get("name") if isinstance(node, dict) else node
        errors.append((node or "?", eo.get("message") or eo.get("description") or str(eo)))
    for nm, runs in (rd.get("runData") or {}).items():
        for run in (runs or []):
            e = (run or {}).get("error")
            if e:
                errors.append((nm, e.get("message") or str(e)))
                break
    if errors:
        for nm, msg in errors[:5]:
            out.append(f"- ❌ « {nm} » : {str(msg)[:300]}")
    else:
        out.append("- ✅ aucune erreur détectée.")
    return "\n".join(out)


def get_n8n_credential_schema(cred_type: str) -> str:
    """Champs attendus pour créer une credential n8n d'un type (ex. telegramApi, smtp, httpHeaderAuth,
    openAiApi, httpBasicAuth). À consulter AVANT create_n8n_credential. Lecture seule."""
    if not (cred_type or "").strip():
        return "Indique un type de credential (ex. telegramApi, smtp, httpHeaderAuth)."
    data, err = _api("GET", f"/credentials/schema/{cred_type.strip()}")
    if err:
        return (err + "\n(Vérifie le nom EXACT du type : telegramApi, smtp, httpHeaderAuth, "
                "httpBasicAuth, openAiApi, slackApi, postgres…)")
    props = (data or {}).get("properties") if isinstance(data, dict) else None
    fields = ", ".join(props.keys()) if isinstance(props, dict) else (json.dumps(data)[:300])
    req = (data or {}).get("required") if isinstance(data, dict) else None
    extra = f" — requis : {', '.join(req)}" if req else ""
    return f"Credential « {cred_type} » — champs : {fields}{extra}"


def create_n8n_credential(name: str, cred_type: str, data_json: str, user_confirmed: bool = False) -> str:
    """CRÉE une credential n8n (jeton Telegram, SMTP, clé API…) à référencer ensuite dans des nœuds.
    SENSIBLE (validation HITL). Consulte get_n8n_credential_schema pour les champs.
    data_json = JSON des champs (ex. {"accessToken":"123:abc"} pour telegramApi).
    ⚠️ Le secret n'est NI stocké NI journalisé par Athena : il est transmis directement à TON n8n."""
    if not (name or "").strip() or not (cred_type or "").strip():
        return "name et cred_type (ex. telegramApi) sont requis."
    try:
        d = json.loads(data_json) if isinstance(data_json, str) else data_json
        if not isinstance(d, dict):
            return "data_json doit être un OBJET JSON des champs de la credential."
    except Exception as e:
        return f"data_json JSON invalide : {e}"
    res, err = _api("POST", "/credentials", json_body={"name": name.strip(),
                                                       "type": cred_type.strip(), "data": d})
    if err:
        return "Création de credential refusée par n8n : " + err
    cid = (res or {}).get("id") if isinstance(res, dict) else None
    return (f"✅ Credential « {name} » (type {cred_type}) créée (id {cid}). "
            f"Pour l'utiliser : dans un nœud, ajoute \"credentials\": {{\"{cred_type}\": "
            f"{{\"id\": \"{cid}\", \"name\": \"{name}\"}}}} (le spec accepte un champ `credentials`).")


def delete_n8n_credential(credential_id: str, user_confirmed: bool = False) -> str:
    """SUPPRIME une credential n8n par son id. SENSIBLE (validation HITL)."""
    if not (credential_id or "").strip():
        return "Indique l'id de la credential à supprimer."
    _res, err = _api("DELETE", f"/credentials/{credential_id.strip()}")
    if err:
        return "Suppression refusée par n8n : " + err
    return f"🗑️ Credential {credential_id} supprimée."


for _f in (create_n8n_credential, delete_n8n_credential):
    _f._requires_approval = True
