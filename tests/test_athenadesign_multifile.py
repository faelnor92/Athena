"""Projets MULTI-FICHIERS AthenaDesign : génération → arborescence écrite sous <projet>/design/
→ servie via l'URL workspace (aperçu des liens relatifs)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_parse_multifile_extrait_arbo():
    from core.athenadesign_generator import parse_artifact_response
    txt = (
        "Un mini-site.\n"
        "=== FILE: index.html ===\n"
        "<!DOCTYPE html><link rel=stylesheet href=./css/style.css><body>Hello</body>\n"
        "=== FILE: css/style.css ===\n"
        "body{background:#111}\n"
    )
    r = parse_artifact_response(txt)
    assert r["entry"] == "index.html"
    paths = {f["path"] for f in r["files"]}
    assert paths == {"index.html", "css/style.css"}
    assert r["type"] == "html" and "Hello" in r["code"]


def test_chat_multifile_ecrit_sous_design_et_sert_les_fichiers(monkeypatch):
    from core import athenadesign_generator as g

    async def fake_generate(**kwargs):
        return {
            "type": "html", "explanation": "Mini-site.",
            "code": "<!DOCTYPE html><link rel=stylesheet href=./css/style.css><body>Hi</body>",
            "tweaks": [], "suggestions": [], "usage": {},
            "files": [
                {"path": "index.html", "content": "<!DOCTYPE html><link rel=stylesheet href=./css/style.css><body>Hi</body>"},
                {"path": "css/style.css", "content": "body{background:#111}"},
            ],
            "entry": "index.html",
        }

    monkeypatch.setattr(g, "generate_design", fake_generate)
    import server
    from fastapi.testclient import TestClient
    c = TestClient(server.app)

    r = c.post("/api/athenadesign/chat", json={"prompt": "fais un mini-site", "provider": "athena"})
    assert r.status_code == 200, r.text
    data = r.json()
    pid = data["project_id"]
    assert data["version"]["entry"] == "index.html"
    assert len(data["version"]["files"]) == 2

    # Les fichiers sont servis depuis <projet>/design/ (liens relatifs résolus à l'aperçu).
    idx = c.get(f"/api/athenadesign/projects/{pid}/workspace/design/index.html")
    assert idx.status_code == 200 and "Hi" in idx.text
    css = c.get(f"/api/athenadesign/projects/{pid}/workspace/design/css/style.css")
    assert css.status_code == 200 and "background:#111" in css.text


def test_tweaks_derives_des_variables_css_quand_modele_les_oublie():
    """Régression : en multi-fichiers le modèle oublie souvent <tweaks> → le dock se vidait.
    On dérive désormais les réglages depuis les variables CSS :root du design (filet)."""
    from core.athenadesign_generator import parse_artifact_response
    mf = (
        "=== FILE: index.html ===\n<link rel=stylesheet href=style.css><h1>Hi</h1>\n"
        "=== FILE: style.css ===\n:root{--primary:#ff5733;--radius:12px;}\n"
    )
    r = parse_artifact_response(mf)
    names = {t["name"] for t in r["tweaks"]}
    assert names == {"--primary", "--radius"}
    by = {t["name"]: t for t in r["tweaks"]}
    assert by["--primary"]["type"] == "color" and by["--primary"]["default"] == "#ff5733"
    assert by["--radius"]["type"] == "slider"


def test_tweaks_explicites_priment_sur_la_derivation():
    from core.athenadesign_generator import parse_artifact_response
    txt = (
        "```html\n<style>:root{--primary:#000;}</style><h1>x</h1>\n```\n"
        "<tweaks>\ncolor|Couleur|--primary|#fff|#fff\n</tweaks>"
    )
    r = parse_artifact_response(txt)
    assert len(r["tweaks"]) == 1 and r["tweaks"][0]["label"] == "Couleur"
