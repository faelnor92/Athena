"""Atelier d'écriture de romans : lance les opérations LONGUES (révision, traduction,
vérification de cohérence) en ARRIÈRE-PLAN via core.jobs et expose leur PROGRESSION, afin
qu'un roman entier ne bloque/ne timeoute plus une requête HTTP. Sert l'onglet rédaction.
Les opérations marchent avec un .docx Nextcloud OU uploadé (workspace/uploads).

POST /api/redaction/chapters   {path}              → liste des chapitres détectés
POST /api/redaction/job        {op, path, ...}     → lance un job, renvoie {job_id}
GET  /api/redaction/job/{id}                       → état + progression + résultat
GET  /api/redaction/jobs                           → jobs de l'utilisateur courant
GET  /api/redaction/onlyoffice/config              → config de l'éditeur OnlyOffice pour un fichier
GET  /api/redaction/onlyoffice/file                → fichier servi au Document Server (jeton)
POST /api/redaction/onlyoffice/callback            → sauvegarde envoyée par le Document Server
"""
import os
import hashlib

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core import jobs, user_config, onlyoffice
import tools.document_editor as de

router = APIRouter(tags=["Rédaction"])


def _resolve_ws_file(path: str):
    """Chemin ABSOLU d'un fichier workspace à partir d'un chemin relatif, avec anti-traversée.
    Renvoie (abs, base) ou (None, base)."""
    from core.state import get_workspace_dir
    base = os.path.realpath(get_workspace_dir())
    clean = os.path.realpath(os.path.join(base, path or ""))
    if os.path.commonpath([clean, base]) != base or not os.path.isfile(clean):
        return None, base
    return clean, base

_OPS = ("autorevise", "translate", "coherence", "repetitions")


# --- Reprise après redémarrage : factories (op, params, checkpoint) → worker ---------
# Les workers posent des checkpoints par chapitre (progress.checkpoint) ; jobs.resume()
# reconstruit le worker avec le dernier checkpoint et relance là où c'était rendu.
def _mk_autorevise(params, ck):
    return lambda prog: de._autorevise_run(params["path"], params.get("instruction", ""),
                                           params.get("chapter", ""), progress=prog, checkpoint=ck)


def _mk_translate(params, ck):
    return lambda prog: de._translate_run(params["path"], params["target_language"],
                                          params.get("instruction", ""), progress=prog, checkpoint=ck)


def _mk_coherence(params, ck):
    return lambda prog: de._coherence_run(params["path"], params.get("chapter", ""),
                                          progress=prog, checkpoint=ck)


def _mk_repetitions(params, ck):
    # Rapide et déterministe : la « reprise » relance simplement l'analyse.
    return lambda prog: de.document_check_repetitions(params["path"], params.get("chapter", ""))


jobs.register_op("autorevise", _mk_autorevise)
jobs.register_op("translate", _mk_translate)
jobs.register_op("coherence", _mk_coherence)
jobs.register_op("repetitions", _mk_repetitions)


class ChaptersRequest(BaseModel):
    path: str


class JobRequest(BaseModel):
    op: str                       # autorevise | translate | coherence | repetitions
    path: str
    instruction: str = ""
    chapter: str = ""
    target_language: str = ""


def _owner() -> str:
    try:
        return user_config.current_user_key() or "local"
    except Exception:
        return "local"


@router.post("/api/redaction/chapters")
async def list_chapters(req: ChaptersRequest):
    """Ouvre le document (Nextcloud ou upload) et renvoie la liste de ses chapitres."""
    path = (req.path or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="Chemin du document manquant.")
    out = de.document_open(path)
    if "📄" not in out:
        raise HTTPException(status_code=400, detail=out)
    try:
        name = de._safe_name(path)
        local = de._local_path(name)
        doc = de._docx()(local)
        chaps = [{"title": t, "paragraphs": b - a} for (t, a, b) in de._chapters(doc)]
        ws_rel = _ws_rel(local)  # chemin relatif workspace → ouverture OnlyOffice
        # S'il existe déjà un « — révisé.docx » (révision précédente, éventuellement faite via
        # le chat), on le signale → le bouton OnlyOffice l'ouvre en priorité (pas l'original).
        rev_base = (name[:-5] if name.lower().endswith(".docx") else name) + " — révisé.docx"
        revised_abs = os.path.join(de._dir(), rev_base)
        revised_rel = _ws_rel(revised_abs) if os.path.exists(revised_abs) else None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"path": path, "chapters": chaps, "ws_path": ws_rel, "revised_path": revised_rel,
            "onlyoffice": onlyoffice.is_configured()}


def _ws_rel(abs_path: str):
    """Chemin RELATIF d'un fichier sous get_workspace_dir() (ou None s'il est en dehors)."""
    try:
        from core.state import get_workspace_dir
        base = os.path.realpath(get_workspace_dir())
        rel = os.path.relpath(os.path.realpath(abs_path), base)
        return rel if not rel.startswith("..") else None
    except Exception:
        return None


