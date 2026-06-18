"""Transcription audio (STT) PARTAGÉE et MISE EN CACHE — un seul modèle en mémoire.

Unifie les chemins de transcription hors-satellite (dictée du chat, réunions) qui chargeaient
auparavant le modèle Whisper À CHAQUE requête (~140 Mo, +5-10 s de latence) et en double
(un cache par module). Ici : un SEUL modèle, chargé une fois (thread-safe, double-checked),
réutilisé partout.

Moteur : on PRÉFÈRE `faster-whisper` (CTranslate2, INT8 — plus rapide et plus léger, déjà le
moteur des satellites), et on RETOMBE sur `openai-whisper` si faster-whisper n'est pas installé.
Ainsi on ne casse aucune install existante. Réglages via env (partagés avec les satellites) :
VOICE_STT_MODEL (base), VOICE_STT_DEVICE (cpu), VOICE_STT_COMPUTE (int8), VOICE_STT_LANGUAGE (auto).
"""
import os
import threading

_model = None
_backend = None          # "faster" | "openai"
_lock = threading.Lock()


class TranscriptionUnavailable(RuntimeError):
    pass


def is_available() -> bool:
    """Vrai si au moins un moteur de transcription est installé."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        try:
            import whisper  # noqa: F401  (openai-whisper)
            return True
        except Exception:
            return False


def _get_model():
    """Charge (une seule fois) et renvoie (modèle, backend). Thread-safe."""
    global _model, _backend
    if _model is not None:
        return _model, _backend
    with _lock:
        if _model is None:
            name = os.getenv("VOICE_STT_MODEL", "base")
            # 1) faster-whisper (préféré).
            try:
                from faster_whisper import WhisperModel
                _model = WhisperModel(
                    name,
                    device=os.getenv("VOICE_STT_DEVICE", "cpu"),
                    compute_type=os.getenv("VOICE_STT_COMPUTE", "int8"),
                )
                _backend = "faster"
                print(f"🎙️ [STT] modèle faster-whisper '{name}' chargé (cache, INT8).")
            except Exception:
                # 2) repli openai-whisper.
                try:
                    import whisper
                    _model = whisper.load_model(name)
                    _backend = "openai"
                    print(f"🎙️ [STT] modèle openai-whisper '{name}' chargé (cache).")
                except Exception as e:
                    raise TranscriptionUnavailable(
                        "Aucun moteur STT installé (faster-whisper ou openai-whisper). "
                        "`pip install faster-whisper`."
                    ) from e
    return _model, _backend


def transcribe_file(path: str, language: str = None) -> str:
    """Transcrit un fichier audio en TEXTE (langue auto si None). Le modèle est mis en cache
    au 1er appel (lent une fois), les suivants sont quasi instantanés."""
    model, backend = _get_model()
    lang = language or (os.getenv("VOICE_STT_LANGUAGE", "").strip() or None)
    if backend == "faster":
        segments, _info = model.transcribe(path, language=lang, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()
    # openai-whisper
    kwargs = {"language": lang} if lang else {}
    result = model.transcribe(path, **kwargs)
    return (result.get("text") or "").strip()
