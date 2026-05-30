"""Synthèse vocale (TTS) locale : Piper (recommandé) ou pyttsx3 (repli)."""
import os
import subprocess
import tempfile
import wave


class TTSUnavailable(RuntimeError):
    pass


class TTS:
    def __init__(self, engine="piper", piper_model="", piper_bin="piper"):
        self.engine = engine
        self.piper_model = piper_model
        self.piper_bin = piper_bin
        self._pyttsx = None

    # ------------------------------------------------------------------ Piper
    def _piper_to_wav(self, text: str) -> str:
        if not self.piper_model or not os.path.exists(self.piper_model):
            raise TTSUnavailable(
                "Modèle Piper introuvable. Définissez VOICE_PIPER_MODEL vers un .onnx "
                "(https://github.com/rhasspy/piper)."
            )
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        try:
            subprocess.run(
                [self.piper_bin, "--model", self.piper_model, "--output_file", out],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
        except FileNotFoundError as e:
            raise TTSUnavailable(f"Binaire Piper '{self.piper_bin}' introuvable.") from e
        except subprocess.CalledProcessError as e:
            raise TTSUnavailable(f"Piper a échoué : {e.stderr.decode('utf-8', 'ignore')}") from e
        return out

    # ----------------------------------------------------------------- pyttsx3
    def _ensure_pyttsx(self):
        if self._pyttsx is None:
            try:
                import pyttsx3
            except ImportError as e:
                raise TTSUnavailable("pyttsx3 non installé (`pip install pyttsx3`).") from e
            self._pyttsx = pyttsx3.init()
        return self._pyttsx

    # ------------------------------------------------------------------- API
    def speak(self, text: str):
        """Synthétise puis joue le texte (bloquant)."""
        text = (text or "").strip()
        if not text:
            return
        if self.engine == "pyttsx3":
            engine = self._ensure_pyttsx()
            engine.say(text)
            engine.runAndWait()
            return
        # Piper -> wav -> lecture
        wav_path = self._piper_to_wav(text)
        try:
            self._play_wav(wav_path)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    @staticmethod
    def _play_wav(path: str):
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            raise TTSUnavailable("sounddevice/numpy requis pour la lecture audio.") from e
        with wave.open(path, "rb") as wf:
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16)
        sd.play(data, sr)
        sd.wait()
