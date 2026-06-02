"""Couche d'émotion vocale : le LLM peut préfixer/insérer une balise d'émotion
(ex. « [emotion: enjoué] », « (ton: calme) ») ; on l'extrait, on la NORMALISE et on
la RETIRE du texte. Le texte propre est synthétisé ; l'émotion est passée au moteur
TTS expressif (le cas échéant). Indépendant du moteur : un TTS monocorde ignore juste
l'émotion, mais la balise ne « fuite » jamais dans le texte affiché ni prononcé.
"""
import re

# Émotions normalisées reconnues + synonymes FR/EN -> clé canonique.
_CANON = {
    "neutral": "neutral", "neutre": "neutral",
    "cheerful": "cheerful", "enjoué": "cheerful", "enjoue": "cheerful", "joyeux": "cheerful", "happy": "cheerful", "content": "cheerful",
    "excited": "excited", "excité": "excited", "excite": "excited", "enthousiaste": "excited",
    "sad": "sad", "triste": "sad",
    "calm": "calm", "calme": "calm", "posé": "calm", "pose": "calm",
    "serious": "serious", "sérieux": "serious", "serieux": "serious",
    "empathetic": "empathetic", "empathique": "empathetic", "doux": "empathetic", "bienveillant": "empathetic",
    "angry": "angry", "fâché": "angry", "fache": "angry", "colère": "angry", "colere": "angry",
    "whisper": "whisper", "chuchoté": "whisper", "chuchote": "whisper", "murmure": "whisper",
}

# Balises : [emotion: X] | (ton: X) | (émotion: X) | [ton:X] (insensible à la casse).
_TAG_RE = re.compile(
    r"[\[(]\s*(?:emotion|émotion|emotion|ton|tone|style)\s*[:=]\s*([^\])]+?)\s*[\])]",
    re.IGNORECASE,
)


def normalize_emotion(word: str):
    if not word:
        return None
    return _CANON.get(word.strip().lower())


def split_emotion(text: str, default: str = "neutral"):
    """Renvoie (emotion_canonique, texte_nettoyé). Retire TOUTES les balises trouvées ;
    la première émotion reconnue gagne. Si aucune, renvoie (default, texte inchangé)."""
    if not text:
        return default, text or ""
    found = None
    for m in _TAG_RE.finditer(text):
        canon = normalize_emotion(m.group(1))
        if canon and found is None:
            found = canon
    clean = _TAG_RE.sub("", text)
    # Nettoyage des espaces/doubles espaces laissés par le retrait des balises.
    clean = re.sub(r"[ \t]{2,}", " ", clean).strip()
    return (found or default), clean


def strip_emotion(text: str) -> str:
    """Retire les balises d'émotion d'un texte (pour l'affichage), sans renvoyer l'émotion."""
    return split_emotion(text)[1]
