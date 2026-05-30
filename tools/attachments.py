"""Extraction du contenu des pièces jointes du chat.

Approche hybride (marche avec tout modèle) : on extrait le TEXTE des fichiers
(texte/code, PDF, CSV/JSON…) pour l'injecter dans le message. Pour les images :
OCR si pytesseract est installé, sinon une note (l'analyse visuelle réelle
nécessite un modèle compatible vision).
"""
import os

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
MAX_CHARS = 12000


def _looks_binary(sample: bytes) -> bool:
    if not sample:
        return False
    nontext = sum(1 for c in sample if c < 9 or (13 < c < 32))
    return (nontext / len(sample)) > 0.1


def extract(path: str, filename: str, max_chars: int = MAX_CHARS) -> dict:
    """Renvoie {kind, text, truncated, note}."""
    ext = os.path.splitext(filename)[1].lower()
    result = {"kind": "fichier", "text": "", "truncated": False, "note": ""}

    # --- Images ---
    if ext in IMAGE_EXTS:
        result["kind"] = "image"
        dims = ""
        try:
            from PIL import Image
            with Image.open(path) as im:
                dims = f"{im.width}x{im.height}"
        except Exception:
            pass
        try:
            import pytesseract
            from PIL import Image
            result["text"] = pytesseract.image_to_string(Image.open(path)).strip()
        except Exception:
            result["text"] = ""
        if not result["text"]:
            result["note"] = (f"Image {dims}. Aucun texte extrait — pour l'analyser "
                              "visuellement, utilise un modèle compatible vision.")
        else:
            result["note"] = f"Image {dims} (texte OCR ci-dessous)."
        result["text"] = result["text"][:max_chars]
        return result

    # --- PDF ---
    if ext == ".pdf":
        result["kind"] = "pdf"
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
            if not text:
                result["note"] = "PDF sans texte extractible (probablement scanné)."
            result["text"] = text
        except Exception as e:
            result["note"] = f"PDF illisible : {e}"
        if len(result["text"]) > max_chars:
            result["text"] = result["text"][:max_chars]
            result["truncated"] = True
        return result

    # --- Texte / code ---
    try:
        with open(path, "rb") as f:
            raw = f.read()
        if _looks_binary(raw[:4096]):
            result["note"] = "Fichier binaire non supporté (texte non extrait)."
            return result
        text = raw.decode("utf-8", errors="ignore")
        result["kind"] = "texte"
        if len(text) > max_chars:
            text = text[:max_chars]
            result["truncated"] = True
        result["text"] = text
    except Exception as e:
        result["note"] = f"Lecture impossible : {e}"
    return result
