"""Contexte d'exécution par run — isole l'état « live » (étapes + statut) qui
était auparavant stocké dans des globales de module (server.ACTIVE_STEPS /
IS_CHAT_RUNNING), ce qui faisait que deux requêtes concurrentes (web + Telegram,
ou agents en parallèle) s'écrasaient mutuellement.

- `current_run_id` : ContextVar identifiant le run courant. Elle se propage aux
  threads enfants si on lance ceux-ci via `contextvars.copy_context().run(...)`,
  de sorte que les étapes des sous-agents (query_agent parallèles) remontent dans
  le même run que l'orchestrateur.
- `RunRegistry` : stocke, de façon thread-safe, les étapes live et le statut
  « running » par run_id, lus par l'endpoint /api/chat/status.
"""
import contextvars
import threading
from typing import Any, Dict, List, Optional

current_run_id: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "current_run_id", default=None
)


class RunRegistry:
    def __init__(self, max_runs: int = 200):
        self._lock = threading.Lock()
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._last_run_id: Optional[str] = None
        self._max_runs = max_runs

    def start(self, run_id: str):
        with self._lock:
            self._runs[run_id] = {"steps": [], "running": True}
            self._order.append(run_id)
            self._last_run_id = run_id
            # Purge des runs live les plus anciens (la persistance durable est en SQLite).
            while len(self._order) > self._max_runs:
                old = self._order.pop(0)
                self._runs.pop(old, None)

    def finish(self, run_id: str):
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run["running"] = False

    def append_step(self, run_id: Optional[str], step: dict):
        if run_id is None:
            return
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run["steps"].append(step)

    def status(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            rid = run_id or self._last_run_id
            run = self._runs.get(rid)
            if not run:
                return {"steps": [], "running": False, "run_id": rid}
            return {"steps": list(run["steps"]), "running": run["running"], "run_id": rid}


registry = RunRegistry()


def publish_step(step: dict):
    """Publie une étape live dans le run courant (déduit via la ContextVar)."""
    registry.append_step(current_run_id.get(), step)
