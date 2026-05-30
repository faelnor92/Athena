"""Boucle de l'assistant vocal local.

Flux : (wake word) → enregistrement (VAD par énergie) → STT → envoi au serveur
Jarvis via /api/chat/stream (canal 'voice') → TTS des réponses au fil de l'eau.

Réutilise l'API HTTP du serveur : il bénéficie donc des sessions par canal, des
permissions (canal 'voice' = auto-approuvé) et du streaming SSE déjà en place.
"""
import json
import time

import requests

from .config import voice_config
from .stt import STT
from .tts import TTS
from .wakeword import WakeWord


class VoiceAssistant:
    def __init__(self, cfg=None):
        self.cfg = cfg or voice_config()
        c = self.cfg
        self.stt = STT(c["stt_model"], c["stt_device"], c["stt_compute"], c["stt_language"])
        self.tts = TTS(c["tts_engine"], c["piper_model"], c["piper_bin"])
        self.wake = WakeWord(c["wake_engine"], c["wake_word"], c["porcupine_key"], c["sample_rate"])

    # ------------------------------------------------------------------ HTTP
    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.cfg["auth_token"]:
            h["Authorization"] = f"Bearer {self.cfg['auth_token']}"
        return h

    # --------------------------------------------------------------- capture
    def wait_for_wake(self):
        if not self.wake.enabled:
            input("⏎  [Entrée] pour parler... ")
            return
        import sounddevice as sd
        sr = self.cfg["sample_rate"]
        block = int(sr * self.cfg["block_ms"] / 1000)
        print(f"🎙️  En écoute du mot d'activation « {self.cfg['wake_word']} »...")
        with sd.InputStream(samplerate=sr, channels=1, dtype="int16", blocksize=block) as stream:
            while True:
                data, _ = stream.read(block)
                if self.wake.detect(data[:, 0]):
                    return

    def record_utterance(self):
        """Enregistre jusqu'au silence (VAD par énergie RMS). Renvoie un numpy float32."""
        import sounddevice as sd
        import numpy as np
        sr = self.cfg["sample_rate"]
        block = int(sr * self.cfg["block_ms"] / 1000)
        silence_blocks = max(1, int(self.cfg["silence_ms"] / self.cfg["block_ms"]))
        frames, silent, started = [], 0, time.time()
        with sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=block) as stream:
            while True:
                data, _ = stream.read(block)
                mono = data[:, 0]
                frames.append(mono.copy())
                rms = float(np.sqrt(np.mean(mono ** 2)) + 1e-9)
                if rms < self.cfg["silence_rms"]:
                    silent += 1
                    if silent >= silence_blocks and len(frames) > silence_blocks:
                        break
                else:
                    silent = 0
                if time.time() - started > self.cfg["max_record_s"]:
                    break
        return np.concatenate(frames).astype("float32")

    # --------------------------------------------------------------- dialogue
    def stream_and_speak(self, text: str):
        url = f"{self.cfg['server_url']}/api/chat/stream"
        payload = {"message": text, "client_id": self.cfg["client_id"]}
        event = None
        with requests.post(url, json=payload, headers=self._headers(), stream=True, timeout=180) as r:
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    if event == "step" and data.get("type") == "message":
                        content = data.get("content", "")
                        if content:
                            print(f"🤖 {content}")
                            self.tts.speak(content)
                    elif event == "error":
                        msg = data.get("detail", "erreur inconnue")
                        print(f"⚠️  {msg}")
                        self.tts.speak("Désolé, une erreur est survenue.")

    # ------------------------------------------------------------------- run
    def run(self):
        print("🟢 Assistant vocal Jarvis démarré. Ctrl+C pour quitter.")
        while True:
            try:
                self.wait_for_wake()
                print("🔴 Enregistrement...")
                audio = self.record_utterance()
                print("📝 Transcription...")
                text = self.stt.transcribe(audio)
                if not text.strip():
                    print("(rien compris)")
                    continue
                print(f"🗣️  Vous : {text}")
                self.stream_and_speak(text)
            except KeyboardInterrupt:
                print("\n👋 Arrêt de l'assistant vocal.")
                break
            except Exception as e:
                print(f"⚠️  Erreur : {e}")
                time.sleep(0.5)
