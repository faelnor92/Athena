"""Streaming AthenaDesign (#4a) : /chat/stream diffuse les tokens (SSE) puis la version finale.
On mocke la génération LLM pour rester déterministe."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _client():
    import server
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def test_chat_stream_emet_tokens_puis_done(monkeypatch):
    from core import athenadesign_generator as g

    def fake_gen(prompt, history, model_name="", design_system="", context_text="",
                images=None, base_code="", on_delta=None):
        for tok in ("Voici ", "une ", "page."):
            if on_delta:
                on_delta(tok)
        return {"type": "html", "code": "<h1>Hi</h1>",
                "explanation": "Une page simple.", "tweaks": [], "suggestions": [], "usage": {}}

    monkeypatch.setattr(g, "_generate_via_athena", fake_gen)

    c = _client()
    pid = c.post("/api/athenadesign/projects/new", json={"name": "S"}).json()["id"]
    r = c.post("/api/athenadesign/chat/stream",
               json={"project_id": pid, "prompt": "fais une page", "provider": "athena"})
    assert r.status_code == 200
    body = r.text
    # Tokens diffusés au fil de l'eau + événement final avec la version.
    assert '"token": "Voici "' in body
    assert "event: done" in body and '"code": "<h1>Hi</h1>"' in body
    # La version a bien été persistée.
    got = c.get(f"/api/athenadesign/projects/{pid}").json()
    assert got["versions"][-1]["code"] == "<h1>Hi</h1>"


def test_chat_stream_erreur_genere_event_error(monkeypatch):
    from core import athenadesign_generator as g

    def boom(*a, **k):
        raise RuntimeError("LLM indispo")

    monkeypatch.setattr(g, "_generate_via_athena", boom)
    c = _client()
    pid = c.post("/api/athenadesign/projects/new", json={"name": "S2"}).json()["id"]
    r = c.post("/api/athenadesign/chat/stream",
               json={"project_id": pid, "prompt": "x", "provider": "athena"})
    assert r.status_code == 200
    assert "event: error" in r.text and "LLM indispo" in r.text
