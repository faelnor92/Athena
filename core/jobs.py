"""Runner de jobs en arrière-plan (in-process) pour les opérations LONGUES — révision,
traduction, vérification de cohérence d'un roman entier — qui dépassent le délai d'une
requête HTTP ou d'un tour de chat. Chaque job tourne dans un thread démon, expose une
PROGRESSION et un résultat ; le client (onglet rédaction) lance puis interroge l'état.

Persistance : l'état de chaque job est MIROIRÉ dans le shared_store SQLite (écritures
amorties). Un job encore « running » dans le store mais absent du registre mémoire a été
tué par un redémarrage → il est présenté « interrupted », et il est REPRENABLE si son
opération a été déclarée via register_op() et que le worker a posé des checkpoints
(progress.checkpoint(...)) : resume(job_id) relance le worker AVEC le dernier checkpoint,
qui saute ce qui est déjà fait. Les threads restent in-process (mono-worker en pratique).
"""
import os
import time
import uuid
import threading
import traceback
import contextvars

_LOCK = threading.Lock()
_JOBS = {}
_TTL = 3600          # un job terminé reste consultable 1 h (mémoire ET store)
_MAX = 200           # garde-fou mémoire
_NS = "jobs"         # namespace shared_store
_PERSIST_EVERY = 1.0  # s — amortit les écritures SQLite sur les progressions rapides

# Opérations REPRENABLES : op -> factory(params: dict, checkpoint) -> worker(progress).
# Déclarées par les routers (ex. redaction) à l'import ; un job dont l'op n'est pas
# enregistrée reste consultable mais pas reprenable.
_RESUMABLE = {}


def register_op(op: str, factory):
    _RESUMABLE[op] = factory


def _persist(j: dict):
    from core import shared_store
    shared_store.set(_NS, j["id"], {k: v for k, v in j.items()})


class Progress:
    """Callback passé au worker : progress(done, total, message). Tout est optionnel.
    progress.checkpoint(data) : sauve l'avancement REPRENABLE (persisté immédiatement) ;
    progress.checkpoint() sans argument renvoie le dernier checkpoint (dict ou None)."""

    def __init__(self, job_id):
        self.job_id = job_id
        self._last_persist = 0.0

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
            if j["updated"] - self._last_persist >= _PERSIST_EVERY:
                self._last_persist = j["updated"]
                _persist(j)

    def checkpoint(self, data=None):
        with _LOCK:
            j = _JOBS.get(self.job_id)
            if not j:
                return None
            if data is None:
                return j.get("checkpoint")
            j["checkpoint"] = data
            j["updated"] = time.time()
            _persist(j)
            return data


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
    # Hygiène du store : mêmes règles de TTL (les « interrupted » restent plus longtemps
    # pour laisser une chance de reprise après redémarrage : 7 jours).
    try:
        from core import shared_store
        for k, v in shared_store.items(_NS).items():
            st = (v or {}).get("status")
            upd = (v or {}).get("updated", 0)
            if st in ("done", "error") and now - upd > _TTL:
                shared_store.delete(_NS, k)
            elif st in ("running", "interrupted") and now - upd > 7 * 86400:
                shared_store.delete(_NS, k)
    except Exception:
        pass


def _launch(jid: str, worker, label: str):
    """Thread démon exécutant `worker(progress)` dans le contexte capturé."""
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
                    _persist(j)
        except Exception as e:
            with _LOCK:
                j = _JOBS.get(jid)
                if j:
                    j.update(status="error", error=str(e), updated=time.time())
                    _persist(j)
            print(f"[jobs] « {label} » échec : {e}\n{traceback.format_exc()}")

    threading.Thread(target=_run, daemon=True).start()


def start(label: str, worker, owner: str = "", op: str = "", params: dict = None) -> str:
    """Lance `worker(progress)` dans un thread démon. Renvoie le job_id.
    `op`/`params` (optionnels) rendent le job REPRENABLE après un redémarrage si
    l'op est enregistrée via register_op (resume() reconstruit le worker avec eux)."""
    jid = uuid.uuid4().hex[:12]
    now = time.time()
    with _LOCK:
        _cleanup_locked()
        _JOBS[jid] = {"id": jid, "label": label, "owner": owner, "status": "running",
                      "done": 0, "total": 0, "message": "", "result": None, "error": None,
                      "op": op, "params": dict(params or {}), "checkpoint": None,
                      "created": now, "updated": now}
        _persist(_JOBS[jid])
    _launch(jid, worker, label)
    return jid


def resume(job_id: str):
    """Reprend un job interrompu (redémarrage) ou en erreur, à partir de son dernier
    checkpoint. Renvoie l'état du job relancé, ou une chaîne d'erreur explicite."""
    j = get(job_id)
    if not j:
        return "Job introuvable (expiré ?)."
    if j["status"] == "running":
        return "Job déjà en cours."
    if j["status"] == "done":
        return "Job déjà terminé."
    factory = _RESUMABLE.get(j.get("op") or "")
    if not factory:
        return f"Opération « {j.get('op') or '?'} » non reprenable (pas de factory enregistrée)."
    try:
        worker = factory(j.get("params") or {}, j.get("checkpoint"))
    except Exception as e:
        return f"Reconstruction du worker impossible : {e}"
    now = time.time()
    with _LOCK:
        rec = dict(j)
        rec.update(status="running", error=None, result=None, updated=now)
        _JOBS[job_id] = rec
        _persist(rec)
    _launch(job_id, worker, j.get("label") or job_id)
    return get(job_id)


def _from_store(rec: dict) -> dict:
    """Vue d'un job persisté absent de la mémoire : un « running » d'avant redémarrage
    est mort (les threads ne survivent pas) → présenté « interrupted » (reprenable)."""
    r = dict(rec)
    if r.get("status") == "running":
        r["status"] = "interrupted"
    r["resumable"] = bool(_RESUMABLE.get(r.get("op") or "")) and r["status"] in ("interrupted", "error")
    return r


def get(job_id: str):
    """État d'un job (copie) ou None. Cherche en mémoire (job vivant), puis dans le
    store persistant (job d'avant redémarrage → « interrupted »)."""
    with _LOCK:
        j = _JOBS.get(job_id)
        if j:
            out = dict(j)
            out["resumable"] = False
            return out
    try:
        from core import shared_store
        rec = shared_store.get(_NS, job_id)
        return _from_store(rec) if rec else None
    except Exception:
        return None


def list_jobs(owner=None):
    """Liste des jobs (filtrés par propriétaire si fourni), mémoire + persistés."""
    with _LOCK:
        out = {k: dict(v) for k, v in _JOBS.items()}
        for v in out.values():
            v["resumable"] = False
    try:
        from core import shared_store
        for k, rec in shared_store.items(_NS).items():
            if k not in out and rec:
                out[k] = _from_store(rec)
    except Exception:
        pass
    return [v for v in out.values() if owner is None or v.get("owner") == owner]