@router.post("/api/redaction/job")
async def start_job(req: JobRequest):
    """Lance une opération longue en arrière-plan. Renvoie un job_id à interroger."""
    op = (req.op or "").strip().lower()
    path = (req.path or "").strip()
    if op not in _OPS:
        raise HTTPException(status_code=400, detail=f"Opération inconnue : {op} (attendu : {', '.join(_OPS)}).")
    if not path:
        raise HTTPException(status_code=400, detail="Chemin du document manquant.")

    params = {"path": path, "instruction": req.instruction, "chapter": req.chapter,
              "target_language": req.target_language}
    if op == "autorevise":
        label = f"Révision — {path}"
        worker = _mk_autorevise(params, None)
    elif op == "translate":
        if not (req.target_language or "").strip():
            raise HTTPException(status_code=400, detail="Langue cible manquante.")
        label = f"Traduction ({req.target_language}) — {path}"
        worker = _mk_translate(params, None)
    elif op == "coherence":
        label = f"Cohérence — {path}"
        worker = _mk_coherence(params, None)
    else:  # repetitions (rapide, déterministe)
        label = f"Répétitions — {path}"
        worker = _mk_repetitions(params, None)

    # op+params rendent le job REPRENABLE après un redémarrage (cf. jobs.resume).
    jid = jobs.start(label, worker, owner=_owner(), op=op, params=params)
    return {"job_id": jid, "label": label}


@router.get("/api/redaction/job/{job_id}")
async def job_status(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job introuvable (expiré ou inexistant).")
    return j


@router.get("/api/redaction/jobs")
async def jobs_list():
    return {"jobs": jobs.list_jobs(owner=_owner())}


@router.post("/api/redaction/job/{job_id}/resume")
async def job_resume(job_id: str):
    """Reprend un job interrompu par un redémarrage (ou en erreur) depuis son dernier
    checkpoint — les chapitres déjà traités ne sont pas refaits."""
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job introuvable (expiré ou inexistant).")
    if j.get("owner") and j.get("owner") != _owner():
        raise HTTPException(status_code=403, detail="Ce job appartient à un autre utilisateur.")
    res = jobs.resume(job_id)
    if isinstance(res, str):
        raise HTTPException(status_code=409, detail=res)
    return res


# ----------------------------------------------------------------- OnlyOffice
@router.get("/api/redaction/onlyoffice/config")
async def onlyoffice_config(path: str, request: Request, mode: str = "edit"):
    """Construit la config de l'éditeur OnlyOffice pour un fichier workspace (.docx).
    Le Document Server téléchargera le fichier via un jeton et POSTera les sauvegardes au
    callback. Config signée en JWT si un secret est configuré."""
    if not onlyoffice.is_configured():
        raise HTTPException(status_code=400, detail="OnlyOffice non configuré (Réglages → OnlyOffice).")
    abs_path, _ = _resolve_ws_file(path)
    if not abs_path:
        raise HTTPException(status_code=404, detail="Fichier introuvable dans le workspace.")
    if not abs_path.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Seuls les .docx sont éditables ici.")

    tok = onlyoffice.register_token(abs_path, mode=("view" if mode == "view" else "edit"))
    base = onlyoffice.public_base(str(request.base_url))
    if not base:
        raise HTTPException(status_code=500, detail="URL publique d'Athena inconnue (ONLYOFFICE_PUBLIC_BASE).")
    name = os.path.basename(abs_path)
    # Clé unique par version du document (chemin + date de modif) → invalide le cache DS au save.
    try:
        ver = str(int(os.path.getmtime(abs_path)))
    except Exception:
        ver = "0"
    # SHA1 NON cryptographique : clé de cache du design-system par version (usedforsecurity=False).
    key = hashlib.sha1((abs_path + ver).encode(), usedforsecurity=False).hexdigest()[:20]

    cfg = {
        "document": {
            "fileType": "docx",
            "key": key,
            "title": name,
            "url": f"{base}/api/redaction/onlyoffice/file?token={tok}",
            "permissions": {"edit": mode != "view", "review": True, "download": True},
        },
        "documentType": "word",
        "editorConfig": {
            "mode": "view" if mode == "view" else "edit",
            "lang": "fr",
            "callbackUrl": f"{base}/api/redaction/onlyoffice/callback?token={tok}",
            "customization": {"forcesave": True, "autosave": True},
        },
    }
    token = onlyoffice.sign(cfg)
    if token:
        cfg["token"] = token
    return {"ds_url": onlyoffice.ds_url(), "config": cfg}


@router.get("/api/redaction/onlyoffice/file")
async def onlyoffice_file(token: str):
    """Sert le fichier au Document Server (server-to-server). Accès par JETON uniquement
    (endpoint non authentifié : le DS ne porte pas de session utilisateur)."""
    abs_path = onlyoffice.resolve_token(token)
    if not abs_path or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Jeton invalide ou fichier absent.")
    return FileResponse(abs_path, filename=os.path.basename(abs_path),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.post("/api/redaction/onlyoffice/callback")
async def onlyoffice_callback(token: str, request: Request):
    """Reçoit la sauvegarde du Document Server. status 2/6 = document prêt → on récupère le
    fichier édité et on écrase la copie de travail. Réponse {error:0} attendue par le DS."""
    abs_path = onlyoffice.resolve_token(token)
    if not abs_path:
        return JSONResponse({"error": 1})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": 1})
    # Vérifie le JWT si un secret est configuré (le DS signe le corps).
    if onlyoffice._secret():
        raw = body.get("token") or request.headers.get("Authorization", "").replace("Bearer ", "")
        try:
            payload = onlyoffice.verify(raw)
            body = payload.get("payload", payload) or body
        except Exception:
            return JSONResponse({"error": 1})
    status = body.get("status")
    # 2 = prêt à sauvegarder (édition terminée), 6 = forcesave pendant l'édition.
    if status in (2, 6):
        durl = body.get("url")
        if durl:
            try:
                r = requests.get(durl, timeout=30)
                if r.status_code == 200:
                    with open(abs_path, "wb") as f:
                        f.write(r.content)
            except Exception:
                return JSONResponse({"error": 1})
    return JSONResponse({"error": 0})
