"""Runner de jobs en arrière-plan (in-process) pour les opérations LONGUES — révision,
traduction, vérification de cohérence d'un roman entier — qui dépassent le délai d'une
requête HTTP ou d'un tour de chat. Chaque job tourne dans un thread démon, expose une
PROGRESSION et un résultat ; le client (onglet rédaction) lance puis interroge l'état.

Volontairement simple : registre EN MÉMOIRE (mono-processus, suffisant en self-hosted), avec
verrou, TTL de nettoyage et capture d'exception. Pas de persistance disque — un redémarrage
annule les jobs en cours, acceptable pour des tâches interactives.
"""
import time
import uuid
import threading
import traceback
import contextvars

_LOCK = threading.Lock()
_JOBS = {}
_TTL = 3600          # un job terminé reste consultable 1 h
_MAX = 200           # garde-fou mémoire


class Progress:
    """Callback passé au worker : progress(done, total, message). Tout est optionnel."""

    def __init__(self, job_id):
        self.job_id = job_id

    def __call__(self, done=None, total=None, message=None):
        with _LOCK:
            j = _JOBS.get(self.job_id)
            if not j:
                return
            if done is not None:
                j["done"] = int(done)
            if total is not None:
                j["total"] = int(total)
            if message is not None:
                j["message"] = str(message)
            j["updated"] = time.time()


def _cleanup_locked():
    now = time.time()
    stale = [k for k, v in _JOBS.items()
             if v["status"] in ("done", "error") and now - v["updated"] > _TTL]
    for k in stale:
        _JOBS.pop(k, None)
    # Garde-fou : si trop de jobs, on purge les plus anciens terminés.
    if len(_JOBS) > _MAX:
        for k, _ in sorted(((k, v["updated"]) for k, v in _JOBS.items()
                            if _JOBS[k]["status"] in ("done", "error")),
                           key=lambda x: x[1])[:len(_JOBS) - _MAX]:
            _JOBS.pop(k, None)


def start(label: str, worker, owner: str = "") -> str:
    """Lance `worker(progress)` dans un thread démon. Renvoie le job_id."""
    jid = uuid.uuid4().hex[:12]
    now = time.time()
    with _LOCK:
        _cleanup_locked()
        _JOBS[jid] = {"id": jid, "label": label, "owner": owner, "status": "running",
                      "done": 0, "total": 0, "message": "", "result": None, "error": None,
                      "created": now, "updated": now}
    prog = Progress(jid)
    # Les ContextVar (utilisateur courant, rôle, langue) ne se propagent PAS aux nouveaux
    # threads → on capture le contexte de la requête et on exécute le worker DEDANS, sinon
    # _dir()/les écritures iraient dans le mauvais espace utilisateur.
    ctx = contextvars.copy_context()

    def _run():
        try:
            res = ctx.run(worker, prog)
            with _LOCK:
                j = _JOBS.get(jid)
                if j:
                    j.update(status="done", result=res, updated=time.time())
        except Exception as e:
            with _LOCK:
                j = _JOBS.get(jid)
                if j:
                    j.update(status="error", error=str(e), updated=time.time())
            print(f"[jobs] « {label} » échec : {e}\n{traceback.format_exc()}")

    threading.Thread(target=_run, daemon=True).start()
    return jid


def get(job_id: str):
    """État d'un job (copie) ou None."""
    with _LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else None


def list_jobs(owner=None):
    """Liste des jobs (filtrés par propriétaire si fourni)."""
    with _LOCK:
        return [dict(v) for v in _JOBS.values() if owner is None or v.get("owner") == owner]
