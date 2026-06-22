"""Pont « Ouvrir dans AthenaDesign » : endpoint import-code qui amorce un projet avec du
code existant (artifact venu du chat) sans appel LLM."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _client():
    import server
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def test_import_code_cree_une_version():
    c = _client()
    proj = c.post("/api/athenadesign/projects/new", json={"name": "T"}).json()
    pid = proj["id"]
    r = c.post(f"/api/athenadesign/projects/{pid}/import-code",
               json={"code": "<h1>Salut</h1>", "type": "html", "explanation": "depuis le chat"})
    assert r.status_code == 200, r.text
    v = r.json()["version"]
    assert v["type"] == "html" and v["code"] == "<h1>Salut</h1>" and v["version"] == 1
    # La version est persistée et relisable.
    got = c.get(f"/api/athenadesign/projects/{pid}").json()
    assert got["versions"][-1]["code"] == "<h1>Salut</h1>"


def test_import_code_type_inconnu_retombe_sur_html():
    c = _client()
    pid = c.post("/api/athenadesign/projects/new", json={"name": "T2"}).json()["id"]
    v = c.post(f"/api/athenadesign/projects/{pid}/import-code",
               json={"code": "x", "type": "bidon"}).json()["version"]
    assert v["type"] == "html"


def test_import_code_vide_refuse():
    c = _client()
    pid = c.post("/api/athenadesign/projects/new", json={"name": "T3"}).json()["id"]
    r = c.post(f"/api/athenadesign/projects/{pid}/import-code", json={"code": "   "})
    assert r.status_code == 400
