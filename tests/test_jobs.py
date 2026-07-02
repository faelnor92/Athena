"""Runner de jobs en arrière-plan : progression, résultat, erreur, et PROPAGATION du
contexte utilisateur (ContextVar) au thread du worker."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import jobs  # noqa: E402


def _wait(jid, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = jobs.get(jid)
        if j and j["status"] in ("done", "error"):
            return j
        time.sleep(0.02)
    return jobs.get(jid)


def test_job_runs_reports_progress_and_result():
    def worker(progress):
        progress(0, 3, "début")
        for i in range(1, 4):
            progress(i, 3, f"étape {i}")
        return "fini-ok"

    jid = jobs.start("test", worker, owner="u1")
    j = _wait(jid)
    assert j["status"] == "done", j
    assert j["result"] == "fini-ok", j
    assert j["done"] == 3 and j["total"] == 3, j
    print("OK test_job_runs_reports_progress_and_result")


def test_job_captures_error():
    def worker(progress):
        raise ValueError("boom")

    jid = jobs.start("test-err", worker, owner="u1")
    j = _wait(jid)
    assert j["status"] == "error", j
    assert "boom" in (j["error"] or ""), j
    print("OK test_job_captures_error")


def test_job_propagates_user_context():
    from core.state import _current_username
    from core import user_config
    token = _current_username.set("alice")
    try:
        def worker(progress):
            return user_config.current_user_key()
        jid = jobs.start("ctx", worker, owner="alice")
        j = _wait(jid)
    finally:
        _current_username.reset(token)
    assert j["status"] == "done", j
    # Le worker tourne dans un autre thread : sans copy_context il lirait "local".
    assert j["result"] == "alice", j["result"]
    print("OK test_job_propagates_user_context")


def test_list_jobs_filters_by_owner():
    jobs.start("a", lambda p: 1, owner="bob")
    _wait(_id := jobs.start("b", lambda p: 2, owner="carol"))
    owners = {j["owner"] for j in jobs.list_jobs(owner="carol")}
    assert owners == {"carol"}, owners
    print("OK test_list_jobs_filters_by_owner")


def test_job_persisted_and_interrupted_after_restart():
    """Un job « running » persisté mais absent de la mémoire (= redémarrage) doit être
    présenté « interrupted », et reprenable si son op a une factory enregistrée."""
    from core import shared_store

    def worker(progress):
        progress(1, 4, "chapitre 1")
        progress.checkpoint({"done": ["ch1"]})
        return "ok"

    jid = jobs.start("persist", worker, owner="u1", op="test-op", params={"x": 1})
    j = _wait(jid)
    assert j["status"] == "done"
    assert (shared_store.get("jobs", jid) or {}).get("status") == "done", "le store doit être miroir"

    # Simule un redémarrage : le registre mémoire perd le job, le store garde « running ».
    rec = shared_store.get("jobs", jid)
    rec.update(status="running")
    shared_store.set("jobs", jid, rec)
    with jobs._LOCK:
        jobs._JOBS.pop(jid, None)
    j2 = jobs.get(jid)
    assert j2 and j2["status"] == "interrupted", j2
    assert j2["checkpoint"] == {"done": ["ch1"]}, j2
    assert not j2["resumable"], "op non enregistrée → pas reprenable"

    # Avec la factory enregistrée : reprenable, et resume() repart du checkpoint.
    seen = {}
    def factory(params, ck):
        def w(progress):
            seen["params"], seen["ck"] = params, ck
            return "repris"
        return w
    jobs.register_op("test-op", factory)
    try:
        assert jobs.get(jid)["resumable"] is True
        res = jobs.resume(jid)
        assert isinstance(res, dict), res
        j3 = _wait(jid)
        assert j3["status"] == "done" and j3["result"] == "repris", j3
        assert seen["ck"] == {"done": ["ch1"]} and seen["params"] == {"x": 1}, seen
    finally:
        jobs._RESUMABLE.pop("test-op", None)
        shared_store.delete("jobs", jid)
    print("OK test_job_persisted_and_interrupted_after_restart")


def test_resume_refuses_running_or_done():
    def worker(progress):
        return 42
    jid = jobs.start("done-job", worker, owner="u1", op="whatever")
    _wait(jid)
    assert jobs.resume(jid) == "Job déjà terminé."
    print("OK test_resume_refuses_running_or_done")


if __name__ == "__main__":
    test_job_runs_reports_progress_and_result()
    test_job_captures_error()
    test_job_propagates_user_context()
    test_list_jobs_filters_by_owner()
    test_job_persisted_and_interrupted_after_restart()
    test_resume_refuses_running_or_done()
    print("\nTous les tests jobs passent.")
