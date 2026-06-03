import os
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(tags=["Workspace"])

# Source unique (évite la divergence) : cf. core/state.py.
from core.state import get_workspace_dir

@router.get("/api/workspace/config")
async def get_workspace_config():
    return {
        "active_workspace_dir": get_workspace_dir(),
        "default_dir": os.getcwd()
    }

class WorkspaceConfigRequest(BaseModel):
    path: str

@router.post("/api/workspace/config")
async def set_workspace_config(req: WorkspaceConfigRequest):
    target_path = os.path.abspath(req.path)
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Le dossier cible spécifié n'existe pas.")
    if not os.path.isdir(target_path):
        raise HTTPException(status_code=400, detail="Le chemin cible doit être un dossier.")
        
    os.environ["ACTIVE_WORKSPACE_DIR"] = target_path
    print(f"📁 [Workspace] Changement de répertoire de travail : {target_path}")
    return {
        "status": "success",
        "active_workspace_dir": target_path,
        "message": f"Dossier de travail repositionné sur : {target_path}"
    }

@router.get("/api/workspace/dirs")
async def list_subdirectories(path: str = ""):
    try:
        if not path or path.strip() == "":
            target_path = os.getcwd()
        else:
            target_path = os.path.abspath(path)
            
        if not os.path.exists(target_path) or not os.path.isdir(target_path):
            target_path = os.getcwd()
            
        parent = os.path.dirname(target_path)
        subdirs = []
        try:
            for item in os.listdir(target_path):
                full_item = os.path.join(target_path, item)
                if os.path.isdir(full_item) and not item.startswith(".") and item not in ["node_modules", "venv", ".venv"]:
                    subdirs.append(item)
        except Exception:
            pass
            
        subdirs.sort()
        return {
            "current_path": target_path,
            "parent_path": parent,
            "subdirs": subdirs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/workspace/files")
async def list_workspace_files():
    try:
        base_dir = get_workspace_dir()
        ignored_patterns = [".venv", "venv", "__pycache__", ".git", ".gemini", "static", ".env", "node_modules"]
        files = []
        for root, dirs, filenames in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in ignored_patterns and not d.startswith(".")]
            
            for f in filenames:
                if f.startswith("."):
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, base_dir)
                
                size_bytes = os.path.getsize(full_path)
                files.append({
                    "name": f,
                    "path": rel_path,
                    "size": size_bytes
                })
        files.sort(key=lambda x: x["path"])
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/workspace/file")
async def get_workspace_file(path: str):
    try:
        base_dir = get_workspace_dir()
        clean_path = os.path.abspath(os.path.join(base_dir, path))
        if os.path.commonpath([clean_path, base_dir]) != base_dir:
            raise HTTPException(status_code=403, detail="Accès interdit.")
            
        if not os.path.exists(clean_path) or os.path.isdir(clean_path):
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
            
        with open(clean_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # mtime = "version" du fichier : permet au front de détecter une modif (ex. l'agent).
        return {"path": path, "content": content, "mtime": os.path.getmtime(clean_path)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _safe_workspace_path(path: str) -> str:
    """Résout `path` sous le workspace actif, refuse toute évasion (403)."""
    base_dir = get_workspace_dir()
    clean = os.path.abspath(os.path.join(base_dir, path))
    if os.path.commonpath([clean, base_dir]) != base_dir:
        raise HTTPException(status_code=403, detail="Accès interdit.")
    return clean


@router.get("/api/workspace/file/meta")
async def get_workspace_file_meta(path: str):
    """Métadonnées légères (mtime) pour détecter qu'un fichier ouvert a changé sur disque
    — ex. l'agent vient de l'éditer → le front propose/effectue un rechargement."""
    clean = _safe_workspace_path(path)
    if not os.path.exists(clean) or os.path.isdir(clean):
        return {"path": path, "exists": False, "mtime": 0}
    return {"path": path, "exists": True, "mtime": os.path.getmtime(clean)}


class FileWriteRequest(BaseModel):
    path: str
    content: str


@router.post("/api/workspace/file")
async def save_workspace_file(req: FileWriteRequest):
    """Sauvegarde (édition humaine dans l'IDE). Garde de RÔLE : un viewer d'un projet
    partagé ne peut PAS écrire (can_write, comme les outils de l'agent). Écriture atomique."""
    from core import projects
    if not projects.can_write():
        raise HTTPException(status_code=403,
                            detail="Lecture seule : vous n'avez pas le droit d'écriture sur ce projet.")
    clean = _safe_workspace_path(req.path)
    if os.path.isdir(clean):
        raise HTTPException(status_code=400, detail="Chemin invalide (dossier).")
    import tempfile
    parent = os.path.dirname(clean) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ide-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(req.content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, clean)
    except Exception as e:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "success", "path": req.path, "mtime": os.path.getmtime(clean)}


class PresenceRequest(BaseModel):
    path: str


@router.post("/api/workspace/presence")
async def workspace_presence(req: PresenceRequest):
    """Présence collaborative : signale que l'utilisateur courant consulte ce fichier et
    renvoie la liste des AUTRES personnes qui le consultent (fenêtre glissante ~20 s)."""
    import time
    from core import shared_store
    from core.user_config import current_user_key
    clean = _safe_workspace_path(req.path)
    user = current_user_key()
    key = clean  # présence par chemin réel (donc par projet/workspace)
    now = time.time()

    def _touch(d):
        d = {u: t for u, t in (d or {}).items() if now - t < 20}  # purge des inactifs
        d[user] = now
        return d
    d = shared_store.update("presence", key, _touch)
    others = [u for u in (d or {}) if u != user]
    return {"viewers": others}

@router.get("/api/workspace/download")
async def download_workspace_file(path: str):
    try:
        base_dir = get_workspace_dir()
        clean_path = os.path.abspath(os.path.join(base_dir, path))
        if os.path.commonpath([clean_path, base_dir]) != base_dir:
            raise HTTPException(status_code=403, detail="Accès interdit.")
            
        if not os.path.exists(clean_path) or os.path.isdir(clean_path):
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
            
        return FileResponse(
            clean_path,
            media_type="application/octet-stream",
            filename=os.path.basename(clean_path)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/workspace/upload")
async def upload_workspace_file(file: UploadFile = File(...)):
    try:
        base_dir = get_workspace_dir()
        filename = os.path.basename(file.filename)
        if not filename or filename in (".", ".."):
            raise HTTPException(status_code=400, detail="Nom de fichier invalide.")
        dest_path = os.path.join(base_dir, filename)

        max_mb = int(os.getenv("MAX_UPLOAD_MB", "50") or 50)
        max_bytes = max_mb * 1024 * 1024
        written = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    f.close()
                    os.remove(dest_path)
                    raise HTTPException(status_code=413, detail=f"Fichier trop volumineux (max {max_mb} Mo).")
                f.write(chunk)
            
        ext = os.path.splitext(filename)[1].lower()
        ingested = False
        report = ""
        
        if ext in ['.txt', '.md', '.markdown', '.py', '.js', '.json', '.html', '.css', '.csv']:
            try:
                from tools.memory_tools import ingest_file
                relative_path = os.path.join("workspace", filename)
                report = ingest_file(relative_path)
                ingested = True
            except Exception as ing_err:
                report = f"Erreur lors de l'ingestion automatique : {str(ing_err)}"
                print(f"[Ingestion Auto Error] {ing_err}")
                
        return {
            "status": "success", 
            "message": f"Fichier '{filename}' téléversé avec succès !", 
            "path": filename,
            "ingested": ingested,
            "report": report
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
