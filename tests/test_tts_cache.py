"""Cache TTS par segment : hash(texte+voix+params) → WAV. Régénérer un livre audio
après correction d'un chapitre ne resynthétise que les segments modifiés."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tts_segment_cache(monkeypatch):
    monkeypatch.setenv("TTS_CACHE_DIR", tempfile.mkdtemp())
    monkeypatch.delenv("VOICE_TTS_VOICE", raising=False)
    from voice.tts import TTS

    t = TTS(engine="http")
    calls = {"n": 0}

    def fake_uncached(text, emotion):
        calls["n"] += 1
        return b"RIFF" + text.encode()
    t._synth_wav_bytes_uncached = fake_uncached

    a = t.synth_wav_bytes("Bonjour chapitre un.")
    b = t.synth_wav_bytes("Bonjour chapitre un.")
    c = t.synth_wav_bytes("Chapitre deux différent.")
    assert a == b and calls["n"] == 2, "segment identique → servi depuis le cache"
    assert c != a
    # Changement de voix → clé différente → resynthèse (pas de faux hit).
    monkeypatch.setenv("VOICE_TTS_VOICE", "autre-voix")
    t.synth_wav_bytes("Bonjour chapitre un.")
    assert calls["n"] == 3
    print("OK: cache TTS par segment (hit identique, miss si texte/voix change)")


def test_tts_cache_desactivable(monkeypatch):
    monkeypatch.setenv("TTS_CACHE_DIR", "")
    from voice.tts import TTS
    t = TTS(engine="http")
    calls = {"n": 0}

    def fake_uncached(text, emotion):
        calls["n"] += 1
        return b"RIFF"
    t._synth_wav_bytes_uncached = fake_uncached
    t.synth_wav_bytes("x")
    t.synth_wav_bytes("x")
    assert calls["n"] == 2, "TTS_CACHE_DIR vide → cache désactivé"
    print("OK: TTS_CACHE_DIR='' désactive le cache")


if __name__ == "__main__":
    class _MP:
        def setenv(self, k, v): os.environ[k] = v
        def delenv(self, k, raising=True): os.environ.pop(k, None)
    test_tts_segment_cache(_MP())
    test_tts_cache_desactivable(_MP())
    print("\nTous les tests du cache TTS passent.")
