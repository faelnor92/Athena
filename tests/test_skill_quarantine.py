"""Quarantaine canary des skills induites : self-tests à l'induction, comptage des
usages réels, promotion après N succès, éviction sur échecs répétés."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import skill_quarantine as sq

_CODE_OK = '''def double_val(x):
    """Double la valeur."""
    return x * 2
'''


def _clean(name):
    for p in (os.path.join(sq.QUARANTINE_DIR, f"{name}.py"),
              os.path.join(sq.QUARANTINE_DIR, f"{name}.tests.json"),
              os.path.join("skills", f"{name}.py")):
        if os.path.exists(p):
            os.remove(p)
    from core import shared_store
    shared_store.delete("skill_canary", name)


def test_self_tests_filtrent_les_skills_bancales():
    def double_val(x):
        return x * 2
    ok, _ = sq.run_self_tests(double_val, [{"args": [2], "expected": 4},
                                           {"args": [0], "expected": 0}])
    assert ok
    ok, reason = sq.run_self_tests(double_val, [{"args": [2], "expected": 5}])
    assert not ok and "attendu" in reason
    ok, reason = sq.run_self_tests(double_val, [])
    assert not ok, "aucun cas de test = refus"

    def boucle(x):
        while True:
            pass
    ok, reason = sq.run_self_tests(boucle, [{"args": [1], "expected": 1}], timeout_s=0.3)
    assert not ok and "timeout" in reason
    print("OK: self-tests (échec, vide, boucle infinie → refus)")


def test_canary_promotion_apres_n_succes(monkeypatch):
    monkeypatch.setenv("SKILL_CANARY_PROMOTE", "2")
    name = "double_val"
    _clean(name)
    try:
        msg = sq.save_quarantined(name, _CODE_OK, "double", [{"args": [1], "expected": 2}])
        assert msg.startswith("Succès")
        loaded = sq.load_quarantined()
        assert name in loaded
        assert loaded[name].__doc__ and "Double" in loaded[name].__doc__, \
            "le wrapper canary doit préserver la docstring (schéma d'outil)"
        assert loaded[name](21) == 42
        assert os.path.exists(os.path.join(sq.QUARANTINE_DIR, f"{name}.py")), "1 succès : encore en quarantaine"
        loaded[name](1)  # 2e succès → promotion
        assert os.path.exists(os.path.join("skills", f"{name}.py")), "promue dans skills/"
        assert not os.path.exists(os.path.join(sq.QUARANTINE_DIR, f"{name}.py"))
    finally:
        _clean(name)
    print("OK: promotion après N usages réussis (wrapper transparent)")


def test_canary_eviction_apres_echecs(monkeypatch):
    monkeypatch.setenv("SKILL_CANARY_MAX_FAILS", "2")
    name = "div_val"
    _clean(name)
    code = 'def div_val(x):\n    """Divise 10 par x."""\n    return 10 / x\n'
    try:
        sq.save_quarantined(name, code, "divise", [{"args": [2], "expected": 5.0}])
        loaded = sq.load_quarantined()
        for _ in range(2):
            try:
                loaded[name](0)  # ZeroDivisionError → échec canary
            except ZeroDivisionError:
                pass
        assert not os.path.exists(os.path.join(sq.QUARANTINE_DIR, f"{name}.py")), \
            "2 échecs en canary → évincée"
        assert not os.path.exists(os.path.join("skills", f"{name}.py"))
    finally:
        _clean(name)
    print("OK: éviction après échecs répétés en canary")


if __name__ == "__main__":
    class _MP:
        def setenv(self, k, v): os.environ[k] = v
    test_self_tests_filtrent_les_skills_bancales()
    test_canary_promotion_apres_n_succes(_MP())
    test_canary_eviction_apres_echecs(_MP())
    print("\nTous les tests de quarantaine passent.")
