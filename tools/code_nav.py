"""Intelligence de code légère (sans serveur LSP) : recherche, définitions, références
et plan de fichier, confinés au workspace.

S'appuie sur ripgrep (`rg`) si présent (rapide, respecte .gitignore), avec repli
Python pur. Les définitions/plans utilisent des motifs regex multi-langages — ~70 %
de la valeur d'un LSP, offline et sans cycle de vie de serveur à gérer.
"""
import os
import re
import shutil
import subprocess

_IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
                ".pytest_cache", "dist", "build", ".next", ".chroma_db", ".idea", ".vscode"}
_TEXT_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".h",
             ".cpp", ".hpp", ".cs", ".rb", ".php", ".sh", ".yaml", ".yml", ".json",
             ".html", ".css", ".scss", ".md", ".txt", ".toml", ".cfg", ".ini", ".sql"}
_MAX = 80


def _ws():
    try:
        from core.state import get_workspace_dir
        return os.path.realpath(get_workspace_dir())
    except Exception:
        base = os.getenv("ACTIVE_WORKSPACE_DIR", "").strip() or os.path.join(os.getcwd(), "workspace")
        return os.path.realpath(base)


def _resolve(path, must_exist):
    name = (path or "").strip().strip('"').strip("'")
    ws = _ws()
    cand = name if (name and os.path.isabs(name)) else os.path.join(ws, name)
    real = os.path.realpath(cand)
    if os.path.commonpath([real, ws]) != ws:
        return None, "Erreur : accès hors du workspace refusé."
    if must_exist and not os.path.exists(real):
        return None, f"Erreur : introuvable : {name}"
    return real, None


def _rg_available():
    return shutil.which("rg") is not None


def _rg(patterns, root, word=False, extra=None):
    """Lance ripgrep avec une ou plusieurs regex (-e). Renvoie une liste 'file:line:text'."""
    cmd = ["rg", "--line-number", "--no-heading", "--color", "never", "--max-count", "50"]
    if word:
        cmd.append("-w")
    if extra:
        cmd += extra
    for p in patterns:
        cmd += ["-e", p]
    cmd += ["--", root]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        return None, str(e)
    lines = [l for l in (res.stdout or "").splitlines() if l.strip()]
    return lines, None


def _py_search(regexes, root, max_results=_MAX):
    """Repli Python pur (pas de rg) : parcourt les fichiers texte du workspace."""
    out = []
    compiled = [re.compile(r) for r in regexes]
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS and not d.startswith(".")]
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in _TEXT_EXT:
                continue
            fp = os.path.join(dirpath, fn)
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if any(c.search(line) for c in compiled):
                            rel = os.path.relpath(fp, root)
                            out.append(f"{rel}:{i}:{line.rstrip()[:200]}")
                            if len(out) >= max_results:
                                return out
            except Exception:
                continue
    return out


def _format(lines, root, title, max_results=_MAX):
    if lines is None:
        return f"Erreur lors de la recherche ({title})."
    # Normaliser les chemins absolus rg -> relatifs au workspace.
    norm = []
    for l in lines[:max_results]:
        if l.startswith(root + os.sep):
            l = l[len(root) + 1:]
        norm.append(l)
    if not norm:
        return f"Aucun résultat pour {title}."
    extra = "" if len(lines) <= max_results else f"\n… (+{len(lines) - max_results} autres)"
    return f"[{title} — {len(norm)} résultat(s)]\n" + "\n".join(norm) + extra


def search_code(pattern: str, path: str = "") -> str:
    """
    Recherche une expression régulière dans le code du workspace (façon grep/ripgrep),
    en renvoyant fichier:ligne:contenu. path: limiter à un sous-dossier (optionnel).
    """
    pattern = (pattern or "").strip()
    if not pattern:
        return "Erreur : motif de recherche vide."
    root, err = _resolve(path or ".", must_exist=True)
    if err:
        return err
    if _rg_available():
        lines, e = _rg([pattern], root)
        if e:
            return f"Erreur ripgrep : {e}"
    else:
        try:
            lines = _py_search([pattern], root)
        except re.error as e:
            return f"Erreur : regex invalide ({e})."
    return _format(lines, _ws(), f"recherche /{pattern}/")


def find_references(symbol: str) -> str:
    """
    Trouve toutes les utilisations d'un symbole (fonction, variable, classe) dans le
    workspace, en correspondance de mot entier. Renvoie fichier:ligne:contenu.
    """
    symbol = (symbol or "").strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
        return "Erreur : fournis un identifiant simple (lettres/chiffres/_)."
    root = _ws()
    if _rg_available():
        lines, e = _rg([re.escape(symbol)], root, word=True)
        if e:
            return f"Erreur ripgrep : {e}"
    else:
        lines = _py_search([r"\b" + re.escape(symbol) + r"\b"], root)
    return _format(lines, root, f"références de « {symbol} »")


