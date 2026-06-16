"""Outils VISION pour Athena : analyser une image/capture, et (optionnel) capturer l'écran.

- analyze_image : « lis/décris/analyse cette image » sur un fichier uploadé (workspace/uploads).
  Utilise un modèle multimodal de l'endpoint (chat-gemma) — voir core/vision.py.
- capture_screen : capture l'écran de la MACHINE où tourne Athena et l'analyse. OPTIONNEL et
  GATÉ (COMPUTER_USE=true) car (a) inutile sur un serveur HEADLESS, (b) c'est la 1ʳᵉ brique d'un
  « computer use » — le contrôle souris/clavier viendra séparément, avec confirmation.
"""
import os

from core import vision


def analyze_image(filename: str, question: str = "") -> str:
    """
    Analyse une IMAGE (capture d'écran, photo, schéma, document scanné) réellement fournie/uploadée
    et répond à une question à son sujet (texte visible, contenu, éléments…). Utilise un modèle
    multimodal. NE PAS chercher sur internet : c'est l'image fournie qui compte.

    Args:
        filename (str): Nom/chemin de l'image uploadée (ex: 'capture.png', 'uploads/xxx.jpg').
        question (str): Ce qu'on veut savoir (ex: 'lis le message d'erreur', 'que montre ce graphe ?').
                        Vide = description détaillée.
    Returns:
        str: La réponse du modèle vision.
    """
    # Réutilise le résolveur d'uploads (workspace/uploads, anti-traversée) de document_tools.
    try:
        from tools.document_tools import _resolve
        path = _resolve(filename)
    except Exception:
        path = None
    if not path:
        return (f"Erreur : image « {filename} » introuvable dans workspace/uploads. "
                "Vérifie le nom ou ré-uploade l'image.")
    ext = (os.path.splitext(path)[1].lstrip(".") or "png").lower()
    if ext not in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
        return f"Format non pris en charge pour la vision : .{ext} (utilise png/jpg/webp…)."
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception as e:
        return f"Erreur de lecture de l'image : {e}"
    return vision.analyze_bytes(data, question=question, ext=ext)


def _grab_screen_png() -> bytes:
    """Capture l'écran → octets PNG. Essaie mss puis Pillow ImageGrab. Lève si indisponible."""
    try:
        import io
        import mss
        import mss.tools
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])  # tous les écrans
            return mss.tools.to_png(shot.rgb, shot.size)
    except Exception:
        pass
    from PIL import ImageGrab
    import io
    im = ImageGrab.grab()
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def capture_screen(question: str = "") -> str:
    """
    Capture l'écran de la machine où tourne Athena et l'analyse (1ʳᵉ brique « computer use »).
    OPTIONNEL : nécessite COMPUTER_USE=true ET une session graphique (inutile sur un serveur
    headless). Le contrôle (clic/clavier) n'est PAS inclus ici.

    Args:
        question (str): Ce qu'on veut savoir sur l'écran (ex: 'que vois-tu ?', 'lis l'erreur').
    Returns:
        str: L'analyse de la capture.
    """
    if os.getenv("COMPUTER_USE", "false").lower() not in ("true", "1", "yes"):
        return ("Capture d'écran désactivée. Active COMPUTER_USE=true (et lance Athena sur une "
                "machine avec session graphique — inutile sur un serveur headless).")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return ("Aucune session graphique détectée (DISPLAY/WAYLAND_DISPLAY absents) : Athena tourne "
                "probablement en headless → pas d'écran à capturer.")
    try:
        png = _grab_screen_png()
    except Exception as e:
        return (f"Capture impossible : {e}. Installe une lib de capture : "
                "`pip install mss` (ou Pillow).")
    return vision.analyze_bytes(png, question=question, ext="png")
