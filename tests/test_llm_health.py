"""Scheduler LLM proactif : disjoncteur par modèle (429/pannes), sélection AVANT l'appel,
failover réactif conservé en filet, jamais de blocage complet."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import llm_health


def setup_function(_fn):
    llm_health.reset()


def test_rate_limit_ouvre_le_disjoncteur_immediatement():
    assert llm_health.available("groq/llama")
    llm_health.record_failure("groq/llama", Exception("429 Too Many Requests"))
    assert not llm_health.available("groq/llama"), "un 429 doit ouvrir le cooldown au 1er échec"
    llm_health.record_success("groq/llama")
    assert llm_health.available("groq/llama"), "un succès referme le disjoncteur"
    print("OK: 429 → cooldown immédiat, succès → refermé")


def test_erreurs_generiques_ouvrent_apres_n_echecs():
    for i in range(2):
        llm_health.record_failure("m1", Exception("connexion refusée"))
        assert llm_health.available("m1"), f"pas encore ouvert après {i + 1} échec(s)"
    llm_health.record_failure("m1", Exception("connexion refusée"))
    assert not llm_health.available("m1"), "3 échecs consécutifs → disjoncteur ouvert"
    print("OK: disjoncteur générique après N échecs")


def test_retry_after_respecte():
    llm_health.record_failure("m2", Exception("Rate limit reached. Please retry after 3600s."))
    snap = llm_health.snapshot()["m2"]
    assert snap["cooldown_remaining_s"] > 300, snap
    print("OK: fenêtre Retry-After du fournisseur respectée")


def test_order_candidates_ne_bloque_jamais():
    llm_health.record_failure("a", Exception("429"))
    assert llm_health.order_candidates(["a", "b", "c"]) == ["b", "c", "a"]
    # Tout en cooldown → ordre de config conservé (on tente quand même).
    llm_health.record_failure("b", Exception("429"))
    llm_health.record_failure("c", Exception("429"))
    assert llm_health.order_candidates(["a", "b", "c"]) == ["a", "b", "c"]
    # Doublons dédupliqués (modèles vierges pour ne pas dépendre des cooldowns ci-dessus).
    assert llm_health.order_candidates(["x", "x", "y"]) == ["x", "y"]
    print("OK: tri des candidats (sains d'abord, jamais vide)")


def test_complete_selection_proactive(monkeypatch):
    """Intégration : le 1er appel échoue en 429 sur le principal → fallback ; le 2e appel
    part DIRECTEMENT sur le fallback sans retenter le principal (proactif)."""
    import core.swarm as swarm_mod
    from core.swarm import Swarm

    seen = []

    class _Msg:
        content = "ok"
        tool_calls = None
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "ok"}

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 1

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]
        usage = _Usage()

    def fake(**kwargs):
        seen.append(kwargs["model"])
        if "principal" in kwargs["model"]:
            raise Exception("429 Too Many Requests")
        return _Resp()

    monkeypatch.setattr(swarm_mod, "completion", fake)
    monkeypatch.setenv("FALLBACK_MODELS", "openai/secours")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("STREAM_TOKENS", "false")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    s = Swarm.__new__(Swarm)
    s.agents = {}
    r1 = s._complete("openai/principal", [{"role": "user", "content": "x"}], tools_schema=None)
    assert r1.choices[0].message.content == "ok"
    assert seen == ["openai/principal", "openai/secours"], seen

    seen.clear()
    r2 = s._complete("openai/principal", [{"role": "user", "content": "x"}], tools_schema=None)
    assert r2.choices[0].message.content == "ok"
    assert seen == ["openai/secours"], f"le principal en cooldown doit être écarté AVANT l'appel : {seen}"
    print("OK: sélection proactive — le modèle en cooldown est écarté avant l'appel")


if __name__ == "__main__":
    for name in list(globals()):
        if name.startswith("test_") and "monkeypatch" not in name:
            llm_health.reset()
            globals()[name]()
    print("\nTests llm_health passés (test d'intégration : via pytest).")
