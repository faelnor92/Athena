import os
import re
import json
import uuid
from typing import List
from fastapi import APIRouter, HTTPException, Body, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
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
    ids = set()
    # IDs from unified code projects
    try:
        ids.update({p.get("id") for p in code_projects.list_projects()})
    except Exception:
        pass
    # IDs from legacy athenadesign JSON store (if present)
    try:
        if os.path.exists(_LEGACY_FILE):
            with open(_LEGACY_FILE, "r", encoding="utf-8") as f:
                legacy_data = json.load(f)
            if isinstance(legacy_data, dict):
                ids.update(legacy_data.keys())
    except Exception:
        pass
    return ids


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

@router.post("/projects/{project_id}/import-code")
async def import_code(request: Request, project_id: str, payload: dict = Body(...)):
    """Amorce un projet avec du code EXISTANT (ex. artifact venu du chat) en l'ajoutant comme
    nouvelle version — sans appel LLM. Sert de pont « Ouvrir dans AthenaDesign »."""
    user = _current_user(request)
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    code = (payload.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code vide.")
    if len(code) > 2_000_000:   # borne anti-abus/DoS (~2 Mo) — un artefact reste raisonnable
        raise HTTPException(status_code=413, detail="Code trop volumineux (max 2 Mo).")
    vtype = (payload.get("type") or "html").strip().lower()
    if vtype not in ("html", "react", "mermaid", "python"):
        vtype = "html"
    db = read_db(user)
    project = db.get(project_id) or _new_design(project_id)
    db[project_id] = project
    new_version = {
        "version": len(project.get("versions", [])) + 1,
        "type": vtype,
        "explanation": payload.get("explanation") or "Code importé.",
        "code": code,
        "prompt": "(import)",
        "comments": [], "tweaks": [], "suggestions": [], "usage": {},
    }
    project.setdefault("versions", []).append(new_version)
    write_db(user, db)
    try:
        _mirror_version_to_workspace(project_id, new_version)
    except Exception:
        pass
    return {"project_id": project_id, "version": new_version}


@router.post("/projects/{project_id}/rename")
async def rename_design_project(request: Request, project_id: str, payload: dict = Body(...)):
    """Renomme un projet (registre unifié code+design)."""
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom vide.")
    if not code_projects.rename(project_id, name):
        raise HTTPException(status_code=404, detail="Renommage impossible.")
    return {"status": "success", "id": project_id, "name": name}


@router.delete("/projects/{project_id}")
async def delete_design_project(request: Request, project_id: str, remove_files: bool = True):
    """Supprime un projet (registre UNIFIÉ avec la partie code) : dossier code + entrée
    du registre + base design associée."""
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if not code_projects.delete(project_id, remove_files=remove_files):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    try:  # nettoie aussi l'entrée design (best-effort)
        user = _current_user(request)
        db = read_db(user)
        if project_id in db:
            del db[project_id]
            write_db(user, db)
    except Exception:
        pass
    return {"status": "deleted"}

@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    db = read_db(_current_user(request))
    return db.get(project_id) or _new_design(project_id)

def _project_path(project_id: str):
    """Dossier de travail (filesystem) d'un projet, PARTAGÉ avec la partie Code.
    None si le projet n'a pas de dossier accessible. Réutilise le registre code."""
    try:
        p = next((x for x in code_projects.list_projects() if x.get("id") == project_id), None)
        path = (p or {}).get("path")
        return os.path.realpath(path) if path else None
    except Exception:
        return None


def _safe_join(base: str, rel: str):
    """Joint base + rel en refusant toute échappée hors de base (anti-traversée)."""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    # On retire les segments dangereux ('..', '.') tout en gardant l'arborescence.
    parts = [seg for seg in rel.split("/") if seg not in ("", ".", "..")]
    if not parts:
        return None
    dest = os.path.realpath(os.path.join(base, *parts))
    if os.path.commonpath([dest, base]) != base:
        return None
    return dest


# Limites de sécurité de l'upload de dossier.
_UPLOAD_MAX_FILES = 2000
_UPLOAD_MAX_BYTES = 50 * 1024 * 1024  # 50 Mo / fichier
_UPLOAD_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}


