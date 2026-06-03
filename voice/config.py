"""Configuration du pipeline vocal (pilotée par variables d'environnement)."""
import os


def voice_config() -> dict:
    return {
        # Serveur Jarvis à interroger (réutilise l'API de streaming + sessions/permissions).
        "server_url": os.getenv("VOICE_SERVER_URL", "http://127.0.0.1:8000").rstrip("/"),
        "client_id": os.getenv("VOICE_CLIENT_ID", "voice"),
        "auth_token": os.getenv("VOICE_AUTH_TOKEN", ""),  # si ADMIN_PASSWORD activé

        # Capture audio
        "sample_rate": int(os.getenv("VOICE_SAMPLE_RATE", "16000")),
        "block_ms": int(os.getenv("VOICE_BLOCK_MS", "30")),
        "silence_rms": float(os.getenv("VOICE_SILENCE_RMS", "0.012")),
        "silence_ms": int(os.getenv("VOICE_SILENCE_MS", "500")),
        "max_record_s": float(os.getenv("VOICE_MAX_RECORD_S", "15")),

        # STT (faster-whisper)
        "stt_model": os.getenv("VOICE_STT_MODEL", "base"),
        "stt_device": os.getenv("VOICE_STT_DEVICE", "cpu"),
        "stt_compute": os.getenv("VOICE_STT_COMPUTE", "int8"),
        "stt_language": os.getenv("VOICE_STT_LANGUAGE", "fr"),

        # TTS : "http" (Kokoro/OpenAI), "piper" (local), ou "pyttsx3" (repli système)
        "tts_engine": os.getenv("VOICE_TTS_ENGINE", "http"),
        "piper_model": os.getenv("VOICE_PIPER_MODEL", ""),   # chemin .onnx
        "piper_bin": os.getenv("VOICE_PIPER_BIN", "piper"),

        # Wake word : "stt" (mot custom ex. Athena, par transcription), "openwakeword",
        # "porcupine", ou "none" (push-to-talk Entrée)
        "wake_engine": os.getenv("VOICE_WAKE_ENGINE", "openwakeword"),
        "wake_word": os.getenv("VOICE_WAKE_WORD", "hey jarvis"),
        "porcupine_key": os.getenv("VOICE_PORCUPINE_KEY", ""),
    }
