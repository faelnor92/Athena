"""Tests d'isolation de l'état live par run (core.run_context)."""
import contextvars
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.run_context import registry, current_run_id, publish_step


def _do_run(rid, n):
    token = current_run_id.set(rid)
    registry.start(rid)
    try:
        for i in range(n):
            publish_step({"type": "message", "content": f"{rid}-{i}"})
    finally:
        registry.finish(rid)
        current_run_id.reset(token)


def test_runs_concurrents_ne_se_melangent_pas():
    # Deux runs lancés dans des threads distincts, chacun avec son contexte copié.
    threads = [
        threading.Thread(target=lambda: contextvars.copy_context().run(_do_run, "A", 5)),
        threading.Thread(target=lambda: contextvars.copy_context().run(_do_run, "B", 3)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    sa, sb = registry.status("A"), registry.status("B")
    assert len(sa["steps"]) == 5, f"run A: {len(sa['steps'])} étapes"
    assert len(sb["steps"]) == 3, f"run B: {len(sb['steps'])} étapes"
    assert all(s["content"].startswith("A-") for s in sa["steps"]), "fuite d'étapes vers A"
    assert all(s["content"].startswith("B-") for s in sb["steps"]), "fuite d'étapes vers B"
    assert sa["running"] is False and sb["running"] is False
    print("OK: les runs concurrents restent isolés")


def test_publish_sans_contexte_ne_plante_pas():
    # Hors de tout run (contextvar=None), publier ne doit rien casser.
    token = current_run_id.set(None)
    try:
        publish_step({"type": "message", "content": "orphelin"})
    finally:
        current_run_id.reset(token)
    print("OK: publish hors-contexte est sans effet")


if __name__ == "__main__":
    test_runs_concurrents_ne_se_melangent_pas()
    test_publish_sans_contexte_ne_plante_pas()