@router.post("/projects/{project_id}/upload")
async def upload_folder(request: Request, project_id: str,
                        files: List[UploadFile] = File(...),
                        paths: List[str] = Form(...)):
    """Importe un DOSSIER COMPLET (sous-dossiers inclus) dans le workspace du projet —
    le MÊME dossier que la partie Code (#5). Le frontend envoie chaque fichier avec son
    chemin relatif (webkitRelativePath). Anti-traversée + filtres (poids, dossiers lourds)."""
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    base = _project_path(project_id)
    if not base:
        raise HTTPException(status_code=409, detail="Ce projet n'a pas de dossier de travail.")
    os.makedirs(base, exist_ok=True)
    if len(files) > _UPLOAD_MAX_FILES:
        raise HTTPException(status_code=413, detail=f"Trop de fichiers (max {_UPLOAD_MAX_FILES}).")

    written, skipped = 0, []
    for f, rel in zip(files, paths):
        # On ignore les répertoires lourds usuels (le premier segment est souvent le nom du dossier racine).
        segs = (rel or "").replace("\\", "/").split("/")
        if any(s in _UPLOAD_SKIP_DIRS for s in segs):
            skipped.append(rel); continue
        dest = _safe_join(base, rel)
        if not dest:
            skipped.append(rel); continue
        data = await f.read()
        if len(data) > _UPLOAD_MAX_BYTES:
            skipped.append(rel); continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as out:
            out.write(data)
        written += 1
    return {"uploaded": written, "skipped": len(skipped), "skipped_paths": skipped[:50]}


# Marqueur de provenance : quel fichier du workspace est « possédé » par Design (écrit par
# ses générations). Évite d'écraser un index.html écrit à la main / par la partie Code.
_DESIGN_MARKER = ".athenadesign.json"


