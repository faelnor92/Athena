"""AthenaDesign : runner durci (sandbox Docker prioritaire, repli local journalisé).

Tests SANS Docker réel (mock) : choix du mode d'exécution + scan des sorties.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import athenadesign_runner as r  # noqa: E402


def test_react_detection_et_scaffold():
    """Type 'react' détecté (balise jsx ou heuristique) + scaffold autonome (React/Babel/root)."""
    from core.athenadesign_generator import parse_artifact_response, react_scaffold
    r = parse_artifact_response("Compteur.\n```jsx\nfunction App(){const[n,setN]=React.useState(0);"
                                "return <button onClick={()=>setN(n+1)}>{n}</button>}\n```")
    assert r["type"] == "react", r["type"]
    r2 = parse_artifact_response("X.\n```\nexport default function App(){return <div>hi</div>}\n```")
    assert r2["type"] == "react"
    sc = react_scaffold(r["code"])
    assert all(x in sc for x in ["react@18", "babel", 'id="root"', "createRoot"]), "scaffold incomplet"
    assert "import " not in sc.split("text/plain")[1], "import non retiré du composant"
    # un vrai HTML ne doit PAS être pris pour du react
    assert parse_artifact_response("```html\n<!DOCTYPE html><html><body>x</body></html>\n```")["type"] == "html"
    print("OK test_react_detection_et_scaffold")


def test_mermaid_detection_et_scaffold():
    """Type 'mermaid' détecté (balise ou mot-clé) ; scaffold mermaid.js + code échappé."""
    from core.athenadesign_generator import parse_artifact_response, mermaid_scaffold
    r = parse_artifact_response("Flux.\n```mermaid\nflowchart TD\n A-->B\n```")
    assert r["type"] == "mermaid", r["type"]
    r2 = parse_artifact_response("```\nsequenceDiagram\n A->>B: hi\n```")
    assert r2["type"] == "mermaid"
    sc = mermaid_scaffold("classDiagram\n A <|-- B")
    assert "mermaid@11" in sc and 'class="mermaid"' in sc
    assert "&lt;|--" in sc, "le code mermaid doit être échappé (vit dans <pre>)"
    print("OK test_mermaid_detection_et_scaffold")


def test_pptx_anti_overflow_present():
    """Le code injecté force word_wrap + shrink-to-fit sur les .pptx produits (anti-débordement
    déterministe). Le code utilisateur reste encadré entre patches."""
    wrapped = r._patched_code("print('hello')")
    assert "print('hello')" in wrapped
    assert "TEXT_TO_FIT_SHAPE" in wrapped and "word_wrap" in wrapped, "post-traitement pptx absent"
    assert ".pptx" in wrapped
    print("OK test_pptx_anti_overflow_present")


def test_scan_outputs_categorise():
    import tempfile
    d = tempfile.mkdtemp(prefix="adscan_")
    for name in ("run.py", "plot_1.png", "plot_2.png", "plotly_1.html", "presentation.pptx"):
        open(os.path.join(d, name), "w").close()
    plots, interactive, other = r._scan_outputs(d)
    assert plots == ["plot_1.png", "plot_2.png"], plots
    assert interactive == ["plotly_1.html"], interactive
    assert [o["name"] for o in other] == ["presentation.pptx"], other
    assert not any(o["name"] == "run.py" for o in other), "run.py ne doit pas être listé"
    print("OK test_scan_outputs_categorise")


def test_execute_utilise_docker_quand_dispo():
    """Docker dispo + image résolue → passe par run_python_in_dir, sandboxed=True."""
    from tools import sandbox_runner
    with mock.patch.object(sandbox_runner, "sandbox_mode", return_value="docker"), \
         mock.patch.object(sandbox_runner, "docker_available", return_value=True), \
         mock.patch.object(r, "_ensure_design_image", return_value=("img:test", None)), \
         mock.patch.object(sandbox_runner, "run_python_in_dir", return_value=("out", "", 0)) as rp, \
         mock.patch.object(r, "_run_local") as local:
        res = r.execute_code("print(1)", "proj_docker")
    rp.assert_called_once()
    local.assert_not_called()
    assert res["sandboxed"] is True and res["success"] is True
    print("OK test_execute_utilise_docker_quand_dispo")


def test_execute_repli_local_si_pas_de_docker():
    """Docker indisponible → repli local non isolé, sandboxed=False."""
    from tools import sandbox_runner
    with mock.patch.object(sandbox_runner, "sandbox_mode", return_value="docker"), \
         mock.patch.object(sandbox_runner, "docker_available", return_value=False), \
         mock.patch.object(r, "_run_local", return_value=("out", "", True)) as local, \
         mock.patch.object(sandbox_runner, "run_python_in_dir") as rp:
        res = r.execute_code("print(1)", "proj_local")
    local.assert_called_once()
    rp.assert_not_called()
    assert res["sandboxed"] is False and res["success"] is True
    print("OK test_execute_repli_local_si_pas_de_docker")


def test_execute_repli_local_si_sandbox_off():
    """SANDBOX_MODE=off → repli local forcé même si Docker présent."""
    from tools import sandbox_runner
    with mock.patch.object(sandbox_runner, "sandbox_mode", return_value="off"), \
         mock.patch.object(sandbox_runner, "docker_available", return_value=True), \
         mock.patch.object(r, "_run_local", return_value=("", "", True)) as local, \
         mock.patch.object(sandbox_runner, "run_python_in_dir") as rp, \
         mock.patch.dict(os.environ, {"SANDBOX_MODE": "off"}):
        res = r.execute_code("print(1)", "proj_off")
    local.assert_called_once()
    rp.assert_not_called()
    assert res["sandboxed"] is False
    print("OK test_execute_repli_local_si_sandbox_off")


def test_charte_depuis_url():
    """Extraction de charte depuis une URL : HTML inline + feuille CSS liée (réseau mocké)."""
    import routers.athenadesign as ad
    html = ('<html><head><link rel="stylesheet" href="/site.css">'
            '<style>body{font-family: Outfit, sans-serif; color:#0ea5e9}</style></head><body></body></html>')
    css = ".btn{background:#f43f5e} h1{font-family: Inter}"
    class _R:
        def __init__(self, t): self.text = t
    def fake_get(u, **kw):
        return _R(css if u.endswith("site.css") else html)
    with mock.patch("requests.get", side_effect=fake_get), \
         mock.patch("tools.net_guard.is_blocked_url", return_value=False):
        raw = ad._fetch_web_styles("https://exemple.test/")
        ds = ad.extract_design_system(raw)
    assert "#0ea5e9" in ds and "#f43f5e" in ds, ds   # couleurs HTML inline + CSS liée
    assert "Outfit" in ds or "Inter" in ds, ds       # typo
    print("OK test_charte_depuis_url")


def test_autofix_corrige_un_script_python():
    """Auto-correction : 1er run échoue → le modèle corrige → 2e run réussit ; version ajoutée."""
    from fastapi.testclient import TestClient
    from core import projects as cp
    import routers.athenadesign as ad
    import server
    c = TestClient(server.app)
    proj = cp.create_project("AutofixTest")
    pid = proj["id"]
    ad.write_db("local", {pid: {"id": pid, "name": "AutofixTest", "history": [],
                "versions": [{"version": 1, "type": "python", "code": "raise ValueError()", "comments": []}]}})
    runs = {"n": 0}
    def fake_exec(code, project_id):
        runs["n"] += 1
        ok = runs["n"] >= 2  # échoue au 1er, réussit ensuite
        return {"success": ok, "stdout": "", "stderr": "" if ok else "Traceback ValueError", "other_files": [], "plots": [], "interactive_plots": [], "sandboxed": True}
    async def fake_gen(**kw):
        return {"type": "python", "code": "print('ok')", "explanation": "corrigé"}
    try:
        with mock.patch.object(ad.runner, "execute_code", side_effect=fake_exec), \
             mock.patch.object(ad.generator, "generate_design", side_effect=fake_gen):
            r = c.post("/api/athenadesign/autofix", json={"project_id": pid}).json()
        assert r["success"] is True and r["fixed"] is True, r
        assert r["attempts"] == 1 and r["versions_count"] == 2, r
        print("OK test_autofix_corrige_un_script_python")
    finally:
        try:
            cp.delete(pid, remove_files=True)
        except Exception:
            pass
        try:
            os.remove(ad._user_file("local"))
        except OSError:
            pass


def test_projets_unifies_code_et_design():
    """Unification : un projet créé via AthenaDesign est un VRAI projet Athena (visible côté
    code) et inversement un projet code apparaît dans AthenaDesign."""
    from fastapi.testclient import TestClient
    from core import projects as cp
    import server
    c = TestClient(server.app)
    created = []
    try:
        pid = c.post("/api/athenadesign/projects/new", json={"name": "UnifTest"}).json()["id"]
        created.append(pid)
        assert pid in {p["id"] for p in cp.list_projects()}, "projet design absent du registre code"
        cproj = cp.create_project("CodeOnly")
        created.append(cproj["id"])
        ad_ids = {p["id"] for p in c.get("/api/athenadesign/projects").json()}
        assert cproj["id"] in ad_ids, "projet code absent d'AthenaDesign"
        # accès refusé à un id inexistant
        assert c.get("/api/athenadesign/projects/deadbeef00").status_code == 404
        print("OK test_projets_unifies_code_et_design")
    finally:
        for x in created:
            try:
                cp.delete(x, remove_files=True)
            except Exception:
                pass
        try:
            os.remove(__import__("routers.athenadesign", fromlist=["_user_file"])._user_file("local"))
        except Exception:
            pass


def test_partage_lecture_seule():
    """Partage par jeton : accès public en lecture, 404 après révocation."""
    from fastapi.testclient import TestClient
    import routers.athenadesign as ad
    import server, os
    c = TestClient(server.app)
    pid = c.post("/api/athenadesign/projects/new", json={"name": "Shr"}).json()["id"]
    c.post("/api/athenadesign/chat", json={"project_id": pid, "prompt": "dashboard", "provider": "mock"})
    try:
        tok = c.post(f"/api/athenadesign/projects/{pid}/share").json()["token"]
        assert len(tok) == 32
        assert c.get(f"/api/athenadesign/shared/{tok}").status_code == 200
        assert c.get(f"/api/athenadesign/shared/{tok}/view").status_code == 200
        assert c.get("/api/athenadesign/shared/deadbeef/view").status_code == 404
        c.delete(f"/api/athenadesign/projects/{pid}/share")
        assert c.get(f"/api/athenadesign/shared/{tok}/view").status_code == 404, "révocation inefficace"
        print("OK test_partage_lecture_seule")
    finally:
        from core import projects as _cp
        try:
            _cp.delete(pid, remove_files=True)
        except Exception:
            pass
        for p in (ad._user_file("local"), ad._SHARED_INDEX):
            try:
                os.remove(p)
            except OSError:
                pass


def test_export_pdf_sans_chromium_renvoie_503():
    """Export PDF : message clair (503) si aucun Chromium ; ownership conservé."""
    from fastapi.testclient import TestClient
    from tools import browser_tools
    import routers.athenadesign as ad
    import server, os
    c = TestClient(server.app)
    pid = c.post("/api/athenadesign/projects/new", json={"name": "X"}).json()["id"]
    try:
        with mock.patch.object(browser_tools, "_find_chromium", return_value=None):
            r = c.post("/api/athenadesign/export/pdf",
                       json={"project_id": pid, "code": "<html></html>"})
        assert r.status_code == 503, r.status_code
        # projet inexistant → 404 (ownership)
        r2 = c.post("/api/athenadesign/export/pdf", json={"project_id": "deadbeef0001", "code": "<html></html>"})
        assert r2.status_code == 404
        print("OK test_export_pdf_sans_chromium_renvoie_503")
    finally:
        from core import projects as _cp
        try:
            _cp.delete(pid, remove_files=True)
        except Exception:
            pass
        try:
            os.remove(ad._user_file("local"))
        except OSError:
            pass


def test_extract_design_system_et_attachments():
    """Extraction de charte (couleurs/typo) depuis CSS + résolution des pièces jointes."""
    import routers.athenadesign as ad
    ds = ad.extract_design_system("a{color:#4f46e5} b{font-family: Inter, sans-serif} c{background:#f43f5e}")
    assert "#4f46e5" in ds and "#f43f5e" in ds and "Inter" in ds, ds
    ctx, imgs = ad._resolve_attachments([
        {"kind": "text", "text": "ton premium minimaliste"},
        {"kind": "image", "data_url": "data:image/png;base64,AAAA"},
    ])
    assert "premium" in ctx and len(imgs) == 1
    print("OK test_extract_design_system_et_attachments")


def test_design_system_et_vision_routing():
    """design_system injecté dans le système ; images envoyées en multimodal SI le modèle
    est vision, sinon note (marche sans vision)."""
    from core import athenadesign_generator as g
    from core import state

    captured = {}
    class _Msg:
        content = "<artifact_type>html</artifact_type><artifact_explanation>ok</artifact_explanation><artifact_code><div/></artifact_code>"
    class _Choice:
        message = _Msg()
    class _Resp:
        choices = [_Choice()]
    def fake_complete(model, messages, **kw):
        captured["messages"] = messages
        return _Resp()

    img = "data:image/png;base64,AAAA"

    # (a) Modèle VISION → image envoyée en multimodal + design_system dans le système.
    with mock.patch.object(state.swarm, "_complete", side_effect=fake_complete), \
         mock.patch.object(g, "_model_supports_vision", return_value=True):
        g._generate_via_athena("fais un hero", [], design_system="Couleurs: indigo/rose; Police: Inter",
                               images=[img])
    sys_msg = captured["messages"][0]["content"]
    user_msg = captured["messages"][-1]["content"]
    assert "DESIGN SYSTEM" in sys_msg and "indigo/rose" in sys_msg, "charte non injectée"
    assert isinstance(user_msg, list) and any(p.get("type") == "image_url" for p in user_msg), \
        "image non envoyée en multimodal au modèle vision"

    # (b) Modèle NON-vision + pas de VISION_MODEL → note, user en texte simple.
    with mock.patch.object(state.swarm, "_complete", side_effect=fake_complete), \
         mock.patch.object(g, "_model_supports_vision", return_value=False), \
         mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("VISION_MODEL", None)
        g._generate_via_athena("fais un hero", [], images=[img])
    user_msg2 = captured["messages"][-1]["content"]
    sys_msg2 = captured["messages"][0]["content"]
    assert isinstance(user_msg2, str), "sans vision, le message user doit rester du texte"
    assert "non analysées" in sys_msg2 or "multimodal" in sys_msg2, "note vision absente"
    print("OK test_design_system_et_vision_routing")


def test_projets_isoles_par_utilisateur():
    """Multi-tenant : chaque utilisateur ne voit que SES projets (bases séparées)."""
    import routers.athenadesign as ad
    a, b = "testalice_x", "testbob_x"
    try:
        ad.write_db(a, {"p1": {"id": "p1", "name": "Alice projet"}})
        ad.write_db(b, {"p2": {"id": "p2", "name": "Bob projet"}})
        da, db = ad.read_db(a), ad.read_db(b)
        assert "p1" in da and "p2" not in da, "Alice ne doit voir que ses projets"
        assert "p2" in db and "p1" not in db, "Bob ne doit voir que ses projets"
        # Sanitisation du nom d'utilisateur (anti chemin).
        assert ad._safe_user("../../etc") and "/" not in ad._safe_user("../../etc")
        print("OK test_projets_isoles_par_utilisateur")
    finally:
        for u in (a, b):
            try:
                os.remove(ad._user_file(u))
            except OSError:
                pass


def test_parse_artifact_separe_prose_et_code():
    """Le parser ne doit JAMAIS coller la prose du modèle dans le code (bug observé)."""
    from core.athenadesign_generator import parse_artifact_response

    # 1) Cas réel qwen3 : prose puis HTML SANS fence ni balise.
    raw1 = "Voici une interface premium.\nJ'ai utilisé du glassmorphism.\n<!DOCTYPE html>\n<html><body>x</body></html>"
    r1 = parse_artifact_response(raw1)
    assert r1["type"] == "html"
    assert r1["code"].startswith("<!DOCTYPE html>"), r1["code"][:40]
    assert "glassmorphism" in r1["explanation"] and "glassmorphism" not in r1["code"]

    # 2) Prose + bloc fencé ```html.
    raw2 = "Petit dashboard.\n```html\n<div>hi</div>\n```"
    r2 = parse_artifact_response(raw2)
    assert r2["code"] == "<div>hi</div>" and r2["explanation"] == "Petit dashboard."

    # 3) Balises explicites toujours honorées.
    raw3 = "<artifact_type>python</artifact_type><artifact_explanation>Plot</artifact_explanation><artifact_code>import x</artifact_code>"
    r3 = parse_artifact_response(raw3)
    assert r3["type"] == "python" and r3["code"] == "import x" and r3["explanation"] == "Plot"

    # 4) Python via fence + détection de type.
    r4 = parse_artifact_response("Génère un pptx.\n```python\nfrom pptx import Presentation\n```")
    assert r4["type"] == "python" and "Presentation" in r4["code"]

    # 5) Pure prose sans code → code vide (PAS de prose dumpée comme code).
    r5 = parse_artifact_response("Je ne peux pas faire ça.")
    assert r5["code"] == "" and "peux pas" in r5["explanation"]
    print("OK test_parse_artifact_separe_prose_et_code")


def test_generate_design_passe_par_l_infra_athena():
    """Par défaut (provider 'athena'), la génération passe par swarm._complete (infra LLM
    d'Athena : endpoint/clés/fallback), PAS par un chemin LLM externe séparé."""
    import asyncio
    from core import athenadesign_generator as g
    from core import state

    text = ("<artifact_type>python</artifact_type>"
            "<artifact_explanation>Présentation pptx</artifact_explanation>"
            "<artifact_code>from pptx import Presentation</artifact_code>")

    class _Msg:
        content = text
    class _Choice:
        message = _Msg()
    class _Resp:
        choices = [_Choice()]

    with mock.patch.object(state.swarm, "_complete", return_value=_Resp()) as cmpl:
        res = asyncio.run(g.generate_design("fais une présentation", [], provider="athena"))
    assert cmpl.called, "doit appeler swarm._complete (infra Athena)"
    assert res["type"] == "python" and "Presentation" in res["code"], res
    assert res["explanation"] == "Présentation pptx", res
    print("OK test_generate_design_passe_par_l_infra_athena")


def test_generate_design_mock_n_appelle_pas_le_llm():
    """provider='mock' → template hors-ligne, sans toucher à l'infra LLM."""
    import asyncio
    from core import athenadesign_generator as g
    from core import state
    with mock.patch.object(state.swarm, "_complete") as cmpl:
        res = asyncio.run(g.generate_design("un dashboard", [], provider="mock"))
    cmpl.assert_not_called()
    assert res.get("type") in ("html", "python") and res.get("code"), res
    print("OK test_generate_design_mock_n_appelle_pas_le_llm")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nTous les tests athenadesign passent.")
