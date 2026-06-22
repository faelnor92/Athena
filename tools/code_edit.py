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
        from core.state import get_workspace_dir
        return os.path.realpath(get_workspace_dir())
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
    # Lecture seule : un membre « viewer » d'un projet partagé ne peut pas écrire.
    try:
        from core import projects
        if not projects.can_write():
            raise PermissionError("projet en LECTURE SEULE (rôle lecteur) — modification refusée.")
    except PermissionError:
        raise
    except Exception:
        pass
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


def _diagnostics_suffix(real_path: str, rel_path: str, content: str) -> str:
    """Boucle de feedback (façon opencode/Claude Code) : après une écriture réussie, renvoie
    les erreurs/avertissements introduits dans le fichier pour que l'agent corrige tout de
    suite. Non bloquant : chaîne vide si rien à signaler ou si l'analyse échoue."""
    try:
        from tools import lsp_client
        return lsp_client.format_for_agent(rel_path, lsp_client.diagnostics(real_path, content))
    except Exception:
        return ""


def read_file(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """
    Lit un fichier texte du workspace avec NUMÉROS DE LIGNE. À utiliser AVANT edit_file pour
    copier le texte exact à remplacer (le numéro de ligne + tabulation n'est PAS du contenu :
    ne l'inclus jamais dans old_string). Optionnellement borné à [start_line, end_line] (1-indexé).
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
    Crée ou REMPLACE intégralement un fichier du workspace (écriture atomique). Réserve cet
    outil aux NOUVEAUX fichiers : pour modifier un fichier existant, préfère TOUJOURS edit_file
    (plus sûr, économe en tokens, ne risque pas d'écraser le reste). Renvoie aussi les
    diagnostics introduits dans le fichier.
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
    return f"{'Remplacé' if existed else 'Créé'} : {path} ({n} lignes)." + _diagnostics_suffix(real, path, content)


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """
    Édition NON destructive par remplacement de chaîne EXACTE (comme un str-replace) — moyen
    PRIVILÉGIÉ pour modifier un fichier existant (sûr, économe en tokens). Renvoie aussi les
    diagnostics (erreurs/avertissements) introduits dans le fichier : corrige-les si présents.

    RÈGLES :
    - LIS le fichier avec read_file AVANT d'éditer, pour copier le texte EXACT (l'édition
      échoue sans rien écrire si old_string est introuvable).
    - Préserve l'INDENTATION exacte (espaces/tabulations) telle qu'affichée APRÈS le numéro
      de ligne de read_file — n'inclus JAMAIS le préfixe « numéro + tabulation » dans old_string.
    - old_string doit être UNIQUE : s'il apparaît plusieurs fois, l'édition échoue → ajoute des
      lignes de contexte autour pour le rendre unique, ou mets replace_all=True.
    - Préfère ÉDITER un fichier existant plutôt qu'en réécrire un (write_file).

    path: chemin relatif au workspace. old_string: texte exact à remplacer (avec son
    indentation). new_string: texte de remplacement. replace_all: remplace toutes les
    occurrences au lieu d'exiger l'unicité (utile pour renommer une variable partout).
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
    if count > 1 and not replace_all:
        return (f"Erreur : old_string apparaît {count} fois (ambigu). Ajoute du contexte "
                "pour le rendre unique, ou utilise replace_all=True.")
    if count >= 1:
        new_content = content.replace(old_string, new_string) if replace_all \
            else content.replace(old_string, new_string, 1)
        try:
            _atomic_write(real, new_content)
        except Exception as e:
            return f"Erreur d'écriture : {e}"
        return (f"Modifié : {path} ({count if replace_all else 1} remplacement{'s' if (replace_all and count > 1) else ''})."
                + _diagnostics_suffix(real, path, new_content))

    # Repli TOLÉRANT (style Aider) : old_string introuvable au caractère près → on tente
    # une correspondance en ignorant l'indentation/les espaces de bord, puis on réindente
    # new_string sur l'indentation réelle du fichier.
    flexible, fcount = _flexible_replace(content, old_string, new_string, replace_all)
    if flexible is not None:
        try:
            _atomic_write(real, flexible)
        except Exception as e:
            return f"Erreur d'écriture : {e}"
        return (f"Modifié : {path} ({fcount} remplacement{'s' if fcount > 1 else ''}, correspondance tolérante aux espaces)."
                + _diagnostics_suffix(real, path, flexible))
    if fcount == -1:
        return ("Erreur : correspondance tolérante AMBIGUË (plusieurs blocs similaires). "
                "Ajoute du contexte unique ou utilise replace_all=True.")

    # Échec total → message utile : on suggère le bloc le plus proche dans le fichier.
    return ("Erreur : old_string introuvable (même en ignorant les espaces). "
            "Lis le fichier avec read_file pour copier le texte exact.\n" + _suggest_similar(content, old_string))


def _flexible_replace(content: str, old: str, new: str, replace_all: bool):
    """Correspondance ligne-à-ligne en ignorant l'indentation/espaces de bord. Réindente
    new sur l'indentation réelle du bloc trouvé. Renvoie (nouveau_contenu, n) ; (None, 0)
    si introuvable ; (None, -1) si ambigu."""
    old_lines = old.splitlines()
    while old_lines and not old_lines[-1].strip():
        old_lines.pop()
    if not old_lines:
        return None, 0
    c_lines = content.splitlines(keepends=True)
    bare = [l.rstrip("\n") for l in c_lines]
    target = [l.strip() for l in old_lines]
    nL = len(old_lines)
    starts = [i for i in range(len(bare) - nL + 1)
              if [bare[i + j].strip() for j in range(nL)] == target]
    if not starts:
        return None, 0
    if len(starts) > 1 and not replace_all:
        return None, -1

    # Indentation de référence dans old (1ère ligne non vide) pour préserver le relatif.
    old_base = old_lines[0][:len(old_lines[0]) - len(old_lines[0].lstrip())]
    new_lines = new.splitlines()
    out, last, n = [], 0, 0
    for start in starts:
        out.extend(c_lines[last:start])
        file_indent = c_lines[start][:len(c_lines[start]) - len(c_lines[start].lstrip())]
        for nl in new_lines:
            if not nl.strip():
                out.append("\n")
                continue
            rel = nl[len(old_base):] if nl.startswith(old_base) else nl.lstrip()
            out.append(file_indent + rel + "\n")
        last = start + nL
        n += 1
        if not replace_all:
            break
    out.extend(c_lines[last:])
    return "".join(out), n


def _suggest_similar(content: str, old: str) -> str:
    """Renvoie le bloc du fichier le plus proche de `old` (aide l'agent à se corriger)."""
    import difflib
    old_lines = [l for l in old.splitlines() if l.strip()]
    if not old_lines:
        return ""
    c_lines = content.splitlines()
    nL = len(old_lines)
    best, best_ratio = None, 0.0
    for i in range(max(1, len(c_lines) - nL + 1)):
        window = "\n".join(c_lines[i:i + nL])
        r = difflib.SequenceMatcher(None, old, window).ratio()
        if r > best_ratio:
            best_ratio, best = r, (i, window)
    if best and best_ratio > 0.5:
        return f"Bloc le plus proche (lignes {best[0]+1}–{best[0]+nL}, similarité {int(best_ratio*100)}%) :\n{best[1]}"
    return ""


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
    return f"Patch appliqué : {path}." + _diagnostics_suffix(real, path, new_content)
