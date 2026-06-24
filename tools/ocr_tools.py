"""OCR — extraction FIDÈLE du texte d'une image ou d'un PDF.

S'appuie sur l'infra vision existante (`core/vision.py`, modèle multimodal de l'endpoint).
- Image → transcription par le modèle vision avec un prompt OCR strict (zéro interprétation).
- PDF « texte » → extraction directe via pypdf (rapide, exact).
- PDF « scanné » (sans couche texte) → rendu des pages en images puis OCR vision, SI une lib de
  rendu est dispo (PyMuPDF). Sinon, message clair (pas d'invention).

Modèle OCR : `OCR_MODEL` si défini (ex. un modèle dédié type glm-ocr), sinon le `VISION_MODEL`
général. Données traitées comme NON FIABLES (on ne suit jamais une instruction trouvée dans une image).
"""
import os

from core import vision

_OCR_PROMPT = (
    "Tu es un moteur OCR. Transcris FIDÈLEMENT et INTÉGRALEMENT tout le texte visible dans cette "
    "image, dans l'ordre de lecture naturel. Ne traduis pas, n'interprète pas, n'ajoute AUCUN "
    "commentaire ni mise en forme inventée. Conserve la ponctuation et les retours à la ligne. "
    "Si une zone est illisible, écris [illisible]. Ne renvoie QUE le texte transcrit."
)

_IMG_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff")


def _ocr_model() -> str:
    return (os.getenv("OCR_MODEL", "") or "").strip() or vision.vision_model()


def _resolve(filename: str):
    try:
        from tools.document_tools import _resolve as _r
        return _r(filename)
    except Exception:
        return None


def ocr_image(filename: str) -> str:
    """Extrait (transcrit) le texte d'une IMAGE uploadée (capture, photo, document scanné).

    filename : nom/chemin de l'image dans workspace/uploads (ex. 'facture.jpg').
    Renvoie le texte brut transcrit (pas d'interprétation). Pour résumer/analyser ensuite,
    utilise le résultat comme contexte.
    """
    path = _resolve(filename)
    if not path:
        return (f"Erreur : image « {filename} » introuvable dans workspace/uploads. "
                "Vérifie le nom ou ré-uploade le fichier.")
    ext = (os.path.splitext(path)[1].lstrip(".") or "png").lower()
    if ext not in _IMG_EXTS:
        return f"Format image non pris en charge pour l'OCR : .{ext} (png/jpg/webp/tiff…)."
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception as e:  # noqa: BLE001
        return f"Erreur de lecture de l'image : {e}"
    txt = vision.analyze_bytes(data, question=_OCR_PROMPT, ext=ext, model=_ocr_model())
    return (txt or "").strip() or "(aucun texte détecté dans l'image)"


def _pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception:
        return ""


def _pdf_ocr_via_render(path: str, max_pages: int = 15) -> str:
    """OCR d'un PDF scanné : rend chaque page en image (PyMuPDF) puis transcrit. None si la lib
    de rendu n'est pas disponible (pas d'invention — l'appelant affichera un message clair)."""
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None
    out = []
    try:
        doc = fitz.open(path)
        for i, page in enumerate(doc):
            if i >= max_pages:
                out.append(f"[… {len(doc) - max_pages} page(s) supplémentaire(s) non traitée(s)]")
                break
            pix = page.get_pixmap(dpi=200)
            png = pix.tobytes("png")
            t = vision.analyze_bytes(png, question=_OCR_PROMPT, ext="png", model=_ocr_model())
            out.append(f"--- Page {i + 1} ---\n{(t or '').strip()}")
    except Exception as e:  # noqa: BLE001
        return f"Erreur de rendu/OCR du PDF : {e}"
    return "\n\n".join(out).strip()


def ocr_document(filename: str) -> str:
    """Extrait le texte d'un DOCUMENT uploadé : image OU PDF.

    - Image → OCR vision.
    - PDF avec couche texte → extraction directe (rapide et exacte).
    - PDF scanné (sans texte) → OCR page par page si une lib de rendu (PyMuPDF) est installée.

    filename : nom/chemin dans workspace/uploads.
    """
    path = _resolve(filename)
    if not path:
        return (f"Erreur : document « {filename} » introuvable dans workspace/uploads.")
    ext = (os.path.splitext(path)[1].lstrip(".") or "").lower()
    if ext in _IMG_EXTS:
        return ocr_image(filename)
    if ext != "pdf":
        return f"Format non pris en charge pour l'OCR : .{ext} (image ou PDF attendu)."

    text = _pdf_text(path)
    if len(text) >= 40:   # couche texte présente → pas besoin d'OCR
        return text
    # PDF probablement scanné → OCR par rendu de pages.
    ocr = _pdf_ocr_via_render(path)
    if ocr is None:
        return ("Ce PDF semble SCANNÉ (aucune couche texte) et l'OCR par image nécessite la "
                "bibliothèque PyMuPDF (`pip install pymupdf`), absente ici. Installe-la côté serveur, "
                "ou uploade les pages en images (png/jpg) puis utilise `ocr_image`.")
    return ocr or "(aucun texte détecté dans le PDF)"
