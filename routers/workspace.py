import os
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(tags=["Workspace"])

import contextlib

# Source unique (évite la divergence) : cf. core/state.py.
from core.state import get_workspace_dir


@contextlib.contextmanager
def _project_scope(project_id: str = None):
    """Cible un projet précis le temps de la requête (override de contexte) — utilisé par
    la console pour lister/éditer SON projet, sans toucher le projet global du chat."""
    tok = None
    if project_id:
        from core import projects
        tok = projects.set_override(project_id)
    try:
        yield
    finally:
        if tok is not None:
            from core import projects
            projects.reset_override(tok)

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
async def list_workspace_files(project_id: str = None):
    try:
      with _project_scope(project_id):
        base_dir = get_workspace_dir()
        from core import projects as _projects
        # « Dans un projet » = le workspace résolu n'est PAS le workspace de base (détection
        # robuste, indépendante de l'état override/active). Dans un projet → aucun filtrage.
        try:
            in_project = os.path.realpath(base_dir) != os.path.realpath(_projects._base_workspace())
        except Exception:
            in_project = _projects.active_path() is not None

        # Dossiers TOUJOURS masqués : volumineux/bruit (partout).
        ignored_dirs = {".venv", "venv", "__pycache__", ".git", ".gemini", "node_modules"}
        if not in_project:
            # Workspace de BASE : on masque aussi l'app et la racine des projets (sinon on
            # exposerait le code d'Athena et tous les projets) + on reste conservateur sur
            # les fichiers cachés.
            ignored_dirs |= {"static", "projects", "athena_projects"}

        def _is_secret_env(name: str) -> bool:
            # (Base uniquement) masquer le .env ; garder .env.example/.sample/.template.
            if name == ".env":
                return True
            if name.startswith(".env."):
                return name.split(".env.", 1)[1].lower() not in ("example", "sample", "template", "dist")
            return False

        files = []
        for root, dirs, filenames in os.walk(base_dir):
            if in_project:
                # Dans un PROJET : AUCUN filtrage de fichiers (c'est le projet de l'utilisateur,
                # l'agent voit tout). On n'élague que les dossiers LOURDS/générés pour que
                # l'arbre reste utilisable (node_modules, .git… peuvent contenir 10k+ entrées).
                dirs[:] = [d for d in dirs if d not in ignored_dirs]
            else:
                # Workspace de BASE : conservateur (pas de dotfiles, ni .env, ni app/projets).
                dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]

            for f in filenames:
                if not in_project and (f.startswith(".") or _is_secret_env(f)):
                    continue   # filtrage seulement hors projet
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, base_dir)
                try:
                    size_bytes = os.path.getsize(full_path)
                except OSError:
                    continue   # lien cassé / fichier disparu entre walk et stat
                files.append({"name": f, "path": rel_path, "size": size_bytes})
        files.sort(key=lambda x: x["path"])
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/workspace/file")
async def get_workspace_file(path: str, project_id: str = None):
    try:
      with _project_scope(project_id):
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
async def get_workspace_file_meta(path: str, project_id: str = None):
    """Métadonnées légères (mtime) pour détecter qu'un fichier ouvert a changé sur disque
    — ex. l'agent vient de l'éditer → le front propose/effectue un rechargement."""
    with _project_scope(project_id):
        clean = _safe_workspace_path(path)
        if not os.path.exists(clean) or os.path.isdir(clean):
            return {"path": path, "exists": False, "mtime": 0}
        return {"path": path, "exists": True, "mtime": os.path.getmtime(clean)}


class FileWriteRequest(BaseModel):
    path: str
    content: str
    project_id: str | None = None
@router.post("/api/workspace/file")
async def save_workspace_file(req: FileWriteRequest):
    """Sauvegarde (édition humaine dans l'IDE). Garde de RÔLE : un viewer d'un projet
    partagé ne peut PAS écrire (can_write, comme les outils de l'agent). Écriture atomique."""
    with _project_scope(req.project_id):
        return _do_save_workspace_file(req)


def _do_save_workspace_file(req: "FileWriteRequest"):
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

@router.delete("/api/workspace/file")
async def delete_workspace_file(path: str, project_id: str = None):
    """Supprime un fichier (ou un dossier vide/avec contenu) du workspace. Anti-traversée stricte.
    Le rôle LECTEUR (viewer) ne peut pas supprimer."""
    try:
      with _project_scope(project_id):
        try:
            from core import projects as _proj
            if not _proj.can_write():
                raise HTTPException(status_code=403, detail="Projet en lecture seule.")
        except HTTPException:
            raise
        except Exception:
            pass
        base_dir = get_workspace_dir()
        clean_path = os.path.abspath(os.path.join(base_dir, path or ""))
        if clean_path == base_dir or os.path.commonpath([clean_path, base_dir]) != base_dir:
            raise HTTPException(status_code=403, detail="Accès interdit.")
        if not os.path.exists(clean_path):
            raise HTTPException(status_code=404, detail="Introuvable.")
        import shutil as _sh
        if os.path.isdir(clean_path):
            _sh.rmtree(clean_path)
        else:
            os.remove(clean_path)
        return {"status": "success", "deleted": os.path.relpath(clean_path, base_dir)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspace/download")
async def download_workspace_file(path: str, project_id: str = None):
    try:
      with _project_scope(project_id):
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
