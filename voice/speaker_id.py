"""Reconnaissance du locuteur (qui parle) par empreinte vocale.

Enrôlement : on calcule une empreinte (embedding) à partir d'un échantillon .wav
par personne (voice/speakers/<nom>.npy). À chaque énoncé, on compare l'empreinte
au plus proche profil (similarité cosinus) ; au-dessus du seuil, on identifie la
personne — ce qui permet une session/mémoire par membre du foyer.

Dépendance optionnelle : resemblyzer (+ numpy). Import paresseux : sans elle, on
renvoie simplement « inconnu » (None) sans planter.

⚠️ Non testé sur la machine de dev (pas d'audio / resemblyzer non installé).
"""
import glob
import os

SPEAKERS_DIR = os.getenv("VOICE_SPEAKERS_DIR", os.path.join(os.path.dirname(__file__), "speakers"))
THRESHOLD = float(os.getenv("VOICE_SPEAKER_THRESHOLD", "0.70"))

_encoder = None


class SpeakerIDUnavailable(RuntimeError):
    pass


def _encoder_instance():
    global _encoder
    if _encoder is None:
        try:
            from resemblyzer import VoiceEncoder
        except ImportError as e:
            raise SpeakerIDUnavailable(
                "resemblyzer non installé (pip install resemblyzer)."
            ) from e
        _encoder = VoiceEncoder(verbose=False)
    return _encoder


def _embed(audio, sr=16000):
    from resemblyzer import preprocess_wav
    if isinstance(audio, str):
        wav = preprocess_wav(audio)
    else:
        import numpy as np
        wav = preprocess_wav(np.asarray(audio, dtype="float32"), source_sr=sr)
    return _encoder_instance().embed_utterance(wav)


def enroll(name: str, wav_path: str) -> str:
    """Enrôle un locuteur depuis un échantillon .wav."""
    import numpy as np
    os.makedirs(SPEAKERS_DIR, exist_ok=True)
    emb = _embed(wav_path)
    np.save(os.path.join(SPEAKERS_DIR, f"{name}.npy"), emb)
    return f"Locuteur « {name} » enrôlé ({os.path.join(SPEAKERS_DIR, name + '.npy')})."


def list_speakers() -> list:
    return [os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(SPEAKERS_DIR, "*.npy"))]


def _profiles():
    import numpy as np
    profs = {}
    for f in glob.glob(os.path.join(SPEAKERS_DIR, "*.npy")):
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            profs[name] = np.load(f)
        except Exception:
            pass
    return profs


def identify(audio, sr=16000):
    """Renvoie (nom, score) du locuteur le plus proche, ou (None, score) si < seuil
    ou si la reconnaissance est indisponible/non enrôlée."""
    try:
        import numpy as np
        profs = _profiles()
        if not profs:
            return None, 0.0
        emb = _embed(audio, sr)
        best, best_s = None, -1.0
        for name, ref in profs.items():
            s = float(np.dot(emb, ref) / (np.linalg.norm(emb) * np.linalg.norm(ref) + 1e-9))
            if s > best_s:
                best, best_s = name, s
        return (best, best_s) if best_s >= THRESHOLD else (None, max(best_s, 0.0))
    except SpeakerIDUnavailable:
        return None, 0.0
    except Exception:
        return None, 0.0