def _definition_patterns(symbol: str):
    s = re.escape(symbol)
    return [
        rf"^\s*(def|class)\s+{s}\b",                         # Python
        rf"\b(function|class)\s+{s}\b",                      # JS/TS
        rf"\b(const|let|var)\s+{s}\s*=",                     # JS/TS assignation
        rf"\bfunc\s+(\([^)]*\)\s*)?{s}\b",                   # Go
        rf"\bfn\s+{s}\b",                                    # Rust
        rf"\b(struct|enum|trait|interface|type|class|record|namespace|module)\s+{s}\b",  # OOP (Java/C#/C++/Ruby…)
        rf"\bdef\s+{s}\b",                                    # Ruby/Python
        rf"^[\w\s:<>\*&\[\],]*\b{s}\s*\([^;{{)]*\)\s*\{{",    # fonction/méthode C-family (corps {)
        rf"^\s*{s}\s*[:=]\s*(async\s+)?(function|\()",       # méthode/propriété
    ]


def find_definition(symbol: str) -> str:
    """
    Localise la (les) définition(s) d'un symbole — def/class (Python), function/class/
    const (JS/TS), func (Go), fn/struct/trait (Rust)… Renvoie fichier:ligne:contenu.
    """
    symbol = (symbol or "").strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
        return "Erreur : fournis un identifiant simple (lettres/chiffres/_)."
    root = _ws()
    pats = _definition_patterns(symbol)
    if _rg_available():
        lines, e = _rg(pats, root)
        if e:
            return f"Erreur ripgrep : {e}"
    else:
        try:
            lines = _py_search(pats, root)
        except re.error as e:
            return f"Erreur regex : {e}"
    return _format(lines, root, f"définition de « {symbol} »", max_results=30)


_OUTLINE_PATTERNS = {
    ".py": [r"^\s*(?:async\s+)?def\s+(\w+)", r"^\s*class\s+(\w+)"],
    ".js": [r"\bfunction\s+(\w+)", r"\bclass\s+(\w+)", r"\b(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\("],
    ".ts": [r"\bfunction\s+(\w+)", r"\bclass\s+(\w+)", r"\b(?:export\s+)?(?:const|function|class)\s+(\w+)"],
    ".go": [r"\bfunc\s+(?:\([^)]*\)\s*)?(\w+)", r"\btype\s+(\w+)"],
    ".rs": [r"\bfn\s+(\w+)", r"\b(?:struct|enum|trait)\s+(\w+)"],
    # Famille C / OOP : type de retour + nom + (...) + { , et déclarations de type.
    ".java": [r"\b(?:class|interface|enum|record)\s+(\w+)",
              r"^[\w\s:<>\[\],]*\b(\w+)\s*\([^;{)]*\)\s*\{"],
    ".cs":   [r"\b(?:class|interface|enum|struct|record|namespace)\s+(\w+)",
              r"^[\w\s:<>\[\],]*\b(\w+)\s*\([^;{)]*\)\s*\{"],
    ".cpp":  [r"\b(?:class|struct|enum)\s+(\w+)",
              r"^[\w\s:<>\*&\[\],]*\b(\w+)\s*\([^;{)]*\)\s*\{"],
    ".cc":   [r"\b(?:class|struct|enum)\s+(\w+)",
              r"^[\w\s:<>\*&\[\],]*\b(\w+)\s*\([^;{)]*\)\s*\{"],
    ".c":    [r"^[\w\s:<>\*&\[\],]*\b(\w+)\s*\([^;{)]*\)\s*\{", r"\b(?:struct|enum)\s+(\w+)"],
    ".h":    [r"^[\w\s:<>\*&\[\],]*\b(\w+)\s*\([^;{)]*\)\s*[\{;]", r"\b(?:class|struct|enum)\s+(\w+)"],
    ".hpp":  [r"^[\w\s:<>\*&\[\],]*\b(\w+)\s*\([^;{)]*\)\s*[\{;]", r"\b(?:class|struct|enum)\s+(\w+)"],
    ".rb":   [r"\bdef\s+(\w+)", r"\b(?:class|module)\s+(\w+)"],
    ".php":  [r"\bfunction\s+(\w+)", r"\b(?:class|trait|interface)\s+(\w+)"],
}


def file_outline(path: str) -> str:
    """
    Donne le PLAN d'un fichier de code : ses fonctions/classes/types principaux avec
    leur numéro de ligne. Utile pour comprendre un fichier sans tout lire.
    path: chemin relatif au workspace.
    """
    real, err = _resolve(path, must_exist=True)
    if err:
        return err
    ext = os.path.splitext(real)[1].lower()
    pats = _OUTLINE_PATTERNS.get(ext)
    if not pats:
        pats = [r"^\s*(?:async\s+)?def\s+(\w+)", r"\bfunction\s+(\w+)",
                r"\bfunc\s+(\w+)", r"\bfn\s+(\w+)",
                r"\b(?:class|struct|interface|enum|trait|module|record)\s+(\w+)",
                r"^[\w\s:<>\*&\[\],]*\b(\w+)\s*\([^;{)]*\)\s*\{"]
    compiled = [re.compile(p) for p in pats]
    out = []
    try:
        with open(real, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                for c in compiled:
                    m = c.search(line)
                    if m:
                        out.append(f"{str(i).rjust(5)}  {line.strip()[:120]}")
                        break
    except Exception as e:
        return f"Erreur de lecture : {e}"
    if not out:
        return f"(aucun symbole de premier niveau détecté dans {os.path.basename(real)})"
    return f"[plan de {os.path.basename(real)} — {len(out)} symbole(s)]\n" + "\n".join(out)
