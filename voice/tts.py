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

    # Émotion → VITESSE (seul levier expressif de Kokoro via l'API OpenAI : pas de pitch/volume).
    # Multiplicateurs appliqués sur VOICE_TTS_SPEED (défaut 1.0). Bornés à [0.5, 2.0] par Kokoro.
    _EMOTION_SPEED = {
        "neutral": 1.0, "cheerful": 1.08, "excited": 1.18, "sad": 0.85, "calm": 0.9,
        "serious": 0.96, "empathetic": 0.92, "angry": 1.12, "whisper": 0.9,
    }

    @classmethod
    def _emotion_speed(cls, emotion: str) -> float:
        base = float(os.getenv("VOICE_TTS_SPEED", "1.0") or 1.0)
        mult = cls._EMOTION_SPEED.get((emotion or "neutral"), 1.0)
        return max(0.5, min(2.0, round(base * mult, 3)))

    # Émotion → GAIN (volume), 2ᵉ levier expressif applicable sur CPU (numpy seul). On REBAISSE
    # surtout les émotions douces (chuchoté, triste, calme) → pas de saturation. Les énergiques
    # gardent ~1.0 (+ la vitesse fait l'effet). Donne une vraie nuance douceur/intensité.
    _EMOTION_GAIN = {
        "neutral": 1.0, "cheerful": 1.0, "excited": 1.0, "serious": 1.0, "angry": 1.0,
        "empathetic": 0.92, "calm": 0.88, "sad": 0.82, "whisper": 0.55,
    }

    @classmethod
    def _emotion_gain(cls, emotion: str) -> float:
        return cls._EMOTION_GAIN.get((emotion or "neutral"), 1.0)

    @staticmethod
    def _apply_gain_wav(wav_bytes: bytes, gain: float) -> bytes:
        """Applique un GAIN de volume à un WAV (numpy uniquement). gain≈1.0 → no-op. Sans clip
        car on ne fait que réduire (gain ≤ 1) ; on clippe quand même par sécurité."""
        if not wav_bytes or abs(gain - 1.0) < 0.02:
            return wav_bytes
        try:
            import io as _io
            import wave as _wave
            import numpy as np
            with _wave.open(_io.BytesIO(wav_bytes), "rb") as wf:
                params = wf.getparams()
                frames = wf.readframes(wf.getnframes())
            if params.sampwidth != 2:
                return wav_bytes  # on ne traite que du PCM 16-bit
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) * gain
            data = np.clip(data, -32768, 32767).astype(np.int16)
            out = _io.BytesIO()
            with _wave.open(out, "wb") as ww:
                ww.setparams(params)
                ww.writeframes(data.tobytes())
            return out.getvalue()
        except Exception:
            return wav_bytes

    # --------------------------------------------------- TTS expressif via HTTP
    def _get_http_payload(self, text: str, emotion: str):
        url = os.getenv("VOICE_TTS_HTTP_URL", "").strip()
        if not url:
            raise TTSUnavailable("VOICE_TTS_HTTP_URL non défini.")
        voice = os.getenv("VOICE_TTS_VOICE", "").strip()
        fmt = os.getenv("VOICE_TTS_FORMAT", "wav").strip() or "wav"
        speed = self._emotion_speed(emotion)
        if "/audio/speech" in url:
            # OpenAI-compatible (Kokoro-FastAPI) : pas de champ « emotion », on module la VITESSE.
            payload = {"model": os.getenv("VOICE_TTS_MODEL", "tts-1"), "input": text,
                       "voice": voice or "alloy", "response_format": fmt, "speed": speed}
        else:
            # Serveur expressif générique : on passe l'émotion ET la vitesse.
            payload = {"text": text, "voice": voice, "emotion": emotion, "format": fmt, "speed": speed}
        headers = {"Content-Type": "application/json"}
        key = os.getenv("VOICE_TTS_API_KEY", "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return url, payload, headers

    def _open_stream(self, emotion: str, text: str):
        """Ouvre la réponse HTTP en streaming. Lève TTSUnavailable si injoignable."""
        import requests
        url, payload, headers = self._get_http_payload(text, emotion)
        try:
            r = requests.post(url, json=payload, headers=headers, stream=True,
                              timeout=int(os.getenv("VOICE_TTS_TIMEOUT", "30")))
            r.raise_for_status()
        except Exception as e:
            raise TTSUnavailable(f"Serveur TTS HTTP injoignable : {e}") from e
        return r

    @staticmethod
    def _iter_pcm(r):
        """Itère les octets PCM 16-bit d'une réponse TTS en streaming.

        Robuste : si c'est un WAV, on localise le sous-chunk `data` (certains
        serveurs insèrent LIST/fact avant les échantillons, donc l'offset n'est
        pas toujours 44) et on en extrait le sample rate ; sinon on traite le flux
        comme du PCM brut 24 kHz. Yield (sample_rate, pcm_bytes), sample_rate
        constant sur tout le flux ; le 1ᵉʳ yield n'arrive qu'une fois l'en-tête lu."""
        import struct
        sample_rate = 24000  # défaut (Kokoro, OpenAI, PCM brut)
        head = b""
        started = False
        carry = b""  # octet impair reporté d'un chunk au suivant (alignement int16)
        for chunk in r.iter_content(chunk_size=4096):
            if not chunk:
                continue
            if not started:
                head += chunk
                if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
                    idx = head.find(b"data")
                    if idx == -1 or len(head) < idx + 8:
                        continue  # en-tête pas encore complet
                    sample_rate = struct.unpack("<I", head[24:28])[0]
                    chunk = head[idx + 8:]
                elif len(head) >= 44:
                    chunk = head  # pas du WAV → PCM brut
                else:
                    continue
                started = True
            chunk = carry + chunk
            if len(chunk) % 2:
                chunk, carry = chunk[:-1], chunk[-1:]  # garde l'octet impair pour la suite
            else:
                carry = b""
            if chunk:
                yield sample_rate, chunk
        if carry:  # dernier octet orphelin : on le complète pour ne rien perdre
            yield sample_rate, carry + b"\x00"

    def _http_play_stream(self, text: str, emotion: str, stop_event=None):
        """Streaming S2S ultra-rapide depuis le serveur HTTP vers les haut-parleurs."""
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            raise TTSUnavailable("sounddevice/numpy requis pour la lecture audio streaming.") from e

        r = self._open_stream(emotion, text)
        gain = self._emotion_gain(emotion)
        stream = None
        try:
            for sample_rate, chunk in self._iter_pcm(r):
                if stop_event and stop_event.is_set():
                    break
                if stream is None:
                    # latency='low' : démarre la sortie au plus tôt (S2S réactif).
                    stream = sd.OutputStream(samplerate=sample_rate, channels=1,
                                             dtype='int16', latency='low')
                    stream.start()
                buf = np.frombuffer(chunk, dtype=np.int16)
                if abs(gain - 1.0) >= 0.02:
                    buf = np.clip(buf.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
                stream.write(buf)
        finally:
            if stream is not None:
                # Barge-in : abort() coupe immédiatement (stop() viderait le buffer).
                if stop_event and stop_event.is_set():
                    stream.abort()
                else:
                    stream.stop()
                stream.close()
            r.close()

    def _http_to_wav(self, text: str, emotion: str = "neutral") -> str:
        """Appelle un serveur TTS expressif et écrit le WAV renvoyé (non-streamé)."""
        import requests
        url, payload, headers = self._get_http_payload(text, emotion)
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
            self._http_play_stream(text, emotion, stop_event)
            return
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
                data = f.read()
            # Nuance d'intensité par émotion (volume) en plus de la vitesse.
            return self._apply_gain_wav(data, self._emotion_gain(emotion))
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def synth_stream(self, text: str, target_sr: int = 16000):
        """Générateur : synthétise et stream l'audio PCM 16-bit au sample rate cible (idéal pour ESP32)."""
        emotion, text = split_emotion(text or "")
        text = text.strip()
        if not text:
            return
        
        if self.engine != "http":
            # Fallback pour pyttsx3 / piper : on génère tout et on yield en une fois
            wav = self.synth_wav_bytes(text)
            pcm, _sr = self.wav_to_pcm16(wav, target_sr)
            yield pcm
            return

        # Moteur HTTP : Streaming
        try:
            import numpy as np
        except ImportError as e:
            raise TTSUnavailable("numpy requis pour le streaming (resampling).") from e

        r = self._open_stream(emotion, text)
        try:
            for source_sr, chunk in self._iter_pcm(r):
                data = np.frombuffer(chunk, dtype=np.int16)
                # Resampling à la volée si nécessaire
                if source_sr != target_sr and len(data) > 1:
                    n = int(len(data) * target_sr / source_sr)
                    xp = np.linspace(0, 1, len(data))
                    data = np.interp(np.linspace(0, 1, n), xp, data).astype(np.float32)
                    data = np.clip(data, -32768, 32767).astype(np.int16)
                yield data.tobytes()
        finally:
            r.close()

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
