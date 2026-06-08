import os
import re
import json
import uuid
from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import HTMLResponse
from core import athenadesign_runner as runner
from core import athenadesign_generator as generator

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
    try:
        import requests
        from core.net_guard import assert_safe_url  # garde SSRF si dispo
        try:
            assert_safe_url(url)
        except Exception:
            pass
        html = requests.get(url, timeout=8).text
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
    db = read_db(_current_user(request))
    return [
        {
            "id": pid,
            "name": pdata.get("name", "Sans titre"),
            "updated_at": pdata.get("updated_at", ""),
            "versions_count": len(pdata.get("versions", []))
        } for pid, pdata in db.items()
    ]

@router.post("/projects/new")
async def create_project(request: Request, payload: dict = Body(...)):
    user = _current_user(request)
    project_id = str(uuid.uuid4().hex[:12])
    name = payload.get("name", f"Projet {project_id[:4]}")

    db = read_db(user)
    db[project_id] = {
        "id": project_id,
        "name": name,
        "created_at": uuid.uuid4().hex,
        "updated_at": uuid.uuid4().hex,
        "history": [],
        "versions": []
    }
    write_db(user, db)
    return db[project_id]

@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    db = read_db(_current_user(request))
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return db[project_id]

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
    if not project_id or project_id not in db:
        project_id = str(uuid.uuid4().hex[:12])
        db[project_id] = {
            "id": project_id,
            "name": f"Conversation {project_id[:4]}",
            "history": [],
            "versions": []
        }

    project = db[project_id]

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
    db = read_db(user)
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    project = db[project_id]

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
    if project_id not in read_db(_current_user(request)):
        raise HTTPException(status_code=404, detail="Projet introuvable")

    execution_result = runner.execute_code(code, project_id)
    return execution_result

@router.get("/projects/{project_id}/versions/{version_num}/raw", response_class=HTMLResponse)
async def get_raw_html(request: Request, project_id: str, version_num: int):
    db = read_db(_current_user(request))
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    project = db[project_id]

    idx = version_num - 1
    if idx < 0 or idx >= len(project["versions"]):
        raise HTTPException(status_code=404, detail="Version introuvable")

    version = project["versions"][idx]
    if version.get("type") != "html":
        raise HTTPException(status_code=400, detail="Seuls les artefacts de type HTML peuvent être affichés de manière brute")

    return HTMLResponse(content=version["code"], status_code=200)


@router.get("/file/{project_id}/{filename}")
async def get_sandbox_file(request: Request, project_id: str, filename: str):
    """Sert un fichier GÉNÉRÉ (plot .png, plotly .html, .pptx…) — AUTHENTIFIÉ (sous /api/ →
    couvert par le middleware) + OWNERSHIP (le projet doit appartenir à l'utilisateur).
    Remplace l'ancien mount statique /sandbox public. Garde anti path-traversal."""
    from fastapi.responses import FileResponse
    if not re.fullmatch(r"[a-f0-9]{6,32}", str(project_id)):
        raise HTTPException(status_code=400, detail="project_id invalide")
    if project_id not in read_db(_current_user(request)):
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
    db = read_db(_current_user(request))
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return {"design_system": db[project_id].get("design_system", "")}


@router.put("/projects/{project_id}/design-system")
async def set_design_system(request: Request, project_id: str, payload: dict = Body(...)):
    """Définit la charte du projet. `design_system` = texte direct ; `source` = CSS/HTML/site
    dont on EXTRAIT couleurs+typo (design system support). Les deux peuvent être combinés."""
    user = _current_user(request)
    db = read_db(user)
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    ds = (payload.get("design_system") or "").strip()
    source = payload.get("source") or ""
    if source:
        extracted = extract_design_system(source)
        ds = (ds + ("\n" if ds and extracted else "") + extracted).strip()
    db[project_id]["design_system"] = ds[:4000]
    write_db(user, db)
    return {"design_system": db[project_id]["design_system"]}
