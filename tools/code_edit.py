"""Outils d'édition de code/fichiers NON destructifs, confinés au workspace.

Remplace l'édition « à la sed/echo » via le shell (destructive, coûteuse en tokens,
source de corruption). Modèle éprouvé (Claude Code / Aider) :
  - read_file   : lit avec numéros de ligne (indispensable pour des éditions précises)
  - edit_file   : remplacement de chaîne EXACTE (str-replace), unicité exigée
  - write_file  : création / réécriture complète
  - apply_patch : application d'un diff unifié (multi-hunks)

Toutes les écritures sont ATOMIQUES (tmp + os.replace) et bornées au workspace
(anti-traversée de répertoire). Les chemins hors workspace sont refusés.
"""
import os
import tempfile


def _workspace_dir():
    try:
        import server
        return os.path.realpath(server.get_workspace_dir())
    except Exception:
        base = os.getenv("ACTIVE_WORKSPACE_DIR", "").strip() or os.path.join(os.getcwd(), "workspace")
        return os.path.realpath(base)


def _resolve(path: str, must_exist: bool):
    """Résout `path` dans le workspace (anti-traversée). Renvoie (abspath, None) ou (None, err)."""
    name = (path or "").strip().strip('"').strip("'")
    if not name:
        return None, "Erreur : chemin de fichier vide."
    ws = _workspace_dir()
    cand = name if os.path.isabs(name) else os.path.join(ws, name)
    real = os.path.realpath(cand)
    if os.path.commonpath([real, ws]) != ws:
        return None, "Erreur : accès hors du workspace refusé."
    if must_exist and not os.path.isfile(real):
        return None, f"Erreur : fichier introuvable : {name}"
    return real, None


