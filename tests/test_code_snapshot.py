"""Snapshots transactionnels des éditions de code (dépôt git shadow) : prise de
snapshot, rollback (fichiers modifiés restaurés, créés supprimés), snapshot auto
unique par run, exclusions protégées."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import code_snapshot as cs


def _tmp_ws(monkeypatch):
    ws = tempfile.mkdtemp(prefix="snap-ws-")
    monkeypatch.setattr(cs, "_workspace_dir", lambda: ws)
    return ws


def test_snapshot_et_rollback(monkeypatch):
    ws = _tmp_ws(monkeypatch)
    with open(os.path.join(ws, "a.txt"), "w") as f:
        f.write("version 1")
    os.makedirs(os.path.join(ws, "node_modules"), exist_ok=True)
    with open(os.path.join(ws, "node_modules", "lib.js"), "w") as f:
        f.write("exclu du snapshot, protégé du clean")

    snap = cs.take_snapshot("avant")
    assert snap and len(snap) >= 7

    # Série d'éditions : modification + création.
    with open(os.path.join(ws, "a.txt"), "w") as f:
        f.write("version 2 cassée")
    with open(os.path.join(ws, "b.txt"), "w") as f:
        f.write("nouveau fichier")

    out = cs.code_rollback(snap)
    assert "⏪" in out, out
    assert open(os.path.join(ws, "a.txt")).read() == "version 1", "fichier modifié restauré"
    assert not os.path.exists(os.path.join(ws, "b.txt")), "fichier créé supprimé"
    assert os.path.exists(os.path.join(ws, "node_modules", "lib.js")), \
        "les exclusions (node_modules…) ne doivent JAMAIS être nettoyées"
    print("OK: snapshot + rollback (restauré/supprimé/exclusions protégées)")


def test_auto_snapshot_un_seul_par_run(monkeypatch):
    ws = _tmp_ws(monkeypatch)
    cs.run_snapshot_id.set(None)
    with open(os.path.join(ws, "x.txt"), "w") as f:
        f.write("x")
    s1 = cs.auto_snapshot_before_mutation()
    s2 = cs.auto_snapshot_before_mutation()
    assert s1 and s1 == s2, "un SEUL snapshot auto par run (le premier)"
    assert cs.run_snapshot_id.get() == s1
    # rollback sans id → utilise le snapshot auto du run.
    with open(os.path.join(ws, "x.txt"), "w") as f:
        f.write("modifié")
    out = cs.code_rollback("")
    assert "⏪" in out and open(os.path.join(ws, "x.txt")).read() == "x"
    cs.run_snapshot_id.set(None)
    print("OK: snapshot auto unique par run + rollback sans id")


def test_rollback_sans_snapshot(monkeypatch):
    _tmp_ws(monkeypatch)
    cs.run_snapshot_id.set(None)
    out = cs.code_rollback("")
    assert "Erreur" in out
    print("OK: rollback sans snapshot → erreur explicite")


def test_code_rollback_est_sensible():
    from core import approvals
    old = os.environ.pop("SENSITIVE_TOOLS", None)
    try:
        assert "code_rollback" in approvals.sensitive_tool_names()
    finally:
        if old is not None:
            os.environ["SENSITIVE_TOOLS"] = old
    print("OK: code_rollback est un outil sensible (HITL) par défaut")


if __name__ == "__main__":
    class _MP:
        def setattr(self, obj, name, val): setattr(obj, name, val)
    test_snapshot_et_rollback(_MP())
    test_auto_snapshot_un_seul_par_run(_MP())
    test_rollback_sans_snapshot(_MP())
    test_code_rollback_est_sensible()
    print("\nTous les tests de snapshot passent.")
