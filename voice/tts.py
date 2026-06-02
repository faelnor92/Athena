"""Synthèse vocale (TTS) : Piper, pyttsx3, ou un moteur EXPRESSIF via HTTP.

Le moteur "http" permet de brancher n'importe quel serveur TTS expressif local
(XTTS, Chatterbox, Qwen3-TTS, OpenAI-compatible…) qui renvoie un WAV, et de lui passer
une ÉMOTION extraite du texte (cf. voice/emotion.py). Le pipeline texte multi-agent
reste inchangé : on ne remplace que la voix.
"""
import os
import subprocess
import tempfile
import wave

from voice.emotion import split_emotion


class TTSUnavailable(RuntimeError):
    pass


class TTS:
    def __init__(self, engine="piper", piper_model="", piper_bin="piper"):
        self.engine = engine
        self.piper_model = piper_model
        self.piper_bin = piper_bin
        self._pyttsx = None

    # --------------------------------------------------- TTS expressif via HTTP
    def _http_to_wav(self, text: str, emotion: str = "neutral") -> str:
        """Appelle un serveur TTS expressif et écrit le WAV renvoyé.
        Config : VOICE_TTS_HTTP_URL (POST), VOICE_TTS_VOICE, VOICE_TTS_FORMAT.
        Corps JSON générique : {text, voice, emotion, format}. Compatible aussi avec
        une API style OpenAI (/v1/audio/speech : {model, input, voice})."""
        import requests
        url = os.getenv("VOICE_TTS_HTTP_URL", "").strip()
        if not url:
            raise TTSUnavailable("VOICE_TTS_HTTP_URL non défini pour le moteur TTS 'http'.")
        voice = os.getenv("VOICE_TTS_VOICE", "").strip()
        fmt = os.getenv("VOICE_TTS_FORMAT", "wav").strip() or "wav"
        if "/audio/speech" in url:  # forme OpenAI-compatible
            payload = {"model": os.getenv("VOICE_TTS_MODEL", "tts-1"), "input": text,
                       "voice": voice or "alloy", "response_format": fmt}
        else:  # forme générique
            payload = {"text": text, "voice": voice, "emotion": emotion, "format": fmt}
        headers = {"Content-Type": "application/json"}
        key = os.getenv("VOICE_TTS_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            r = requests.post(url, json=payload, headers=headers,
                              timeout=int(os.getenv("VOICE_TTS_TIMEOUT", "30")))
        except Exception as e:
            raise TTSUnavailable(f"Serveur TTS HTTP injoignable : {e}") from e
        if r.status_code != 200:
            raise TTSUnavailable(f"Serveur TTS HTTP : code {r.status_code} ({r.text[:160]}).")
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        with open(out, "wb") as f:
            f.write(r.content)
        return out

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
        emotion, text = split_emotion(text or "")
        text = text.strip()
        if not text:
            return
        if self.engine == "pyttsx3":
            engine = self._ensure_pyttsx()
            self._apply_pyttsx_emotion(engine, emotion)
            engine.say(text)
            engine.runAndWait()
            return
        if self.engine == "http":
            wav_path = self._http_to_wav(text, emotion)
        else:
            wav_path = self._piper_to_wav(text)
        try:
            self._play_wav(wav_path, stop_event)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    @staticmethod
    def _apply_pyttsx_emotion(engine, emotion):
        """Approximation d'émotion pour pyttsx3 (monocorde) via débit/volume."""
        try:
            base = engine.getProperty("rate") or 200
            tuning = {
                "excited": (1.18, 1.0), "cheerful": (1.08, 1.0), "angry": (1.12, 1.0),
                "sad": (0.85, 0.85), "calm": (0.9, 0.9), "empathetic": (0.92, 0.95),
                "whisper": (0.95, 0.5), "serious": (0.95, 1.0), "neutral": (1.0, 1.0),
            }.get(emotion, (1.0, 1.0))
            engine.setProperty("rate", int(base * tuning[0]))
            engine.setProperty("volume", tuning[1])
        except Exception:
            pass

    def synth_wav_bytes(self, text: str) -> bytes:
        """Synthétise et renvoie les octets WAV (pour streaming vers un satellite)."""
        emotion, text = split_emotion(text or "")
        text = text.strip()
        if not text:
            return b""
        if self.engine == "pyttsx3":
            engine = self._ensure_pyttsx()
            self._apply_pyttsx_emotion(engine, emotion)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
            try:
                engine.save_to_file(text, tmp)
                engine.runAndWait()
                with open(tmp, "rb") as f:
                    return f.read()
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        if self.engine == "http":
            wav_path = self._http_to_wav(text, emotion)
        else:
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
