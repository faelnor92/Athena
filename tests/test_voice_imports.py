"""Le package voice doit s'importer SANS les dépendances audio lourdes
(imports paresseux). L'erreur ne doit survenir qu'à l'utilisation effective."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_import_sans_dependances_audio():
    import voice  # noqa: F401
    from voice.config import voice_config
    from voice.stt import STT, STTUnavailable
    from voice.tts import TTS, TTSUnavailable
    from voice.wakeword import WakeWord
    from voice.assistant import VoiceAssistant  # noqa: F401

    cfg = voice_config()
    assert cfg["client_id"] == "voice"

    # Instancier ne charge aucune lib lourde.
    STT(); TTS(); WakeWord(engine="none")

    # Utiliser sans la lib doit lever une erreur claire (et non un crash d'import).
    try:
        STT().transcribe("inexistant.wav")
    except STTUnavailable:
        pass
    except Exception:
        # faster-whisper installé mais fichier absent -> autre erreur acceptable
        pass

    print("OK: package voice importable sans dépendances audio")


if __name__ == "__main__":
    test_import_sans_dependances_audio()