def _design_owned_entry(base: str):
    """Fichier que Design a lui-même écrit dans ce workspace (None si aucun)."""
    try:
        with open(os.path.join(base, _DESIGN_MARKER), "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("entry")
    except Exception:
        return None


def _workspace_entry(base: str):
    """Fichier HTML « page d'entrée » prévisualisable d'un workspace : le fichier possédé
    par Design en priorité, puis index.html, puis le premier *.htm(l) à la racine."""
    if not base or not os.path.isdir(base):
        return None
    owned = _design_owned_entry(base)
    if owned and os.path.isfile(os.path.join(base, owned)):
        return owned
    for cand in ("index.html", "index.htm"):
        if os.path.isfile(os.path.join(base, cand)):
            return cand
    try:
        for name in sorted(os.listdir(base)):
            if name.lower().endswith((".html", ".htm")) and os.path.isfile(os.path.join(base, name)):
                return name
    except Exception:
        pass
    return None


# Sous-dossier DÉDIÉ aux productions de Design dans le projet : isole le design du code de
# base (on ne touche JAMAIS aux fichiers racine écrits à la main / par la partie Code).
_DESIGN_SUBDIR = "design"


def _split_html_assets(html: str):
    """Extrait les <style> et <script> INLINE d'une page HTML autonome vers des fichiers
    séparés (style.css / script.js), et relie la page via <link>/<script src>. Laisse en
    place les scripts EXTERNES (src=…) et les types spéciaux (importmap, application/json).
    Renvoie (html_relié, css, js). Permet de retrouver une structure multi-fichiers."""
    css_parts, js_parts = [], []

    def _take_style(m):
        css_parts.append(m.group(1))
        return ""

    out = re.sub(r"<style[^>]*>(.*?)</style>", _take_style, html, flags=re.DOTALL | re.IGNORECASE)

    def _take_script(m):
        attrs = m.group(1) or ""
        if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
            return m.group(0)  # script externe (CDN…) : on n'y touche pas
        tm = re.search(r"\btype\s*=\s*[\"']?([^\"'\s>]+)", attrs, re.IGNORECASE)
        if tm and tm.group(1).lower() not in ("text/javascript", "module"):
            return m.group(0)  # importmap / application/json / etc. : laissé inline
        js_parts.append(m.group(2))
        return ""

    out = re.sub(r"<script([^>]*)>(.*?)</script>", _take_script, out, flags=re.DOTALL | re.IGNORECASE)

    css = "\n\n".join(p.strip() for p in css_parts if p.strip())
    js = "\n\n".join(p.strip() for p in js_parts if p.strip())
    if css:
        link = '<link rel="stylesheet" href="style.css">'
        out = (re.sub(r"</head>", link + "\n</head>", out, count=1, flags=re.IGNORECASE)
               if re.search(r"</head>", out, re.IGNORECASE) else link + "\n" + out)
    if js:
        tag = '<script src="script.js"></script>'
        out = (re.sub(r"</body>", tag + "\n</body>", out, count=1, flags=re.IGNORECASE)
               if re.search(r"</body>", out, re.IGNORECASE) else out + "\n" + tag)
    return out, css, js


def _mirror_version_to_workspace(project_id: str, version: dict):
    """Écrit l'artefact généré par Design comme VRAI fichier dans le sous-dossier `design/`
    du workspace du projet (partagé avec le Code, #5) → visible/éditable côté Code, SANS
    jamais toucher au code de base à la racine. Best-effort (n'interrompt pas la génération)."""
    base = _project_path(project_id)
    if not base:
        return
    t = version.get("type")
    try:
        ddir = os.path.join(base, _DESIGN_SUBDIR)
        os.makedirs(ddir, exist_ok=True)
        if t == "html":
            # Page HTML autonome → on sépare le CSS/JS inline en fichiers dédiés pour
            # retrouver une structure multi-fichiers (style.css / script.js) côté Code.
            html_out, css, js = _split_html_assets(_web_render(version))
            with open(os.path.join(ddir, "index.html"), "w", encoding="utf-8") as f:
                f.write(html_out)
            # Nettoie d'anciens fichiers si la nouvelle version n'en produit plus.
            for rel, content in (("style.css", css), ("script.js", js)):
                p = os.path.join(ddir, rel)
                if content:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(content)
                elif os.path.isfile(p):
                    os.remove(p)
            entry = f"{_DESIGN_SUBDIR}/index.html"
        elif t in _WEB_TYPES:
            # react/mermaid : scaffolds à CDN, gardés en un seul fichier autonome.
            with open(os.path.join(ddir, "index.html"), "w", encoding="utf-8") as f:
                f.write(_web_render(version))
            entry = f"{_DESIGN_SUBDIR}/index.html"
        elif t == "python":
            with open(os.path.join(ddir, "design.py"), "w", encoding="utf-8") as f:
                f.write(version.get("code", ""))
            entry = None  # pas une page web prévisualisable
        else:
            entry = None
        if entry:
            with open(os.path.join(base, _DESIGN_MARKER), "w", encoding="utf-8") as f:
                json.dump({"entry": entry}, f)
    except Exception:
        pass


def _base_html_entry(base: str):
    """Page web du CODE DE BASE à la racine (hors sous-dossier `design/`), ignorant le
    marqueur Design : index.html prioritaire, sinon premier *.htm(l) racine. None si aucun."""
    if not base or not os.path.isdir(base):
        return None
    for cand in ("index.html", "index.htm"):
        if os.path.isfile(os.path.join(base, cand)):
            return cand
    try:
        for name in sorted(os.listdir(base)):
            if name == _DESIGN_SUBDIR:
                continue
            if name.lower().endswith((".html", ".htm")) and os.path.isfile(os.path.join(base, name)):
                return name
    except Exception:
        pass
    return None


def _read_base_code(project_id: str, max_total: int = 60000, max_file: int = 40000) -> str:
    """Lit le CODE DE BASE du projet (page d'entrée racine + CSS/JS compagnons à la racine,
    hors `design/`) pour le fournir au générateur comme point de départ. Bornes de taille
    pour maîtriser les tokens. '' si le projet n'a pas de code de base."""
    base = _project_path(project_id)
    if not base:
        return ""
    entry = _base_html_entry(base)
    if not entry:
        return ""
    chunks, total = [], 0

    def _add(rel: str):
        nonlocal total
        p = _safe_join(base, rel)
        if not p or not os.path.isfile(p):
            return
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                txt = f.read(max_file + 1)
        except Exception:
            return
        if len(txt) > max_file:
            txt = txt[:max_file] + "\n/* …tronqué… */"
        if total + len(txt) > max_total:
            return
        total += len(txt)
        chunks.append(f"--- {rel} ---\n{txt}")

    _add(entry)
    try:
        for name in sorted(os.listdir(base)):
            if name == _DESIGN_SUBDIR:
                continue
            if name.lower().endswith((".css", ".js")) and os.path.isfile(os.path.join(base, name)):
                _add(name)
    except Exception:
        pass
    return "\n\n".join(chunks)


@router.get("/projects/{project_id}/sources")
async def project_sources(request: Request, project_id: str):
    """Sources prévisualisables d'un projet : `base` = page du code d'origine (racine,
    intacte) ; `design` = page générée par Design (`design/index.html`). Permet à l'UI de
    proposer une bascule « Code de base / Design » quand les deux coexistent."""
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    base = _project_path(project_id)
    design_rel = f"{_DESIGN_SUBDIR}/index.html"
    has_design = bool(base) and os.path.isfile(os.path.join(base, design_rel))
    return {
        "base": _base_html_entry(base) if base else None,
        "design": design_rel if has_design else None,
    }


@router.get("/projects/{project_id}/workspace-entry")
async def workspace_entry(request: Request, project_id: str):
    """Indique la page web prévisualisable du workspace du projet (partagé avec le Code).
    Permet à Design d'afficher un projet créé/édité côté Code même sans 'version' Design."""
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return {"entry": _workspace_entry(_project_path(project_id))}


@router.get("/projects/{project_id}/workspace/{file_path:path}")
async def workspace_file(request: Request, project_id: str, file_path: str):
    """Sert un fichier du workspace du projet (aperçu live des pages + assets relatifs).
    Anti-traversée : le chemin est assaini et confiné au dossier du projet."""
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    base = _project_path(project_id)
    if not base:
        raise HTTPException(status_code=404, detail="Pas de dossier de travail.")
    dest = _safe_join(base, file_path)
    if not dest or not os.path.isfile(dest):
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return FileResponse(dest)


def _prepare_design_chat(user: str, payload: dict) -> dict:
    """Contexte de génération commun à /chat et /chat/stream : projet (créé si besoin), charte,
    références (imports), code de base. Par défaut provider 'athena' (infra LLM d'Athena)."""
    project_id = payload.get("project_id")
    prompt = payload.get("prompt")
    db = read_db(user)
    # Projet inexistant/non accessible → on crée un VRAI projet Athena (code+design).
    if not project_id or not _can_access(project_id):
        proj = code_projects.create_project(f"Design {prompt[:24]}".strip() if prompt else "Design")
        project_id = proj["id"] if proj else str(uuid.uuid4().hex[:8])
    project = db.get(project_id) or _new_design(project_id)
    db[project_id] = project
    context_text, images = _resolve_attachments(payload.get("attachments"))
    return {
        "db": db, "project_id": project_id, "project": project, "prompt": prompt,
        "provider": payload.get("provider") or "athena",
        "api_key": payload.get("api_key", ""),
        "model_name": payload.get("model_name", ""),
        "design_system": project.get("design_system", ""),
        "context_text": context_text, "images": images,
        # CODE DE BASE du projet → on PART de l'existant au lieu d'inventer une page générique.
        "base_code": _read_base_code(project_id),
    }


def _persist_design_version(user: str, ctx: dict, result: dict) -> dict:
    """Ajoute l'échange à l'historique + une nouvelle version, télémétrie globale, miroir
    workspace (fichier sous design/). Renvoie la version créée. Commun à /chat et /chat/stream."""
    project = ctx["project"]
    project["history"].append({"role": "user", "content": ctx["prompt"]})
    project["history"].append({"role": "assistant", "content": result.get("explanation") or ""})
    _usage = result.get("usage") or {}
    new_version = {
        "version": len(project["versions"]) + 1,
        "type": result["type"],
        "explanation": result.get("explanation") or "",
        "code": result["code"],
        "prompt": ctx["prompt"],
        "comments": [], "tweaks": result.get("tweaks", []),
        "suggestions": result.get("suggestions", []), "usage": _usage,
    }
    project["versions"].append(new_version)
    try:
        _pt = int(_usage.get("prompt_tokens", 0) or 0)
        _ct = int(_usage.get("completion_tokens", 0) or 0)
        if _pt or _ct:
            from core.state import TELEMETRY, get_model_cost
            TELEMETRY["total_tokens"] += _pt + _ct
            TELEMETRY["total_cost"] += get_model_cost(ctx["model_name"] or "default", _pt, _ct)
            TELEMETRY["total_queries"] += 1
    except Exception:
        pass
    write_db(user, ctx["db"])
    _mirror_version_to_workspace(ctx["project_id"], new_version)
    return new_version


@router.post("/chat")
async def chat_endpoint(request: Request, payload: dict = Body(...)):
    user = _current_user(request)
    ctx = _prepare_design_chat(user, payload)
    result = await generator.generate_design(
        prompt=ctx["prompt"], history=ctx["project"]["history"], provider=ctx["provider"],
        api_key=ctx["api_key"], model_name=ctx["model_name"], design_system=ctx["design_system"],
        context_text=ctx["context_text"], images=ctx["images"], base_code=ctx["base_code"])
    version = _persist_design_version(user, ctx, result)
    return {"project_id": ctx["project_id"], "version": version, "history": ctx["project"]["history"]}


@router.post("/chat/stream")
async def chat_stream(request: Request, payload: dict = Body(...)):
    """Comme /chat mais en STREAMING (Server-Sent Events) : diffuse le code généré
    token-par-token (ressenti « live » façon Claude Design), puis émet la version finale
    (`event: done`). Chemin Athena uniquement ; un provider externe retombe sur une génération
    non-streamée (un seul `event: done`)."""
    import asyncio
    import json as _json
    import queue as _queue
    import threading
    from fastapi.responses import StreamingResponse

    user = _current_user(request)
    ctx = _prepare_design_chat(user, payload)

    def _sse(event: str, data: dict) -> str:
        prefix = f"event: {event}\n" if event else ""
        return prefix + "data: " + _json.dumps(data, ensure_ascii=False) + "\n\n"

    # Provider EXTERNE : pas de streaming token → on génère puis on émet la version finale.
    if ctx["provider"] not in ("athena", "", None):
        result = await generator.generate_design(
            prompt=ctx["prompt"], history=ctx["project"]["history"], provider=ctx["provider"],
            api_key=ctx["api_key"], model_name=ctx["model_name"], design_system=ctx["design_system"],
            context_text=ctx["context_text"], images=ctx["images"], base_code=ctx["base_code"])
        version = _persist_design_version(user, ctx, result)

        async def _one():
            yield _sse("done", {"project_id": ctx["project_id"], "version": version})
        return StreamingResponse(_one(), media_type="text/event-stream")

    async def event_gen():
        q: "_queue.Queue" = _queue.Queue()
        out = {}

        def worker():
            try:
                out["res"] = generator._generate_via_athena(
                    ctx["prompt"], ctx["project"]["history"], model_name=ctx["model_name"],
                    design_system=ctx["design_system"], context_text=ctx["context_text"],
                    images=ctx["images"], base_code=ctx["base_code"],
                    on_delta=lambda t: q.put(("token", t)))
            except Exception as e:  # noqa: BLE001
                out["err"] = str(e)
            finally:
                q.put(("end", None))

        threading.Thread(target=worker, name="athenadesign-stream", daemon=True).start()
        loop = asyncio.get_event_loop()
        while True:
            kind, data = await loop.run_in_executor(None, q.get)
            if kind == "token":
                yield _sse("", {"token": data})
            else:
                break
        if "res" in out:
            version = _persist_design_version(user, ctx, out["res"])
            yield _sse("done", {"project_id": ctx["project_id"], "version": version})
        else:
            yield _sse("error", {"error": out.get("err", "échec de génération")})

    return StreamingResponse(event_gen(), media_type="text/event-stream")

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
        "tag_name": comment.get("tag_name", ""),
        "tag_text": comment.get("tag_text", ""),
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
    provider = payload.get("provider") or "athena"
    api_key = payload.get("api_key", "")
    model_name = payload.get("model_name", "")
    error_message = payload.get("error_message")

    v = project.get("versions", [])[-1] if project.get("versions") else None
    if not v:
        raise HTTPException(status_code=400, detail="Aucune version disponible pour correction")

    fixed = False
    attempts = 0

    if error_message or v.get("type") in ("html", "react"):
        # Web auto-fix (HTML/React browser console runtime errors)
        attempts = 1
        code = v.get("code", "")
        err = str(error_message or "Erreur d'exécution inconnue")[:2000]
        fix_prompt = (
            "L'aperçu Web (HTML/React) ci-dessous a généré une erreur JavaScript à l'exécution. "
            "Corrige le code pour qu'il fonctionne correctement sans cette erreur, en conservant "
            "toute l'intention initiale, le style, les fonctionnalités et les bibliothèques CDN. "
            "Renvoie le code complet de la page.\n\n"
            f"ERREUR:\n{err}\n\nCODE ACTUEL:\n{code}"
        )
        gen = await generator.generate_design(
            prompt=fix_prompt, history=project.get("history", []),
            provider=provider, api_key=api_key, model_name=model_name,
            design_system=project.get("design_system", "")
        )
        new_code = (gen.get("code") or "").strip()
        if new_code:
            code = new_code
            vn = len(project["versions"]) + 1
            project["versions"].append({
                "version": vn,
                "type": gen.get("type", v.get("type", "html")),
                "explanation": f"🔧 Auto-correction Web — {gen.get('explanation', '')}",
                "code": code,
                "prompt": "[auto-correction web]",
                "comments": [],
                "tweaks": gen.get("tweaks", []),
                "suggestions": gen.get("suggestions", [])
            })
            project.setdefault("history", []).append({"role": "user", "content": "[auto-correction web] " + err[:200]})
            project["history"].append({"role": "assistant", "content": gen.get("explanation", "")})
            fixed = True
        
        write_db(user, db)
        _mirror_version_to_workspace(project_id, project["versions"][-1])
        return {
            "success": True,
            "fixed": fixed,
            "attempts": attempts,
            "versions_count": len(project["versions"]),
            "latest_version": project["versions"][-1]
        }
    else:
        # Python script auto-fix
        max_tries = int(os.getenv("ATHENADESIGN_AUTOFIX_MAX", "2") or 2)
        code = v.get("code", "")
        result = runner.execute_code(code, project_id)
        while not result.get("success") and attempts < max_tries:
            attempts += 1
            err = (result.get("stderr") or "")[-2000:]
            fix_prompt = ("Le script Python ci-dessous a ÉCHOUÉ à l'exécution. Corrige-le pour qu'il "
                          "fonctionne, en gardant l'intention initiale. Renvoie le script complet.\n\n"
                          f"ERREUR:\n{err}\n\nCODE ACTUEL:\n{code}")
            gen = await generator.generate_design(
                prompt=fix_prompt, history=project.get("history", []),
                provider=provider, api_key=api_key, model_name=model_name,
                design_system=project.get("design_system", ""))
            new_code = (gen.get("code") or "").strip()
            if not new_code:
                break
            code = new_code
            vn = len(project["versions"]) + 1
            project["versions"].append({
                "version": vn, "type": gen.get("type", "python"),
                "explanation": f"🔧 Auto-correction {attempts} — {gen.get('explanation', '')}",
                "code": code, "prompt": "[auto-correction]", "comments": [],
                "tweaks": gen.get("tweaks", []),
                "suggestions": gen.get("suggestions", [])})
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
@router.get("/projects/{project_id}/versions/{version_num}/handoff")
async def export_handoff_bundle(request: Request, project_id: str, version_num: int):
    import zipfile
    import io
    from fastapi.responses import StreamingResponse
    
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    
    user = _current_user(request)
    project = read_db(user).get(project_id) or _new_design(project_id)

    idx = version_num - 1
    if idx < 0 or idx >= len(project["versions"]):
        raise HTTPException(status_code=404, detail="Version introuvable")

    version = project["versions"][idx]
    v_type = version.get("type", "html")
    code = version.get("code", "")
    
    if v_type == "react":
        code_filename = "App.jsx"
        integration_instructions = (
            "Pour intégrer ce composant React dans votre application :\n"
            "1. Copiez 'App.jsx' dans le répertoire de vos composants React.\n"
            "2. Assurez-vous d'avoir les dépendances Lucide React si des icônes sont utilisées (`npm install lucide-react`).\n"
            "3. Importez-le dans votre fichier principal : `import App from './components/App';`"
        )
    elif v_type == "python":
        code_filename = "script.py"
        integration_instructions = (
            "Pour exécuter ce script Python :\n"
            "1. Assurez-vous d'installer les dépendances nécessaires :\n"
            "   `pip install matplotlib pandas openpyxl python-pptx` (selon les packages requis).\n"
            "2. Lancez le script via votre terminal : `python script.py`."
        )
    elif v_type == "mermaid":
        code_filename = "diagram.mmd"
        integration_instructions = (
            "Pour visualiser ce diagramme :\n"
            "1. Utilisez un lecteur Mermaid (ex. https://mermaid.live).\n"
            "2. Ou installez l'extension Markdown Preview Mermaid dans votre éditeur."
        )
    else:
        code_filename = "index.html"
        integration_instructions = (
            "Pour intégrer cette page HTML :\n"
            "1. Double-cliquez sur 'index.html' pour l'ouvrir directement dans votre navigateur.\n"
            "2. Copiez les styles et la structure dans votre template de site ou votre CMS."
        )

    tweaks_lines = []
    for tweak in version.get("tweaks", []):
        t_label = tweak.get("label", "")
        t_var = tweak.get("name", "")
        t_type = tweak.get("type", "")
        t_default = tweak.get("default", "")
        tweaks_lines.append(f"- **{t_label}** (`{t_var}`) : type `{t_type}`, valeur par défaut : `{t_default}`")
    
    tweaks_desc = "\n".join(tweaks_lines) if tweaks_lines else "*Aucun tweak dynamique configuré pour cette version.*"

    handoff_md = f"""# Guide de Transition Athena Design

Ce dossier d'export contient les fichiers générés par Athena Design pour le projet **{project.get('name', 'Sans titre')}** (Version {version_num}).

## Fichiers Inclus
- `{code_filename}` : Le code source généré.
- `claude-handoff.md` : Ce guide d'intégration.

## Variables de Personnalisation (Tweaks)
Le design utilise les variables CSS/de personnalisation suivantes pour configurer son aspect dynamique :
{tweaks_desc}

## Instructions d'Intégration
{integration_instructions}

---
Généré avec ❤️ par Athena Design.
"""

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(code_filename, code)
        zip_file.writestr("claude-handoff.md", handoff_md)

    zip_buffer.seek(0)
    
    safe_project_name = "".join(c for c in project.get("name", "athena-design") if c.isalnum() or c in ("-", "_")).strip()
    filename = f"handoff_{safe_project_name}_v{version_num}.zip"
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


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


@router.post("/projects/{project_id}/design-system/auto")
async def auto_design_system(request: Request, project_id: str, payload: dict = Body(...)):
    """Génère AUTOMATIQUEMENT la charte (parité Claude Design). `source` :
    - 'codebase' : extraction déterministe des tokens du code du projet (Tailwind/CSS) ;
    - 'image'    : extraction via la vision (`images` = data URLs / URLs) ;
    - 'brief'    : déduction depuis une description (`brief`) — cas greenfield sans code.
    Enregistre la charte dans le projet si `save` (défaut True)."""
    user = _current_user(request)
    if not _can_access(project_id):
        raise HTTPException(status_code=404, detail="Projet introuvable")
    from core import design_tokens
    source = (payload.get("source") or "codebase").strip().lower()
    charte = ""
    if source == "codebase":
        from core import projects as _proj
        from core.state import get_workspace_dir
        tok = _proj.set_override(project_id)
        try:
            ws = get_workspace_dir()
        finally:
            _proj.reset_override(tok)
        charte = design_tokens.from_codebase(ws)
    elif source == "image":
        charte = design_tokens.from_image(payload.get("images") or [])
    elif source == "brief":
        charte = design_tokens.from_brief(payload.get("brief") or "")
    else:
        raise HTTPException(status_code=400, detail="source invalide (codebase|image|brief).")

    saved = False
    if payload.get("save", True) and charte:
        db = read_db(user)
        db.setdefault(project_id, _new_design(project_id))
        db[project_id]["design_system"] = charte[:4000]
        write_db(user, db)
        saved = True
    return {"design_system": charte, "source": source, "saved": saved}


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
