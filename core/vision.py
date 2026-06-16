"""Vision : fait « voir » une image à Athena via un modèle multimodal de l'endpoint.

Contraintes de l'endpoint (cf. mémoire) : les images doivent être envoyées en BASE64 (data URI),
pas en URL distante (sinon 400). Le modèle vision est configurable (VISION_MODEL, défaut
« custom/chat-gemma ») et distinct du modèle orchestrateur (chat-qwen, texte).
"""
import os
import base64


def vision_model() -> str:
    """Modèle multimodal à utiliser. Configurable ; défaut = chat-gemma (Gemma 4 vision)."""
    return (os.getenv("VISION_MODEL", "") or "").strip() or "custom/chat-gemma"


def is_enabled() -> bool:
    """La vision est disponible dès qu'un modèle vision est configuré (toujours vrai par défaut)."""
    return bool(vision_model())


def _data_uri(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
         "webp": "image/webp", "bmp": "image/bmp"}


def analyze_bytes(image_bytes: bytes, question: str = "", ext: str = "png", model: str = "") -> str:
    """Analyse une image (octets) avec le modèle vision et renvoie la réponse texte.
    `question` = ce qu'on veut savoir (défaut : décrire). Lève en cas d'échec."""
    if not image_bytes:
        return "Erreur : image vide."
    q = (question or "").strip() or "Décris cette image en détail (texte visible, éléments, contexte)."
    mime = _MIME.get((ext or "png").lower().lstrip("."), "image/png")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": q},
        {"type": "image_url", "image_url": {"url": _data_uri(image_bytes, mime)}},
    ]}]
    from core.state import swarm
    mdl = (model or "").strip() or vision_model()
    try:
        resp = swarm._complete(mdl, messages, tools_schema=None)
        return (resp.choices[0].message.content or "").strip() or "(réponse vide du modèle vision)"
    except Exception as e:
        return f"Erreur du modèle vision ({mdl}) : {e}"
