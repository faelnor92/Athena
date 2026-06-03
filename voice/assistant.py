"""Boucle de l'assistant vocal local.

Flux : (wake word) → enregistrement (VAD par énergie) → STT → envoi au serveur
Jarvis via /api/chat/stream (canal 'voice') → TTS des réponses au fil de l'eau.

Réutilise l'API HTTP du serveur : il bénéficie donc des sessions par canal, des
permissions (canal 'voice' = auto-approuvé) et du streaming SSE déjà en place.
"""
import json
import re
import threading
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
        # Mode STT : wake word custom (ex. « Athena ») détecté par transcription d'une
        # fenêtre glissante — aucun modèle à entraîner, marche pour n'importe quel mot.
        if self.cfg["wake_engine"] == "stt":
            return self._wait_for_wake_stt()
        import sounddevice as sd
        sr = self.cfg["sample_rate"]
        block = int(sr * self.cfg["block_ms"] / 1000)
        print(f"🎙️  En écoute du mot d'activation « {self.cfg['wake_word']} »...")
        with sd.InputStream(samplerate=sr, channels=1, dtype="int16", blocksize=block) as stream:
            while True:
                data, _ = stream.read(block)
                if self.wake.detect(data[:, 0]):
                    return

    def _wait_for_wake_stt(self):
        """Wake word par STT : transcrit une fenêtre glissante (~1.5 s) toutes les ~0.6 s
        (uniquement quand il y a du son) et déclenche si le mot d'activation y apparaît."""
        import sounddevice as sd
        import numpy as np
        from .wakeword import phrase_in_text
        sr = self.cfg["sample_rate"]
        block = int(sr * self.cfg["block_ms"] / 1000)
        win_blocks = max(1, int(1500 / self.cfg["block_ms"]))
        phrase = self.cfg["wake_word"]
        print(f"🎙️  En écoute du mot d'activation « {phrase} » (STT)...")
        win, last_check = [], 0.0
        with sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=block) as stream:
            while True:
                data, _ = stream.read(block)
                win.append(data[:, 0].copy())
                if len(win) > win_blocks:
                    win.pop(0)
                now = time.time()
                if now - last_check < 0.6:
                    continue
                last_check = now
                samples = np.concatenate(win)
                rms = float(np.sqrt(np.mean(samples ** 2)) + 1e-9)
                if rms < self.cfg["silence_rms"]:
                    continue  # silence → on ne transcrit pas (économie CPU)
                try:
                    text = self.stt.transcribe(samples)
                except Exception:
                    continue
                if phrase_in_text(text, phrase):
                    win.clear()
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

    # ------------------------------------------------------------- barge-in
    def _barge_in_monitor(self, interrupted: threading.Event, stop: threading.Event):
        """Écoute le micro pendant que Jarvis parle ; déclenche `interrupted`
        si le wake word est redétecté (l'utilisateur reprend la parole)."""
        try:
            import sounddevice as sd
            sr = self.cfg["sample_rate"]
            block = int(sr * self.cfg["block_ms"] / 1000)
            with sd.InputStream(samplerate=sr, channels=1, dtype="int16", blocksize=block) as stream:
                while not stop.is_set():
                    data, _ = stream.read(block)
                    try:
                        if self.wake.detect(data[:, 0]):
                            interrupted.set()
                            return
                    except Exception:
                        return
        except Exception:
            return

    def _cancel_run(self, run_id):
        if not run_id:
            return
        try:
            requests.post(f"{self.cfg['server_url']}/api/runs/{run_id}/cancel",
                          headers=self._headers(), timeout=5)
        except Exception:
            pass

    # --------------------------------------------------------------- dialogue
    def stream_and_speak(self, text: str, speaker: str = None):
        url = f"{self.cfg['server_url']}/api/chat/stream"
        # Session par locuteur si identifié (mémoire/contexte par personne).
        client_id = f"{self.cfg['client_id']}:{speaker}" if speaker else self.cfg["client_id"]
        if speaker:
            text = f"[Locuteur identifié : {speaker}]\n{text}"
        payload = {"message": text, "client_id": client_id}
        event = None
        run_id = None
        interrupted = threading.Event()
        monitor_stop = threading.Event()
        monitor = None

        # Buffer pour la TTS phrase-par-phrase (latence minimale).
        buffer = {"txt": ""}
        spoke_stream = {"v": False}

        def flush(force=False):
            if interrupted.is_set():
                buffer["txt"] = ""
                return
            if force:
                seg = buffer["txt"].strip()
                buffer["txt"] = ""
                if seg:
                    self.tts.speak(seg, stop_event=interrupted)
                return
            # Micro-chunking (S2S) : on coupe aussi sur les virgules (,) pour démarrer la synthèse très tôt.
            matches = list(re.finditer(r"[.!?…:,]['\")\]]?\s|\n", buffer["txt"]))
            if not matches:
                return
            cut = matches[-1].end()
            seg = buffer["txt"][:cut].strip()
            buffer["txt"] = buffer["txt"][cut:]
            if seg:
                self.tts.speak(seg, stop_event=interrupted)

        try:
            with requests.post(url, json=payload, headers=self._headers(), stream=True, timeout=180) as r:
                for raw in r.iter_lines(decode_unicode=True):
                    if interrupted.is_set():
                        break
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
                        if event == "run":
                            run_id = data.get("run_id")
                            if self.wake.enabled:
                                monitor = threading.Thread(
                                    target=self._barge_in_monitor,
                                    args=(interrupted, monitor_stop), daemon=True)
                                monitor.start()
                        elif event == "step" and data.get("type") == "message_delta":
                            # Token-par-token : on parle dès qu'une phrase est complète.
                            buffer["txt"] += data.get("content", "")
                            spoke_stream["v"] = True
                            flush()
                        elif event == "step" and data.get("type") == "message":
                            content = data.get("content", "")
                            if spoke_stream["v"]:
                                flush(force=True)   # reste éventuel
                            elif content and not interrupted.is_set():
                                print(f"🤖 {content}")
                                self.tts.speak(content, stop_event=interrupted)
                        elif event == "done":
                            flush(force=True)
                        elif event == "error":
                            print(f"⚠️  {data.get('detail', 'erreur inconnue')}")
                            self.tts.speak("Désolé, une erreur est survenue.")
        finally:
            monitor_stop.set()
            if not interrupted.is_set():
                flush(force=True)
        if interrupted.is_set():
            print("⏹️  Interrompu par l'utilisateur — annulation du run.")
            self._cancel_run(run_id)

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
                # Reconnaissance du locuteur (optionnelle).
                speaker = None
                try:
                    from .speaker_id import identify
                    speaker, _score = identify(audio, self.cfg["sample_rate"])
                except Exception:
                    speaker = None
                who = speaker or "Vous"
                print(f"🗣️  {who} : {text}")
                self.stream_and_speak(text, speaker=speaker)
            except KeyboardInterrupt:
                print("\n👋 Arrêt de l'assistant vocal.")
                break
            except Exception as e:
                print(f"⚠️  Erreur : {e}")
                time.sleep(0.5)
