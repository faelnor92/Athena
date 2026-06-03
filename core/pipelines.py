"""Workflows / Pipelines DÉTERMINISTES (mode « chaîne de montage » type CrewAI).

Alternative OPTIONNELLE au swarm organique : au lieu de laisser l'orchestrateur
router librement, on définit une suite ORDONNÉE d'étapes — chacune = un agent + une
instruction (+ une sortie attendue). Les étapes s'exécutent séquentiellement, la sortie
de l'une devient l'entrée de la suivante, et AUCUN agent ne peut dévier de la chaîne
(cf. swarm.run(locked=True, lock_delegation=True)). Reproductible et auditable —
ce que certaines entreprises préfèrent au mode organique.

Le swarm organique reste le défaut ; les pipelines ne s'exécutent que si on le demande
(UI, API, routine). Stockés dans le store SQLite partagé (multi-worker), par propriétaire.

Modèle : pipeline = {
    id, name, owner, created_at,
    steps: [ {agent: str, instruction: str, expected_output: str} ]
}
"""
import time
import uuid

from core import shared_store

_NS = "pipelines"


def _now_owner() -> str:
    try:
        from core.user_config import current_user_key
        return current_user_key()
    except Exception:
        return "local"


class PipelineStore:
    def list(self, owner: str = None) -> list:
        owner = owner or _now_owner()
        return [p for p in shared_store.values(_NS) if (p.get("owner") or "local") == owner]

    def get(self, pid: str):
        return shared_store.get(_NS, pid)

    def get_owned(self, pid: str, owner: str = None):
        """Pipeline si propriété de l'utilisateur courant, sinon None."""
        owner = owner or _now_owner()
        p = shared_store.get(_NS, pid)
        if not p or (p.get("owner") or "local") != owner:
            return None
        return p

    @staticmethod
    def _clean_steps(steps) -> list:
        out = []
        for s in (steps or []):
            agent = (s.get("agent") or "").strip()
            instr = (s.get("instruction") or "").strip()
            if not agent or not instr:
                continue
            out.append({
                "agent": agent,
                "instruction": instr,
                "expected_output": (s.get("expected_output") or "").strip(),
            })
        return out

    def upsert(self, data: dict, owner: str = None) -> dict:
        owner = owner or _now_owner()
        pid = data.get("id") or uuid.uuid4().hex[:8]
        # On ne peut pas écraser le pipeline d'un autre propriétaire.
        prev = shared_store.get(_NS, pid)
        if prev and (prev.get("owner") or "local") != owner:
            raise PermissionError("Pipeline d'un autre utilisateur.")
        pipeline = {
            "id": pid,
            "name": (data.get("name") or "Workflow").strip() or "Workflow",
            "owner": owner,
            "steps": self._clean_steps(data.get("steps")),
            "created_at": prev.get("created_at") if prev else time.time(),
            "updated_at": time.time(),
        }
        shared_store.set(_NS, pid, pipeline)
        return pipeline

    def delete(self, pid: str, owner: str = None) -> bool:
        owner = owner or _now_owner()
        p = shared_store.get(_NS, pid)
        if not p or (p.get("owner") or "local") != owner:
            return False
        return shared_store.delete(_NS, pid)


pipeline_store = PipelineStore()
