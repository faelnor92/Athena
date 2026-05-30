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
    def speak(self, text: str, stop_event=None):
        """Synthétise puis joue le texte. Si stop_event (threading.Event) est
        fourni et déclenché pendant la lecture (Piper), celle-ci est coupée
        (barge-in). pyttsx3 ne supporte pas l'interruption."""
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
            self._play_wav(wav_path, stop_event)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def synth_wav_bytes(self, text: str) -> bytes:
        """Synthétise et renvoie les octets WAV (pour streaming vers un satellite)."""
        text = (text or "").strip()
        if not text:
            return b""
        if self.engine == "pyttsx3":
            engine = self._ensure_pyttsx()
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            try:
                engine.save_to_file(text, tmp)
                engine.runAndWait()
                with open(tmp, "rb") as f:
                    return f.read()
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        wav_path = self._piper_to_wav(text)
        try:
            with open(wav_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    @staticmethod
    def wav_to_pcm16(wav_bytes: bytes, target_sr: int = 16000):
        """Convertit des octets WAV en PCM 16-bit mono au sample rate cible.
        Renvoie (pcm_bytes, sample_rate). Resample naïf si numpy dispo."""
        import wave as _wave
        import io as _io
        with _wave.open(_io.BytesIO(wav_bytes), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
        try:
            import numpy as np
            dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
            data = np.frombuffer(frames, dtype=dtype).astype(np.float32)
            if ch > 1:
                data = data.reshape(-1, ch).mean(axis=1)
            if sw != 2:
                data = data / (2 ** (8 * sw - 1)) * 32767.0
            if sr != target_sr and len(data) > 1:
                n = int(len(data) * target_sr / sr)
                xp = np.linspace(0, 1, len(data))
                data = np.interp(np.linspace(0, 1, n), xp, data)
                sr = target_sr
            return np.clip(data, -32768, 32767).astype(np.int16).tobytes(), sr
        except ImportError:
            return frames, sr

    @staticmethod
    def _play_wav(path: str, stop_event=None):
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            raise TTSUnavailable("sounddevice/numpy requis pour la lecture audio.") from e
        import time
        with wave.open(path, "rb") as wf:
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16)
        sd.play(data, sr)
        if stop_event is None:
            sd.wait()
            return
        # Lecture interruptible : on coupe dès que stop_event est déclenché.
        while True:
            stream = sd.get_stream()
            if stream is None or not stream.active:
                break
            if stop_event.is_set():
                sd.stop()
                break
            time.sleep(0.05)
