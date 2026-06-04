"""Repo-map : carte compacte du projet (arborescence + symboles clés par fichier).

Inspiré d'Aider : on donne à l'agent de code une vue du projet (fichiers + définitions
de haut niveau) sans lui envoyer tout le code, pour qu'il comprenne la structure et ne
« code pas à l'aveugle ». Budget de lignes borné pour ne pas exploser le contexte.
"""
import os
import re

_IGNORE_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".gemini",
                "dist", "build", ".next", ".cache", "target", ".idea", ".vscode"}
_CODE_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
             ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".sh", ".sql", ".vue", ".svelte"}

# Symboles « importants » par langage (regex sur début de ligne, indentation faible).
_PATTERNS = [
    re.compile(r"^\s{0,4}(?:export\s+)?(?:async\s+)?def\s+\w+\s*\([^)]*\)"),          # python def
    re.compile(r"^\s{0,4}class\s+\w+"),                                                # class
    re.compile(r"^\s{0,4}(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w+"),   # js function
    re.compile(r"^\s{0,4}(?:export\s+)?const\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),# js arrow fn
    re.compile(r"^\s{0,4}(?:pub\s+)?fn\s+\w+"),                                        # rust fn
    re.compile(r"^\s{0,4}func\s+\w+"),                                                 # go func
    re.compile(r"^\s{0,4}(?:public|private|protected).*\b\w+\s*\([^)]*\)\s*\{?"),      # java/c# method
]


def _symbols(path: str, max_syms: int) -> list:
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if len(out) >= max_syms:
                    break
                s = line.rstrip("\n")
                if any(p.match(s) for p in _PATTERNS):
                    out.append(s.strip()[:120])
    except Exception:
        pass
    return out


def build_repo_map(root: str = None, max_files: int = 120, max_syms_per_file: int = 12,
                   max_lines: int = 400) -> str:
    """Carte compacte du projet `root` (défaut : workspace actif). Renvoie une chaîne."""
    if root is None:
        try:
            from core.state import get_workspace_dir
            root = get_workspace_dir()
        except Exception:
            root = os.getcwd()
    root = os.path.abspath(root)
    files = []
    for dirpath, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            files.append(rel)
            if len(files) > max_files * 4:
                break
    files.sort()
    if not files:
        return "(projet vide)"

    lines = [f"Carte du projet ({len(files)} fichier(s)) — racine = {os.path.basename(root) or root} :"]
    shown = 0
    for rel in files[:max_files]:
        ext = os.path.splitext(rel)[1].lower()
        if ext in _CODE_EXT:
            syms = _symbols(os.path.join(root, rel), max_syms_per_file)
            lines.append(f"• {rel}")
            for s in syms:
                lines.append(f"    {s}")
                shown += 1
        else:
            lines.append(f"• {rel}")
        if len(lines) >= max_lines:
            lines.append("… (carte tronquée)")
            break
    return "\n".join(lines)
