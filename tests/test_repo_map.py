"""Repo-map : classement par CENTRALITÉ (fichier le plus référencé en tête)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.repo_map import build_repo_map  # noqa: E402


def _mkproj():
    d = tempfile.mkdtemp(prefix="athena_repomap_")
    open(os.path.join(d, "utils.py"), "w").write("def helper():\n    return 1\nclass Base:\n    pass\n")
    open(os.path.join(d, "a.py"), "w").write("from utils import helper\nprint(helper())\n")
    open(os.path.join(d, "b.py"), "w").write("import utils\nutils.helper()\n")
    open(os.path.join(d, "c.py"), "w").write("from utils import helper\nhelper()\n")
    open(os.path.join(d, "main.py"), "w").write("def main():\n    return 0\n")
    open(os.path.join(d, "README.md"), "w").write("# projet\n")
    return d


def test_central_file_ranked_first():
    m = build_repo_map(root=_mkproj())
    lines = m.splitlines()
    iu = next(i for i, l in enumerate(lines) if l.startswith("• utils.py"))
    im = next(i for i, l in enumerate(lines) if l.startswith("• main.py"))
    assert iu < im, "le fichier le plus référencé (utils.py) doit être listé avant main.py"
    assert "⭐" in lines[iu], "utils.py doit porter un score de centralité"


def test_symbols_listed_and_others_section():
    m = build_repo_map(root=_mkproj())
    assert "def helper():" in m and "class Base:" in m   # symboles extraits
    assert "Autres fichiers" in m and "README.md" in m   # non-code en fin


def test_empty_project():
    assert build_repo_map(root=tempfile.mkdtemp()) == "(projet vide)"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests repo_map passent.")
