"""Atelier d'écriture de romans : lance les opérations LONGUES (révision, traduction,
vérification de cohérence) en ARRIÈRE-PLAN via core.jobs et expose leur PROGRESSION, afin
qu'un roman entier ne bloque/ne timeoute plus une requête HTTP. Sert l'onglet rédaction.
Les opérations marchent avec un .docx Nextcloud OU uploadé (workspace/uploads).

POST /api/redaction/chapters   {path}              → liste des chapitres détectés
POST /api/redaction/job        {op, path, ...}     → lance un job, renvoie {job_id}
GET  /api/redaction/job/{id}                       → état + progression + résultat
GET  /api/redaction/jobs                           → jobs de l'utilisateur courant
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import jobs, user_config
import tools.document_editor as de

router = APIRouter(tags=["Rédaction"])

_OPS = ("autorevise", "translate", "coherence", "repetitions")


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
        doc = de._docx()(de._local_path(de._safe_name(path)))
        chaps = [{"title": t, "paragraphs": b - a} for (t, a, b) in de._chapters(doc)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"path": path, "chapters": chaps}


@router.post("/api/redaction/job")
async def start_job(req: JobRequest):
    """Lance une opération longue en arrière-plan. Renvoie un job_id à interroger."""
    op = (req.op or "").strip().lower()
    path = (req.path or "").strip()
    if op not in _OPS:
        raise HTTPException(status_code=400, detail=f"Opération inconnue : {op} (attendu : {', '.join(_OPS)}).")
    if not path:
        raise HTTPException(status_code=400, detail="Chemin du document manquant.")

    if op == "autorevise":
        label = f"Révision — {path}"
        def worker(prog): return de._autorevise_run(path, req.instruction, req.chapter, progress=prog)
    elif op == "translate":
        if not (req.target_language or "").strip():
            raise HTTPException(status_code=400, detail="Langue cible manquante.")
        label = f"Traduction ({req.target_language}) — {path}"
        def worker(prog): return de._translate_run(path, req.target_language, req.instruction, progress=prog)
    elif op == "coherence":
        label = f"Cohérence — {path}"
        def worker(prog): return de._coherence_run(path, req.chapter, progress=prog)
    else:  # repetitions (rapide, déterministe)
        label = f"Répétitions — {path}"
        def worker(prog): return de.document_check_repetitions(path, req.chapter)

    jid = jobs.start(label, worker, owner=_owner())
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
