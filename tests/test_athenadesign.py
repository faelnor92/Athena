"""AthenaDesign : runner durci (sandbox Docker prioritaire, repli local journalisé).

Tests SANS Docker réel (mock) : choix du mode d'exécution + scan des sorties.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import athenadesign_runner as r  # noqa: E402


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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nTous les tests athenadesign passent.")
