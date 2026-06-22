"""Isolation GLOBALE de la suite de tests (hermétique, indépendante de l'ordre).

Problème historique : chaque fichier de test mutait `os.environ` et des globals de
modules AU NIVEAU MODULE. Or pytest importe TOUS les modules de test pendant la
collecte, avant de lancer le moindre test → « le dernier écrivain gagne » et des tests
verts en isolation devenaient rouges en suite complète (faux LLM qui fuit, comptes/
pipelines d'un test vus par un autre, base SQLite du dépôt polluée…).

Ce conftest règle ça en trois temps :
  1. AVANT tout import applicatif (ce module est importé par pytest avant la collecte),
     on redirige tout l'état persistant vers un dossier temporaire de session et on
     force l'import du store pour FIGER son chemin (la plupart des modules lisent ces
     chemins une seule fois, à l'import).
  2. Une fixture autouse restaure `core.swarm.completion` autour de CHAQUE test : les
     tests qui font `swarm_mod.completion = fake` n'ont plus besoin de nettoyer.
  3. La même fixture VIDE le store clé-valeur partagé entre chaque test : comptes,
     pipelines, sessions… repartent de zéro, quel que soit l'ordre d'exécution.
"""
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# --- 1) État persistant → dossier temporaire de session, AVANT tout import applicatif.
_TMP = tempfile.mkdtemp(prefix="athena_tests_")
_PERSIST_PATHS = {
    "STATE_DB_PATH": os.path.join(_TMP, "state.sqlite3"),
    "RUNS_DB_PATH": os.path.join(_TMP, "runs.sqlite3"),
    "CONVERSATIONS_DB_PATH": os.path.join(_TMP, "conv.sqlite3"),
    "CHROMA_DB_PATH": os.path.join(_TMP, "chroma"),
    "CORE_MEMORY_PATH": os.path.join(_TMP, "core_memory.json"),
    "GRAPH_MEMORY_PATH": os.path.join(_TMP, "graph_memory.sqlite3"),
    "ROUTINES_PATH": os.path.join(_TMP, "routines.json"),
    "PLANS_PATH": os.path.join(_TMP, "plans.json"),
}
for _k, _v in _PERSIST_PATHS.items():
    os.environ[_k] = _v

# Garde-fous globaux inoffensifs : éviter qu'un test isolé déclenche le garde réseau,
# le rate-limit ou la boucle d'auto-amélioration (chacun reste surchargeable par test).
os.environ.setdefault("HOST", "127.0.0.1")
os.environ.setdefault("RATE_LIMIT_PER_MIN", "100000")
os.environ.setdefault("SELF_IMPROVE", "false")
# CRUCIAL pour l'hermétisme : après CHAQUE run swarm, des hooks d'apprentissage tournent
# (rapport d'expérience, induction de skill, profil utilisateur, extraction de graphe). Ils
# appellent le LLM (donc le faux `_complete`/`completion` des tests → corrompt les valeurs
# capturées) ET écrivent dans l'état global. En prod ils sont en arrière-plan (thread daemon
# ASYNC_POST_HOOKS=true) → en test ils courent en concurrence avec le test suivant (fuites
# NON DÉTERMINISTES, échecs qui « se déplacent » selon l'ordre/le timing). On les neutralise
# par défaut ; les tests qui les VALIDENT (test_skill_induction, hook swarm…) les réactivent
# eux-mêmes (os.environ restauré par test → pas de fuite).
os.environ.setdefault("ASYNC_POST_HOOKS", "false")   # synchrone : pas de thread qui fuit
os.environ.setdefault("SELF_IMPROVE_SKILLS", "false")
os.environ.setdefault("USER_MODELING", "false")
os.environ.setdefault("GRAPH_AUTO_EXTRACT", "false")

# Fige le chemin du store sur le dossier de session (sinon le 1er fichier de test
# important `core.shared_store` imposerait SON chemin à toute la suite).
import core.shared_store as _shared_store  # noqa: E402

import pytest  # noqa: E402


_MISSING = object()


def _wipe_shared_store():
    """Vide la table kv (comptes, pipelines, sessions, quotas, projets…)."""
    try:
        c = _shared_store._conn()
        c.execute("DELETE FROM kv")
        c.commit()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _hermetic_test():
    """Garantit qu'aucun état global ne fuit d'un test à l'autre.

    Restaure autour de CHAQUE test : `os.environ` (un test qui pose STREAM_TOKENS,
    SELF_IMPROVE… ne contamine plus les suivants), `core.swarm.completion` (faux LLM),
    et `sys.modules['server']` (test_agent_tools y injecte un module factice). Vide aussi
    le store partagé avant ET après (comptes/pipelines/sessions repartent de zéro).
    """
    import core.swarm as swarm_mod

    _orig_env = dict(os.environ)
    _orig_completion = swarm_mod.completion  # 1er test = litellm ; ensuite = déjà restauré
    _orig_server = sys.modules.get("server", _MISSING)
    # `Swarm._complete` est une méthode HÉRITÉE d'un mixin ; certains tests la remplacent sur
    # la CLASSE (ex. test_memory) sans la restaurer → les tests swarm suivants n'appellent
    # plus le vrai chemin LLM (« obtenu 0 appels »). On capture l'état du __dict__ de classe.
    _orig_complete = swarm_mod.Swarm.__dict__.get("_complete", _MISSING)
    # HERMÉTISME vis-à-vis du .env de l'opérateur : la liste SENSITIVE_TOOLS (HITL) ne doit pas
    # influencer la suite (sinon un outil nommé comme un outil sensible, ex. edit_file, part en
    # approbation et un test d'exécution échoue/bloque). On la neutralise ; les tests du gate
    # HITL utilisent l'attribut `_requires_approval` (indépendant de l'env) ou la posent eux-mêmes.
    os.environ["SENSITIVE_TOOLS"] = ""
    _wipe_shared_store()  # chaque test démarre avec un store vierge
    try:
        yield
    finally:
        swarm_mod.completion = _orig_completion
        if _orig_complete is _MISSING:
            if "_complete" in swarm_mod.Swarm.__dict__:
                delattr(swarm_mod.Swarm, "_complete")  # rétablit l'héritage du mixin
        else:
            swarm_mod.Swarm._complete = _orig_complete
        if _orig_server is _MISSING:
            sys.modules.pop("server", None)
        else:
            sys.modules["server"] = _orig_server
        os.environ.clear()
        os.environ.update(_orig_env)
        _wipe_shared_store()
