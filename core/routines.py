"""Routines proactives / planifiées (cron-agent).

Une routine = un prompt exécuté par un agent à intervalle/horaire défini. Le
résultat est persisté (run) et notifié sur les messageries configurées.

Déclencheurs supportés (schedule.type) :
  - "interval" : minutes=N           (toutes les N minutes)
  - "daily"    : time="HH:MM"         (chaque jour à l'heure dite)
  - "weekly"   : weekday=0..6, time   (0=lundi ; chaque semaine)
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta


_NS = "routines"


class RoutineStore:
    """Routines adossées au store SQLite partagé (process-safe, multi-worker)."""
    def __init__(self, path: str = None):
        from core import shared_store
        self._s = shared_store
        self._s.migrate_json_dict(path or os.getenv("ROUTINES_PATH", "routines.json"), _NS)

    def list(self) -> list:
        return self._s.values(_NS)

    def get(self, rid: str):
        return self._s.get(_NS, rid)

    def upsert(self, routine: dict) -> dict:
        rid = routine.get("id") or uuid.uuid4().hex[:8]
        routine["id"] = rid
        routine.setdefault("enabled", True)
        routine.setdefault("notify", True)
        routine.setdefault("agent", "Athena")
        # Propriétaire (multi-tenant) : la routine s'exécutera dans SON contexte.
        if not routine.get("owner"):
            try:
                from core.user_config import current_user_key
                routine["owner"] = current_user_key()
            except Exception:
                routine["owner"] = "local"
        prev = self._s.get(_NS, rid) or {}
        # Conserver last_run existant si non fourni.
        if "last_run" not in routine:
            routine["last_run"] = prev.get("last_run")
        # Conserver le secret existant si l'appel n'en fournit pas.
        if not routine.get("secret") and prev.get("secret"):
            routine["secret"] = prev["secret"]
        # Webhook entrant : générer un secret si toujours absent.
        if (routine.get("schedule") or {}).get("type") == "webhook" and not routine.get("secret"):
            routine["secret"] = uuid.uuid4().hex
        self._s.set(_NS, rid, routine)
        return routine

    def delete(self, rid: str):
        self._s.delete(_NS, rid)

    def mark_run(self, rid: str, when_iso: str):
        def _mark(d):
            if d is None:
                return None
            d["last_run"] = when_iso
            return d
        self._s.update(_NS, rid, _mark)


routine_store = RoutineStore()


def _parse_hhmm(value, default=(8, 0)):
    try:
        hh, mm = map(int, str(value).split(":"))
        return hh, mm
    except Exception:
        return default


def is_due(routine: dict, now: datetime) -> bool:
    sched = routine.get("schedule", {}) or {}
    typ = sched.get("type")
    last = routine.get("last_run")
    last_dt = None
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
        except Exception:
            last_dt = None

    if typ == "interval":
        mins = max(1, int(sched.get("minutes", 60)))
        return last_dt is None or now >= last_dt + timedelta(minutes=mins)

    if typ == "daily":
        hh, mm = _parse_hhmm(sched.get("time", "08:00"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return now >= target and (last_dt is None or last_dt.date() < now.date())

    if typ == "weekly":
        hh, mm = _parse_hhmm(sched.get("time", "08:00"))
        if now.weekday() != int(sched.get("weekday", 0)):
            return False
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return now >= target and (last_dt is None or last_dt.date() < now.date())

    return False


def start_scheduler(run_callback):
    """Lance le planificateur en thread de fond. run_callback(routine) exécute la tâche."""
    def loop():
        print("🗓️  [Routines] Planificateur démarré.")
        while True:
            try:
                now = datetime.now()
                for r in routine_store.list():
                    if not r.get("enabled", True):
                        continue
                    if is_due(r, now):
                        routine_store.mark_run(r["id"], now.isoformat())
                        try:
                            run_callback(r)
                        except Exception as e:
                            print(f"[Routines] erreur '{r.get('name')}' : {e}")
            except Exception as e:
                print(f"[Routines scheduler] {e}")
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="routine-scheduler").start()