def _atomic_write(real_path: str, content: str):
    directory = os.path.dirname(real_path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".edit-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, real_path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """
    Lit un fichier texte du workspace avec NUMÉROS DE LIGNE (nécessaires pour éditer
    ensuite précisément). Optionnellement borné à [start_line, end_line] (1-indexé).
    path: chemin relatif au workspace (ex: 'src/app.py').
    """
    real, err = _resolve(path, must_exist=True)
    if err:
        return err
    try:
        with open(real, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return f"Erreur de lecture : {e}"
    s = max(1, int(start_line or 1))
    e = int(end_line) if end_line else len(lines)
    e = min(e, len(lines))
    if s > len(lines):
        return f"(fichier de {len(lines)} lignes ; start_line={s} hors limites)"
    width = len(str(e))
    out = [f"{str(i).rjust(width)}\t{lines[i-1]}" for i in range(s, e + 1)]
    header = f"[{os.path.basename(real)} — lignes {s}-{e}/{len(lines)}]\n"
    return header + "\n".join(out)


def write_file(path: str, content: str) -> str:
    """
    Crée ou REMPLACE intégralement un fichier du workspace (écriture atomique).
    À utiliser pour un nouveau fichier ; pour une modification ciblée, préfère edit_file.
    path: chemin relatif au workspace. content: contenu complet du fichier.
    """
    real, err = _resolve(path, must_exist=False)
    if err:
        return err
    existed = os.path.isfile(real)
    try:
        _atomic_write(real, content)
    except Exception as e:
        return f"Erreur d'écriture : {e}"
    n = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
    return f"{'Remplacé' if existed else 'Créé'} : {path} ({n} lignes)."


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """
    Édition NON destructive par remplacement de chaîne EXACTE (comme un str-replace).
    `old_string` doit apparaître TEL QUEL dans le fichier et être UNIQUE (sauf
    replace_all=True). Échoue sans rien écrire si introuvable ou ambigu — c'est le
    moyen le plus sûr et le plus économe en tokens pour modifier un fichier existant.
    path: chemin relatif au workspace. old_string: texte exact à remplacer (avec son
    indentation). new_string: texte de remplacement. replace_all: remplace toutes les
    occurrences au lieu d'exiger l'unicité.
    """
    real, err = _resolve(path, must_exist=True)
    if err:
        return err
    if old_string == new_string:
        return "Erreur : old_string et new_string sont identiques."
    try:
        with open(real, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"Erreur de lecture : {e}"
    count = content.count(old_string)
    if count == 0:
        return ("Erreur : old_string introuvable tel quel (vérifie l'indentation et les "
                "espaces ; lis d'abord le fichier avec read_file).")
    if count > 1 and not replace_all:
        return (f"Erreur : old_string apparaît {count} fois (ambigu). Ajoute du contexte "
                "pour le rendre unique, ou utilise replace_all=True.")
    new_content = content.replace(old_string, new_string)
    try:
        _atomic_write(real, new_content)
    except Exception as e:
        return f"Erreur d'écriture : {e}"
    return f"Modifié : {path} ({count} remplacement{'s' if count > 1 else ''})."


def _apply_unified_diff(original: str, patch: str):
    """Applique un diff unifié. Renvoie (nouveau_texte, None) ou (None, raison).
    Matche le contexte + lignes supprimées ; refuse proprement si ça ne colle pas."""
    orig_lines = original.splitlines(keepends=True)
    patch_lines = patch.splitlines()
    result = []
    idx = 0  # position courante dans orig_lines
    i = 0
    n = len(patch_lines)
    applied = 0
    while i < n:
        line = patch_lines[i]
        if line.startswith("--- ") or line.startswith("+++ "):
            i += 1
            continue
        if line.startswith("@@"):
            # @@ -l,s +l,s @@  : on récupère la ligne de départ côté original.
            try:
                seg = line.split("-", 1)[1].split(" ", 1)[0]
                start = int(seg.split(",")[0])
            except Exception:
                return None, f"hunk illisible : {line!r}"
            target = max(0, start - 1)
            # Copier tout l'inchangé jusqu'au début du hunk.
            if target < idx:
                return None, "hunks non ordonnés ou se chevauchant."
            result.extend(orig_lines[idx:target])
            idx = target
            i += 1
            # Traiter les lignes du hunk.
            while i < n and not patch_lines[i].startswith("@@"):
                pl = patch_lines[i]
                if pl.startswith("--- ") or pl.startswith("+++ "):
                    break
                tag, text = (pl[0], pl[1:]) if pl else (" ", "")
                if tag == " ":
                    if idx >= len(orig_lines) or orig_lines[idx].rstrip("\n") != text:
                        return None, f"contexte ne correspond pas à la ligne {idx+1} : {text!r}"
                    result.append(orig_lines[idx]); idx += 1
                elif tag == "-":
                    if idx >= len(orig_lines) or orig_lines[idx].rstrip("\n") != text:
                        return None, f"ligne à supprimer absente à la ligne {idx+1} : {text!r}"
                    idx += 1
                elif tag == "+":
                    result.append(text + "\n")
                    applied += 1
                else:
                    # ligne hors format (ex: "\ No newline at end of file") : ignorée
                    pass
                i += 1
        else:
            i += 1
    result.extend(orig_lines[idx:])
    if applied == 0:
        return None, "aucune ligne ajoutée — diff vide ou mal formé."
    return "".join(result), None


def apply_patch(path: str, patch: str) -> str:
    """
    Applique un DIFF UNIFIÉ (format `diff -u` / git) à un fichier du workspace, par
    hunks avec vérification du contexte (refuse proprement si le contexte ne colle pas,
    sans rien écrire). Idéal pour des modifications multi-endroits en un seul appel.
    path: chemin relatif au workspace. patch: le diff unifié (lignes @@, -, +, espace).
    """
    real, err = _resolve(path, must_exist=True)
    if err:
        return err
    try:
        with open(real, "r", encoding="utf-8") as f:
            original = f.read()
    except Exception as e:
        return f"Erreur de lecture : {e}"
    new_content, reason = _apply_unified_diff(original, patch or "")
    if reason:
        return f"Erreur : patch non appliqué ({reason})."
    try:
        _atomic_write(real, new_content)
    except Exception as e:
        return f"Erreur d'écriture : {e}"
    return f"Patch appliqué : {path}."
