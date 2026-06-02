"""Analyse de document LONG (roman, rapport…) réellement UPLOADÉ, par map-reduce.

Lit le fichier complet (PDF via pypdf, ou texte), le découpe en passages, analyse
chaque passage avec le LLM (map), puis synthétise (reduce) selon l'instruction.
N'utilise JAMAIS le web : l'analyse porte sur le CONTENU FOURNI, pas sur des résumés
trouvés en ligne. Borné par DOC_MAX_CHUNKS (échantillonnage régulier si trop long).
"""
import os
import glob

CHUNK_CHARS = 6000


def _resolve(filename: str):
    """Trouve le fichier dans workspace/uploads ou workspace, par chemin ou par nom."""
    ws = None
    try:
        from core.state import get_workspace_dir
        ws = get_workspace_dir()
    except Exception:
        ws = os.getenv("ACTIVE_WORKSPACE_DIR", "").strip() or os.path.join(os.getcwd(), "workspace")
    name = (filename or "").strip().strip('"').strip("'")
    cands = []
    if name:
        cands.append(os.path.join(ws, name))
        cands.append(os.path.join(ws, "uploads", os.path.basename(name)))
        # recherche par sous-chaîne du basename (les uploads ont un préfixe aléatoire)
        base = os.path.basename(name).lower()
        for p in glob.glob(os.path.join(ws, "uploads", "*")):
            if base in os.path.basename(p).lower() or os.path.basename(p).lower().endswith(base):
                cands.append(p)
    for c in cands:
        if c and os.path.isfile(c):
            real = os.path.realpath(c)
            if real.startswith(os.path.realpath(ws)):  # anti-traversée
                return real
    return None


def _extract_full_text(path: str) -> str:
    if path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            return "\n".join((pg.extract_text() or "") for pg in reader.pages)
        except Exception as e:
            return f"__ERR__ Lecture PDF impossible : {e}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"__ERR__ Lecture impossible : {e}"


def _chunks(text: str, size: int = CHUNK_CHARS):
    paras, cur, out = text.split("\n"), "", []
    for p in paras:
        if len(cur) + len(p) + 1 > size and cur:
            out.append(cur); cur = ""
        cur += p + "\n"
    if cur.strip():
        out.append(cur)
    return out


def analyze_document(filename: str, instruction: str = "") -> str:
    """
    Analyse un document LONG réellement fourni/uploadé (roman, rapport, PDF…) en le
    lisant INTÉGRALEMENT (découpage + synthèse). À utiliser pour « relis/critique/résume
    ce roman/document » : NE PAS chercher sur internet, c'est le contenu fourni qui compte.
    filename: nom ou chemin du fichier (ex: 'Les_larmes.pdf' ou 'uploads/xxx_Les_larmes.pdf').
    instruction: ce qu'il faut faire (ex: 'critique littéraire détaillée', 'résumé par chapitre').
    """
    path = _resolve(filename)
    if not path:
        return (f"Erreur : fichier « {filename} » introuvable dans workspace/uploads. "
                "Vérifie le nom, ou ré-uploade le document.")
    text = _extract_full_text(path)
    if text.startswith("__ERR__"):
        return text.replace("__ERR__ ", "Erreur : ")
    text = text.strip()
    if not text:
        return "Erreur : aucun texte extractible de ce document (PDF scanné/image ?)."

    chunks = _chunks(text)
    total = len(chunks)
    cap = int(os.getenv("DOC_MAX_CHUNKS", "60") or 60)
    sampled_note = ""
    if total > cap:
        step = total / cap
        chunks = [chunks[int(i * step)] for i in range(cap)]
        sampled_note = f" (document très long : {total} passages → {cap} échantillonnés régulièrement)"

    instruction = (instruction or "").strip() or "Fais une critique littéraire détaillée et constructive."

    import server
    swarm = getattr(server, "swarm", None)
    if swarm is None:
        return "Erreur : moteur LLM indisponible."
    orch = getattr(swarm, "orchestrator_name", None)
    model = (swarm.agents.get(orch).model if orch and swarm.agents.get(orch)
             else (next(iter(swarm.agents.values())).model if swarm.agents else "gpt-4o"))

    # MAP : notes par passage.
    notes = []
    for i, ch in enumerate(chunks, 1):
        try:
            resp = swarm._complete(model, [
                {"role": "system", "content": (
                    "Tu analyses un PASSAGE d'un document long. Objectif global : " + instruction +
                    "\nRelève SEULEMENT, en 2-4 puces, les éléments utiles à cet objectif pour ce passage "
                    "(intrigue, style, personnages, incohérences, fautes notables…). Sois bref et factuel.")},
                {"role": "user", "content": f"[Passage {i}/{len(chunks)}]\n{ch[:CHUNK_CHARS]}"},
            ], tools_schema=None, allow_continuation=False, allow_fallback=True)
            notes.append(f"— Passage {i} —\n" + (resp.choices[0].message.content or "").strip())
        except Exception as e:
            notes.append(f"— Passage {i} — (erreur d'analyse : {e})")

    # REDUCE : synthèse globale.
    joined = "\n\n".join(notes)[:14000]
    try:
        resp = swarm._complete(model, [
            {"role": "system", "content": (
                "Tu es un critique littéraire. À partir des notes d'analyse de TOUS les passages "
                "d'un document, produis une SYNTHÈSE structurée répondant à l'objectif : " + instruction +
                "\nStructure : points forts, axes d'amélioration, et une appréciation globale. "
                "Appuie-toi UNIQUEMENT sur les notes (donc sur le contenu réel du document).")},
            {"role": "user", "content": f"Notes des {len(chunks)} passages :\n\n{joined}"},
        ], tools_schema=None, allow_continuation=True, allow_fallback=True)
        synthesis = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"Erreur lors de la synthèse : {e}"

    header = f"[Analyse du document « {os.path.basename(path)} » — {total} passages lus{sampled_note}]\n\n"
    return header + synthesis
