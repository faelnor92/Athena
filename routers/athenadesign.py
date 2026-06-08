import os
import re
import json
import uuid
from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import HTMLResponse
from core import athenadesign_runner as runner
from core import athenadesign_generator as generator
from core import projects as code_projects  # PROJETS UNIFIÉS : même registre que la partie code

router = APIRouter(prefix="/api/athenadesign", tags=["AthenaDesign"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# MULTI-UTILISATEUR : une base de projets PAR UTILISATEUR (isolation). Un projet n'est
# accessible qu'à son propriétaire (lookup dans SA base → 404 sinon).
PROJECTS_DIR = os.path.join(BASE_DIR, "athenadesign_projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)
_LEGACY_FILE = os.path.join(BASE_DIR, "athenadesign_projects.json")  # ancienne base globale

# Ensure sandbox directory exists
SANDBOX_DIR = runner.SANDBOX_DIR
os.makedirs(SANDBOX_DIR, exist_ok=True)


# ── PROJETS UNIFIÉS code + design ─────────────────────────────────────────────
# La LISTE et la CRÉATION de projets délèguent à core.projects (le registre des projets de
# code) → un projet Athena porte à la fois le code (dossier) ET le design. Les données de
# design (versions/history/charte) restent indexées par le MÊME id de projet.
def _accessible_ids() -> set:
    try:
        return {p.get("id") for p in code_projects.list_projects()}
    except Exception:
        return set()


def _can_access(project_id: str) -> bool:
    return project_id in _accessible_ids()


def _project_name(project_id: str) -> str:
    try:
        p = next((x for x in code_projects.list_projects() if x.get("id") == project_id), None)
        return (p or {}).get("name", "Projet")
    except Exception:
        return "Projet"


def _new_design(project_id: str) -> dict:
    return {"id": project_id, "name": _project_name(project_id), "history": [], "versions": []}


# Types d'artefacts rendus comme une page web (aperçu/PDF/partage/raw).
_WEB_TYPES = ("html", "react", "mermaid")


def _web_render(version: dict) -> str:
    """Rend un artefact web en HTML autonome selon son type (react/mermaid → scaffold)."""
    t = version.get("type")
    code = version.get("code", "")
    if t == "react":
        return generator.react_scaffold(code)
    if t == "mermaid":
        return generator.mermaid_scaffold(code)
    return code


def _current_user(request: Request) -> str:
    """Utilisateur courant (posé par l'auth middleware) ; 'local' en mode sans auth."""
    u = getattr(request.state, "user", None)
    name = (u.get("username") if isinstance(u, dict) else None) or "local"
    return name


def _safe_user(user: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.-]", "_", user or "local").strip("_") or "local"
    return s[:64]


def _user_file(user: str) -> str:
    return os.path.join(PROJECTS_DIR, f"{_safe_user(user)}.json")


def read_db(user: str) -> dict:
    path = _user_file(user)
    if not os.path.exists(path):
        # Migration douce : l'ancienne base globale revient à l'utilisateur local/admin.
        if _safe_user(user) in ("local", "admin") and os.path.exists(_LEGACY_FILE):
            try:
                with open(_LEGACY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                write_db(user, data)
                return data
            except Exception:
                pass
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_db(user: str, data: dict):
    path = _user_file(user)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)  # écriture atomique


# ── Imports (références → contexte) : images, documents, capture web ──────────
def _extract_doc(data_url: str, name: str) -> str:
    """Texte d'un document fourni en data URL (PDF via pypdf, sinon décodage texte)."""
    import base64
    try:
        b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
        raw = base64.b64decode(b64)
    except Exception:
        return ""
    if name.lower().endswith(".pdf") or raw[:4] == b"%PDF":
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:20])
        except Exception:
            return ""
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _fetch_web_text(url: str) -> str:
    """Récupère le contenu d'une page (capture web) en TEXTE → contexte sans vision."""
    try:
        from tools import web_tools
        if hasattr(web_tools, "web_scrape"):
            return str(web_tools.web_scrape(url))[:8000]
    except Exception:
        pass
    if not re.match(r"^https?://", url or ""):
        return ""
    # Garde SSRF FAIL-CLOSED : si on ne peut pas vérifier l'URL, on ne fetch pas.
    try:
        from tools.net_guard import is_blocked_url
        if is_blocked_url(url):
            return ""
    except Exception:
        return ""
    try:
        import requests
        html = requests.get(url, timeout=8, headers={"User-Agent": "AthenaDesign/1.0"}).text
        return re.sub(r"<[^>]+>", " ", html)[:8000]
    except Exception:
        return ""


def _resolve_attachments(attachments) -> tuple:
    """Transforme les pièces jointes en (contexte_texte, images_data_urls). Les docs/web
    deviennent du TEXTE (utilisable SANS vision) ; les images restent des data URLs."""
    texts, images = [], []
    for a in (attachments or [])[:8]:
        if not isinstance(a, dict):
            continue
        kind = (a.get("kind") or "").lower()
        name = a.get("name") or ""
        if kind == "image" and a.get("data_url"):
            images.append(a["data_url"])
        elif kind == "web" and a.get("url"):
            txt = _fetch_web_text(a["url"])
            if txt:
                texts.append(f"[Capture web : {a['url']}]\n{txt}")
        elif kind == "document":
            txt = a.get("text") or _extract_doc(a.get("data_url", ""), name)
            if txt:
                texts.append(f"[Document : {name}]\n{txt[:8000]}")
        elif kind == "text" and a.get("text"):
            texts.append(f"[Référence]\n{a['text'][:8000]}")
    return ("\n\n".join(texts), images)


def _fetch_web_styles(url: str) -> str:
    """Récupère le HTML BRUT d'une page + ses CSS (blocs <style> et feuilles liées) pour en
    EXTRAIRE la charte (couleurs/typo). Garde SSRF (net_guard) + bornes (taille, nb de CSS)."""
    if not re.match(r"^https?://", url or ""):
        return ""
    # Garde SSRF FAIL-CLOSED : pas de vérif possible → on ne fetch pas.
    try:
        from tools.net_guard import is_blocked_url
        if is_blocked_url(url):
            return ""
    except Exception:
        return ""
    try:
        import requests
        from urllib.parse import urljoin
        html = requests.get(url, timeout=8, headers={"User-Agent": "AthenaDesign/1.0"}).text[:300000]
    except Exception:
        return ""
    css = html  # le HTML contient déjà <style> et style="…"
    # Feuilles de style liées (limitées à 5, 200 Ko chacune).
    for href in re.findall(r'<link[^>]+rel=["\']?stylesheet["\']?[^>]*href=["\']([^"\']+)["\']', html, re.I)[:5]:
        try:
            from tools.net_guard import is_blocked_url
            cu = urljoin(url, href)
            if is_blocked_url(cu):
                continue
            import requests as _rq
            css += "\n" + _rq.get(cu, timeout=6, headers={"User-Agent": "AthenaDesign/1.0"}).text[:200000]
        except Exception:
            continue
    return css


def extract_design_system(source: str) -> str:
    """Construit une charte de départ depuis du CSS/HTML/texte : couleurs (#hex/rgb) et
    polices (font-family) les plus fréquentes. Sert le 'design system support'."""
    if not source:
        return ""
    from collections import Counter
    colors = Counter(re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", source))
    fonts = Counter(re.findall(r"font-family\s*:\s*([^;\}\n]+)", source, re.IGNORECASE))
    lines = []
    if colors:
        top = ", ".join(c for c, _ in colors.most_common(8))
        lines.append(f"Couleurs de marque : {top}")
    if fonts:
        top = "; ".join(f.strip().strip('\"\'') for f, _ in fonts.most_common(3))
        lines.append(f"Typographie : {top}")
    return "\n".join(lines)


@router.get("/projects")
async def get_projects(request: Request):
    user = _current_user(request)
    db = read_db(user)
    # La liste = les projets Athena (partagés avec la partie code). versions_count = design.
    return [
        {
            "id": p.get("id"),
            "name": p.get("name", "Sans titre"),
            "updated_at": (db.get(p.get("id"), {}) or {}).get("updated_at", ""),
            "versions_count": len((db.get(p.get("id"), {}) or {}).get("versions", [])),
            "role": p.get("role"),
        } for p in code_projects.list_projects()
    ]

@router.post("/projects/new")
async def create_project(request: Request, payload: dict = Body(...)):
    user = _current_user(request)
    name = payload.get("name") or "Nouveau projet"
    # Crée un VRAI projet Athena (dossier code) → partagé avec l'espace Code.
    proj = code_projects.create_project(name)
    if not proj:
        raise HTTPException(status_code=400, detail="Création du projet impossible")
    db = read_db(user)
    db[proj["id"]] = _new_design(proj["id"])
    write_db(user, db)
    return db[proj["id"]]

@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(_current_user(request))
    return db.get(project_id) or _new_design(project_id)

@router.post("/chat")
async def chat_endpoint(request: Request, payload: dict = Body(...)):
    user = _current_user(request)
    project_id = payload.get("project_id")
    prompt = payload.get("prompt")
    # Par défaut, AthenaDesign utilise l'infra LLM d'Athena (provider 'athena') — pas un
    # chemin LLM séparé. 'mock' (hors-ligne) ou un provider externe + clé restent possibles.
    provider = payload.get("provider") or "athena"
    api_key = payload.get("api_key", "")
    model_name = payload.get("model_name", "")

    db = read_db(user)
    # Projet inexistant/non accessible → on crée un VRAI projet Athena (code+design).
    if not project_id or not _can_access(project_id):
        proj = code_projects.create_project(f"Design {prompt[:24]}".strip() if prompt else "Design")
        project_id = proj["id"] if proj else str(uuid.uuid4().hex[:8])
    project = db.get(project_id) or _new_design(project_id)
    db[project_id] = project

    # Imports (références) + charte du projet → contexte de génération.
    context_text, images = _resolve_attachments(payload.get("attachments"))
    design_system = project.get("design_system", "")

    result = await generator.generate_design(
        prompt=prompt,
        history=project["history"],
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        design_system=design_system,
        context_text=context_text,
        images=images,
    )

    project["history"].append({"role": "user", "content": prompt})
    project["history"].append({"role": "assistant", "content": result["explanation"]})

    version_num = len(project["versions"]) + 1
    new_version = {
        "version": version_num,
        "type": result["type"],
        "explanation": result["explanation"],
        "code": result["code"],
        "prompt": prompt,
        "comments": []
    }
    project["versions"].append(new_version)

    write_db(user, db)

    return {
        "project_id": project_id,
        "version": new_version,
        "history": project["history"]
    }

@router.post("/projects/{project_id}/versions/{version_num}/comments")
async def save_comment(request: Request, project_id: str, version_num: int, comment: dict = Body(...)):
    user = _current_user(request)
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(user)
    project = db.get(project_id) or _new_design(project_id)
    db[project_id] = project

    idx = version_num - 1
    if idx < 0 or idx >= len(project["versions"]):
        raise HTTPException(status_code=404, detail="Version introuvable")

    version = project["versions"][idx]
    if "comments" not in version:
        version["comments"] = []

    comment_id = str(uuid.uuid4().hex[:8])
    comment_data = {
        "id": comment_id,
        "text": comment.get("text", ""),
        "x": comment.get("x", 0),
        "y": comment.get("y", 0),
        "width": comment.get("width", 0),
        "height": comment.get("height", 0),
        "tool": comment.get("tool", "point"),
        "color": comment.get("color", "#ef4444"),
        "drawing_data": comment.get("drawing_data", ""),
        "resolved": False
    }

    version["comments"].append(comment_data)
    write_db(user, db)
    return comment_data

@router.post("/execute")
async def execute_endpoint(request: Request, payload: dict = Body(...)):
    project_id = payload.get("project_id")
    code = payload.get("code")

    if not project_id or not code:
        raise HTTPException(status_code=400, detail="Paramètres project_id et code requis")
    # Sécurité : project_id doit être un id hex (anti path-traversal sur le dossier sandbox)
    # ET appartenir à l'utilisateur courant (un user n'exécute que dans SES projets).
    if not re.fullmatch(r"[a-f0-9]{6,32}", str(project_id)):
        raise HTTPException(status_code=400, detail="project_id invalide")
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")

    execution_result = runner.execute_code(code, project_id)
    return execution_result


@router.post("/autofix")
async def autofix_endpoint(request: Request, payload: dict = Body(...)):
    """Auto-correction : exécute la dernière version PYTHON ; en cas d'erreur, renvoie le
    traceback au modèle pour corriger, ré-exécute, jusqu'à N essais (ATHENADESIGN_AUTOFIX_MAX).
    Les corrections sont ajoutées comme nouvelles versions. Indépendant du modèle."""
    user = _current_user(request)
    project_id = payload.get("project_id")
    if not project_id or not re.fullmatch(r"[a-f0-9]{6,32}", str(project_id)):
        raise HTTPException(status_code=400, detail="project_id invalide")
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(user)
    project = db.get(project_id) or _new_design(project_id)
    db[project_id] = project
    v = next((x for x in reversed(project.get("versions", [])) if x.get("type") == "python"), None)
    if not v:
        raise HTTPException(status_code=400, detail="Aucun script Python à corriger")

    max_tries = int(os.getenv("ATHENADESIGN_AUTOFIX_MAX", "2") or 2)
    code = v.get("code", "")
    result = runner.execute_code(code, project_id)
    attempts, fixed = 0, False
    while not result.get("success") and attempts < max_tries:
        attempts += 1
        err = (result.get("stderr") or "")[-2000:]
        fix_prompt = ("Le script Python ci-dessous a ÉCHOUÉ à l'exécution. Corrige-le pour qu'il "
                      "fonctionne, en gardant l'intention initiale. Renvoie le script complet.\n\n"
                      f"ERREUR:\n{err}\n\nCODE ACTUEL:\n{code}")
        gen = await generator.generate_design(
            prompt=fix_prompt, history=project.get("history", []),
            provider="athena", design_system=project.get("design_system", ""))
        new_code = (gen.get("code") or "").strip()
        if not new_code:
            break
        code = new_code
        vn = len(project["versions"]) + 1
        project["versions"].append({
            "version": vn, "type": gen.get("type", "python"),
            "explanation": f"🔧 Auto-correction {attempts} — {gen.get('explanation', '')}",
            "code": code, "prompt": "[auto-correction]", "comments": []})
        project.setdefault("history", []).append({"role": "user", "content": "[auto-correction] " + err[:200]})
        project["history"].append({"role": "assistant", "content": gen.get("explanation", "")})
        result = runner.execute_code(code, project_id)
        fixed = bool(result.get("success"))

    write_db(user, db)
    return {"success": result.get("success"), "fixed": fixed, "attempts": attempts,
            "result": result, "versions_count": len(project["versions"]),
            "latest_version": project["versions"][-1] if project["versions"] else None}

@router.get("/projects/{project_id}/versions/{version_num}/raw", response_class=HTMLResponse)
async def get_raw_html(request: Request, project_id: str, version_num: int):
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    project = read_db(_current_user(request)).get(project_id) or _new_design(project_id)

    idx = version_num - 1
    if idx < 0 or idx >= len(project["versions"]):
        raise HTTPException(status_code=404, detail="Version introuvable")

    version = project["versions"][idx]
    if version.get("type") not in _WEB_TYPES:
        raise HTTPException(status_code=400, detail="Seuls les artefacts web (HTML/React/Mermaid) peuvent être affichés en brut")
    return HTMLResponse(content=_web_render(version), status_code=200)


@router.get("/file/{project_id}/{filename}")
async def get_sandbox_file(request: Request, project_id: str, filename: str):
    """Sert un fichier GÉNÉRÉ (plot .png, plotly .html, .pptx…) — AUTHENTIFIÉ (sous /api/ →
    couvert par le middleware) + OWNERSHIP (le projet doit appartenir à l'utilisateur).
    Remplace l'ancien mount statique /sandbox public. Garde anti path-traversal."""
    from fastapi.responses import FileResponse
    if not re.fullmatch(r"[a-f0-9]{6,32}", str(project_id)):
        raise HTTPException(status_code=400, detail="project_id invalide")
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", str(filename)) or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="nom de fichier invalide")
    base = os.path.realpath(os.path.join(SANDBOX_DIR, project_id))
    real = os.path.realpath(os.path.join(base, filename))
    if real != base and not real.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="chemin invalide")
    if not os.path.isfile(real):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(real)


@router.get("/projects/{project_id}/design-system")
async def get_design_system(request: Request, project_id: str):
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(_current_user(request))
    return {"design_system": (db.get(project_id) or {}).get("design_system", "")}


@router.put("/projects/{project_id}/design-system")
async def set_design_system(request: Request, project_id: str, payload: dict = Body(...)):
    """Définit la charte du projet. `design_system` = texte direct ; `source` = CSS/HTML/site
    dont on EXTRAIT couleurs+typo (design system support). Les deux peuvent être combinés."""
    user = _current_user(request)
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(user)
    db.setdefault(project_id, _new_design(project_id))
    ds = (payload.get("design_system") or "").strip()
    source = payload.get("source") or ""
    url = (payload.get("url") or "").strip()
    if url:
        # Capture web : on récupère HTML+CSS brut de la page et on en extrait la charte.
        source = (source + "\n" + _fetch_web_styles(url)).strip()
    if source:
        extracted = extract_design_system(source)
        ds = (ds + ("\n" if ds and extracted else "") + extracted).strip()
    db[project_id]["design_system"] = ds[:4000]
    write_db(user, db)
    return {"design_system": db[project_id]["design_system"]}


@router.post("/export/pdf")
async def export_pdf(request: Request, payload: dict = Body(...)):
    """Exporte un design HTML en PDF (Chromium headless --print-to-pdf). Ownership requis."""
    import tempfile
    import subprocess
    from fastapi.responses import FileResponse
    from tools import browser_tools
    user = _current_user(request)
    project_id = payload.get("project_id")
    if not project_id or not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    project = read_db(user).get(project_id) or _new_design(project_id)
    # Code à exporter : explicite, sinon la version demandée, sinon la dernière HTML.
    code = payload.get("code")
    if not code:
        versions = project.get("versions", [])
        vnum = payload.get("version_num")
        v = None
        if isinstance(vnum, int) and 1 <= vnum <= len(versions):
            v = versions[vnum - 1]
        else:
            v = next((x for x in reversed(versions) if x.get("type") in _WEB_TYPES), None)
        if not v or v.get("type") not in _WEB_TYPES:
            raise HTTPException(status_code=400, detail="Aucun design web (HTML/React/Mermaid) à exporter")
        code = _web_render(v)
    chrome = browser_tools._find_chromium()
    if not chrome:
        raise HTTPException(status_code=503, detail="Export PDF indisponible : aucun navigateur "
                            "Chromium trouvé (installe chromium ou définis CHROMIUM_BIN).")
    d = tempfile.mkdtemp(prefix="ad-pdf-")
    html_path = os.path.join(d, "design.html")
    pdf_path = os.path.join(d, "design.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
             "--disable-extensions", f"--user-data-dir={os.path.join(d, 'profile')}",
             "--virtual-time-budget=8000", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", f"file://{html_path}"],
            capture_output=True, timeout=45,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec de l'export PDF : {e}")
    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=500, detail="Échec de l'export PDF (aucune sortie produite).")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{project.get('name', 'design')}.pdf")


# ── Partage en lecture seule par jeton (non énumérable) ───────────────────────
_SHARED_INDEX = os.path.join(BASE_DIR, "athenadesign_shared.json")


def _read_shared() -> dict:
    try:
        with open(_SHARED_INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_shared(data: dict):
    tmp = _SHARED_INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _SHARED_INDEX)


def _resolve_shared(token: str):
    """token → projet (ou None). Vérifie que le projet porte TOUJOURS ce jeton (révocation)."""
    if not re.fullmatch(r"[a-f0-9]{8,64}", str(token or "")):
        return None
    ent = _read_shared().get(token)
    if not ent:
        return None
    proj = read_db(ent.get("user", "")).get(ent.get("pid", ""))
    if not proj or proj.get("share_token") != token:
        return None
    return proj


@router.post("/projects/{project_id}/share")
async def share_project(request: Request, project_id: str):
    user = _current_user(request)
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(user)
    proj = db.get(project_id) or _new_design(project_id)
    db[project_id] = proj
    token = proj.get("share_token")
    if not token:
        token = uuid.uuid4().hex
        proj["share_token"] = token
        write_db(user, db)
        idx = _read_shared()
        idx[token] = {"user": user, "pid": project_id}
        _write_shared(idx)
    return {"token": token, "url": f"/api/athenadesign/shared/{token}/view"}


@router.delete("/projects/{project_id}/share")
async def unshare_project(request: Request, project_id: str):
    user = _current_user(request)
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(user)
    token = (db.get(project_id) or {}).pop("share_token", None) if project_id in db else None
    write_db(user, db)
    if token:
        idx = _read_shared()
        idx.pop(token, None)
        _write_shared(idx)
    return {"ok": True}


@router.get("/shared/{token}")
async def shared_project(token: str):
    """PUBLIC (lecture seule) : métadonnées + dernière version d'un projet partagé."""
    proj = _resolve_shared(token)
    if not proj:
        raise HTTPException(status_code=404, detail="Lien de partage invalide ou révoqué")
    versions = proj.get("versions", [])
    return {"name": proj.get("name", "Design partagé"),
            "version": versions[-1] if versions else None,
            "versions_count": len(versions)}


@router.get("/shared/{token}/view", response_class=HTMLResponse)
async def shared_view(token: str):
    """PUBLIC : rend le dernier design web partagé. SÉCURITÉ : le design (potentiellement créé
    par un autre utilisateur) est rendu dans une IFRAME SANDBOX sans `allow-same-origin` → son
    JavaScript s'exécute dans une origine nulle et ne peut PAS lire le localStorage d'Athena
    (jeton de session). Neutralise le vol de jeton via un lien partagé."""
    proj = _resolve_shared(token)
    if not proj:
        raise HTTPException(status_code=404, detail="Lien de partage invalide ou révoqué")
    v = next((x for x in reversed(proj.get("versions", [])) if x.get("type") in _WEB_TYPES), None)
    if not v:
        return HTMLResponse("<h1>Ce design partagé n'a pas d'aperçu web.</h1>", status_code=200)
    inner = _web_render(v)
    esc = inner.replace("&", "&amp;").replace('"', "&quot;")
    wrapper = (
        "<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>Design partagé</title><style>html,body{margin:0;height:100%}"
        "iframe{border:0;width:100%;height:100vh;display:block}</style></head><body>"
        f"<iframe sandbox=\"allow-scripts allow-popups allow-forms allow-modals\" srcdoc=\"{esc}\"></iframe>"
        "</body></html>"
    )
    return HTMLResponse(content=wrapper, status_code=200)
