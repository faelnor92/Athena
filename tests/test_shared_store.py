"""Store SQLite partagé : cohérence multi-worker + atomicité des compteurs.

Vérifie que les stems d'état (users/quotas, invitations, routines) :
- sont cohérents entre plusieurs instances (= plusieurs workers) car ils ne gardent
  plus de copie en mémoire mais lisent/écrivent la même base SQLite ;
- gèrent les compteurs de façon ATOMIQUE (pas de perte de mise à jour sous concurrence) ;
- garantissent qu'une invitation à usage unique ne peut être consommée qu'une fois,
  même si plusieurs threads tentent simultanément.
"""
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Base d'état isolée AVANT d'importer le store (chemin résolu à l'import).
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name

from core import shared_store


def test_kv_basic():
    shared_store.set("t", "a", {"x": 1})
    assert shared_store.get("t", "a") == {"x": 1}
    assert shared_store.count("t") == 1
    assert shared_store.delete("t", "a") is True
    assert shared_store.get("t", "a") is None


def test_update_atomic_no_lost_writes():
    shared_store.set("ctr", "k", {"n": 0})

    def bump():
        for _ in range(200):
            shared_store.update("ctr", "k", lambda d: {"n": (d or {"n": 0})["n"] + 1})

    threads = [threading.Thread(target=bump) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert shared_store.get("ctr", "k")["n"] == 8 * 200, shared_store.get("ctr", "k")


def test_userstore_quota_coherent_across_instances():
    from core.users import UserStore
    a = UserStore()
    b = UserStore()  # simule un 2e worker
    a.create("zoe", "pw")
    a.set_quota("zoe", 1000)
    # conso via l'instance A → visible et plafonnante via l'instance B
    a.consume_tokens("zoe", 600)
    assert b.check_quota("zoe", 300) is True      # 600+300 <= 1000
    b.consume_tokens("zoe", 600)                  # total 1200 > 1000
    assert a.check_quota("zoe", 1) is False       # quota épuisé, vu depuis A


def test_invite_single_use_under_concurrency():
    from core.invites import InviteStore
    s = InviteStore()
    code = s.create(role="user")["code"]
    results = []

    def consume(i):
        results.append(s.consume(code, f"user{i}"))

    threads = [threading.Thread(target=consume, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1, f"l'invitation a été consommée {results.count(True)} fois (attendu 1)"


def test_routine_visible_across_instances():
    from core.routines import RoutineStore
    a = RoutineStore()
    b = RoutineStore()
    r = a.upsert({"name": "Test", "prompt": "x", "schedule": {"type": "daily", "time": "08:00"}})
    assert b.get(r["id"])["name"] == "Test"
    a.delete(r["id"])
    assert b.get(r["id"]) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests du store partagé passent.")
