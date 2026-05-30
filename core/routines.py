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


class RoutineStore:
    def __init__(self, path: str = None):
        self.path = path or os.getenv("ROUTINES_PATH", "routines.json")
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Routines] sauvegarde impossible : {e}")

    def list(self) -> list:
        with self._lock:
            return list(self._data.values())

    def get(self, rid: str):
        with self._lock:
            return self._data.get(rid)

    def upsert(self, routine: dict) -> dict:
        with self._lock:
            rid = routine.get("id") or uuid.uuid4().hex[:8]
            routine["id"] = rid
            routine.setdefault("enabled", True)
            routine.setdefault("notify", True)
            routine.setdefault("agent", "Jarvis")
            # Conserver last_run existant si non fourni.
            if "last_run" not in routine:
                prev = self._data.get(rid, {})
                routine["last_run"] = prev.get("last_run")
            self._data[rid] = routine
            self._save()
            return routine

    def delete(self, rid: str):
        with self._lock:
            self._data.pop(rid, None)
            self._save()

    def mark_run(self, rid: str, when_iso: str):
        with self._lock:
            if rid in self._data:
                self._data[rid]["last_run"] = when_iso
                self._save()


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
