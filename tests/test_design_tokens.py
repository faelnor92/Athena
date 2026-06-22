"""A2 — extraction automatique de la charte (design system) : depuis le code (déterministe),
depuis une brève (LLM, mocké), garde-fous. Parité Claude Design."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import design_tokens  # noqa: E402


def _mkproj():
    d = tempfile.mkdtemp(prefix="athena_ds_")
    os.makedirs(os.path.join(d, "src"), exist_ok=True)
    with open(os.path.join(d, "src", "style.css"), "w", encoding="utf-8") as f:
        f.write(":root{--brand-color:#1e3a8a;--accent:#f59e0b;}\n"
                "body{font-family:'Inter',sans-serif;}\n"
                ".card{border-radius:12px;background:#1e3a8a;}\n"
                ".btn{border-radius:12px;color:#f59e0b;}\n")
    with open(os.path.join(d, "tailwind.config.js"), "w", encoding="utf-8") as f:
        f.write("module.exports={theme:{extend:{colors:{brand:'#1e3a8a'},"
                "fontFamily:{display:['Outfit','sans-serif']}}}}\n")
    return d


def test_from_codebase_extrait_couleurs_typo_arrondis():
    d = _mkproj()
    charte = design_tokens.from_codebase(d)
    assert "#1e3a8a" in charte
    assert "Inter" in charte
    assert "12px" in charte                      # arrondis
    assert "brand-color" in charte or "--brand" in charte  # variable de marque
    assert "Outfit" in charte                    # police Tailwind


def test_from_codebase_vide():
    assert design_tokens.from_codebase(tempfile.mkdtemp()) == ""
    assert design_tokens.from_codebase("/inexistant/xyz") == ""


def test_from_image_sans_image():
    assert design_tokens.from_image([]) == ""


def test_from_brief_mocke(monkeypatch):
    monkeypatch.setattr(design_tokens, "_complete", lambda *a, **k: "Palette : #0ea5e9\nTypo : Inter")
    out = design_tokens.from_brief("appli météo épurée bleu ciel")
    assert "#0ea5e9" in out
    assert design_tokens.from_brief("") == ""   # brève vide → rien


def test_endpoint_auto_source_invalide():
    import server
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    pid = c.post("/api/athenadesign/projects/new", json={"name": "DS"}).json()["id"]
    r = c.post(f"/api/athenadesign/projects/{pid}/design-system/auto", json={"source": "bidon"})
    assert r.status_code == 400


def test_endpoint_auto_brief_enregistre(monkeypatch):
    from core import design_tokens as dt
    monkeypatch.setattr(dt, "from_brief", lambda brief: "Palette : #111827\nTypo : Space Grotesk")
    import server
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    pid = c.post("/api/athenadesign/projects/new", json={"name": "DS2"}).json()["id"]
    r = c.post(f"/api/athenadesign/projects/{pid}/design-system/auto",
               json={"source": "brief", "brief": "fintech sombre"})
    assert r.status_code == 200
    data = r.json()
    assert data["saved"] is True and "#111827" in data["design_system"]
    # Persistée :
    got = c.get(f"/api/athenadesign/projects/{pid}/design-system").json()
    assert "Space Grotesk" in got["design_system"]
