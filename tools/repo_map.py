"""Repo-map : carte compacte du projet (fichiers + symboles clés), TRIÉE PAR CENTRALITÉ.

Inspiré d'Aider : on donne à l'agent de code une vue du projet (fichiers + définitions de
haut niveau) sans lui envoyer tout le code, pour qu'il comprenne la structure et ne « code
pas à l'aveugle ». Budget de lignes borné.

Classement (approximation légère du PageRank d'Aider, SANS dépendance) : chaque fichier est
noté par sa CENTRALITÉ = nombre d'autres fichiers qui référencent ses symboles définis
(def/class/fonction). Un fichier-clé (utilitaires, modèles, core…) référencé partout remonte
en tête ; un fichier feuille descend. À budget contraint, on montre d'abord les plus centraux.
"""
import os
import re
from collections import defaultdict

_IGNORE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".gemini",
                "dist", "build", ".next", ".cache", "target", ".idea", ".vscode"}
_CODE_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
             ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".sh", ".sql", ".vue", ".svelte"}

# Symboles « importants » par langage : (regex sur début de ligne, nom capturé en groupe 1).
_PATTERNS = [
    re.compile(r"^\s{0,4}(?:export\s+)?(?:async\s+)?def\s+(\w+)\s*\("),               # python def
    re.compile(r"^\s{0,4}class\s+(\w+)"),                                              # class
    re.compile(r"^\s{0,4}(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)"), # js function
    re.compile(r"^\s{0,4}(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),  # js arrow fn
    re.compile(r"^\s{0,4}(?:pub\s+)?fn\s+(\w+)"),                                      # rust fn
    re.compile(r"^\s{0,4}func\s+(?:\([^)]*\)\s*)?(\w+)"),                              # go func/méthode
]
_IDENT_RE = re.compile(r"[A-Za-z_]\w{2,}")  # identifiants (≥3 car. → moins de bruit)


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _symbols_and_names(content: str, max_syms: int):
    """Renvoie (lignes de symboles affichables, ensemble des NOMS définis)."""
    display, names = [], set()
    for line in content.splitlines():
        if len(display) >= max_syms:
            break
        s = line.rstrip()
        for p in _PATTERNS:
            m = p.match(s)
            if m:
                display.append(s.strip()[:120])
                names.add(m.group(1))
                break
    return display, names


def build_repo_map(root: str = None, max_files: int = 120, max_syms_per_file: int = 12,
                   max_lines: int = 400) -> str:
    """Carte compacte du projet `root` (défaut : workspace actif), triée par centralité."""
    if root is None:
        try:
            from core.state import get_workspace_dir
            root = get_workspace_dir()
        except Exception:
            root = os.getcwd()
    root = os.path.abspath(root)

    all_files, code_files = [], []
    for dirpath, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            all_files.append(rel)
            if os.path.splitext(fn)[1].lower() in _CODE_EXT:
                code_files.append(rel)
        if len(all_files) > max_files * 6:
            break
    if not all_files:
        return "(projet vide)"

    # 1) Lecture + extraction des symboles (sur un sous-ensemble borné de fichiers de code).
    code_files = sorted(code_files)[: max_files * 2]
    info = {}                  # rel -> {"display":[...], "names":set}
    contents = {}
    all_names = set()
    for rel in code_files:
        c = _read(os.path.join(root, rel))
        contents[rel] = c
        disp, names = _symbols_and_names(c, max_syms_per_file)
        info[rel] = {"display": disp, "names": names}
        all_names |= names

    # 2) Index inversé RESTREINT aux noms définis : fichier -> noms (définis ailleurs) qu'il cite.
    files_with = defaultdict(set)   # nom -> {fichiers qui le citent}
    for rel in code_files:
        cited = {t for t in _IDENT_RE.findall(contents.get(rel, "")) if t in all_names}
        for n in cited:
            files_with[n].add(rel)

    # 3) Score de centralité = nb d'AUTRES fichiers citant un des symboles définis par le fichier.
    def _score(rel):
        refs = set()
        for n in info[rel]["names"]:
            refs |= files_with.get(n, ())
        refs.discard(rel)
        return len(refs)

    scored = sorted(code_files, key=lambda r: (-_score(r), r))

    lines = [f"Carte du projet ({len(all_files)} fichier(s), triée par centralité) — "
             f"racine = {os.path.basename(root) or root} :"]
    for rel in scored:
        sc = _score(rel)
        tag = f"  ⭐×{sc}" if sc else ""
        lines.append(f"• {rel}{tag}")
        for s in info[rel]["display"]:
            lines.append(f"    {s}")
        if len(lines) >= max_lines:
            lines.append("… (carte tronquée — fichiers les plus centraux montrés en premier)")
            return "\n".join(lines)

    # 4) Autres fichiers (non-code / sans symbole) : liste compacte en fin.
    others = sorted(set(all_files) - set(code_files))
    if others and len(lines) < max_lines:
        lines.append("Autres fichiers :")
        for rel in others:
            lines.append(f"• {rel}")
            if len(lines) >= max_lines:
                lines.append("… (tronqué)")
                break
    return "\n".join(lines)
