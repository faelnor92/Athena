"""Backend vocal « compatible ESPHome » : Jarvis se connecte aux satellites
ESP32-S3 (ESPHome, composant voice_assistant) via l'API native ESPHome
(aioesphomeapi) et joue le rôle d'assistant — SANS Home Assistant dans la boucle.

Flux par satellite :
  bouton/wake word sur l'ESP -> handle_start -> l'ESP streame l'audio (handle_audio)
  -> handle_stop -> STT (faster-whisper) -> essaim via /api/chat/stream (streaming)
  -> TTS (Piper) PHRASE PAR PHRASE renvoyée au satellite (send_voice_assistant_audio).

⚠️ NON TESTÉ sans matériel : le séquencement des events et le format audio
(sample rate) sont les points à ajuster sur ton ESP (voir le runbook README).

Config : satellites.json (cf. .example). Dépendances : aioesphomeapi (+ voice).
Lancement : python3 -m voice.esphome_satellites   (ou via esphome_satellites.py)
"""
import asyncio
import json
import os
import re

import requests

from .config import voice_config
from .stt import STT
from .tts import TTS

SATELLITES_PATH = os.getenv("SATELLITES_PATH", "satellites.json")
OUT_SR = int(os.getenv("VOICE_OUT_SAMPLE_RATE", "16000"))   # format audio renvoyé au satellite


def _load_satellites() -> list:
    if not os.path.exists(SATELLITES_PATH):
        return []
    try:
        with open(SATELLITES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("satellites", data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"[Satellites] lecture {SATELLITES_PATH} impossible : {e}")
        return []


class Satellite:
    """Gère une connexion à un ESP32-S3 et son pipeline vocal."""

    def __init__(self, cfg: dict, voice_cfg: dict, stt: STT, tts: TTS):
        self.cfg = cfg
        self.vc = voice_cfg
        self.stt = stt
        self.tts = tts
        self.name = cfg.get("name", cfg.get("host", "satellite"))
        self.client = None
        self._buf = bytearray()
        self._in_sr = 16000

    async def connect(self):
        from aioesphomeapi import APIClient
        self.client = APIClient(
            self.cfg["host"], int(self.cfg.get("port", 6053)),
            self.cfg.get("password", ""),
            noise_psk=self.cfg.get("encryption_key") or None,
        )
        await self.client.connect(login=True)
        self.client.subscribe_voice_assistant(
            handle_start=self._on_start,
            handle_stop=self._on_stop,
            handle_audio=self._on_audio,
        )
        print(f"🛰️  Satellite « {self.name} » connecté ({self.cfg['host']}).")

    async def _on_start(self, conversation_id, flags, audio_settings, wake_word_phrase):
        self._buf = bytearray()
        try:
            self._in_sr = int(getattr(audio_settings, "noise_suppression_level", 0) and 16000 or 16000)
        except Exception:
            self._in_sr = 16000
        # 0 = audio reçu via l'API (handle_audio), pas d'UDP.
        return 0

    async def _on_audio(self, data: bytes, data2=None):
        if data:
            self._buf.extend(data)

    async def _on_stop(self, server_side: bool):
        audio = bytes(self._buf)
        self._buf = bytearray()
        if len(audio) < 1600:   # trop court
            await self._event("VOICE_ASSISTANT_RUN_END")
            return
        try:
            await asyncio.to_thread(self._pipeline, audio)
        except Exception as e:
            print(f"[Satellite {self.name}] erreur pipeline : {e}")
            await self._event("VOICE_ASSISTANT_RUN_END")

    async def _event(self, name: str, data=None):
        from aioesphomeapi import VoiceAssistantEventType
        try:
            self.client.send_voice_assistant_event(getattr(VoiceAssistantEventType, name), data)
        except Exception:
            pass

    def _pipeline(self, pcm_in: bytes):
        """STT -> essaim (streaming) -> TTS phrase par phrase -> audio vers le satellite."""
        import numpy as np
        loop = asyncio.get_event_loop() if False else None  # exécuté hors-loop (to_thread)

        # 1. STT
        samples = np.frombuffer(pcm_in, dtype=np.int16).astype("float32") / 32768.0
        text = self.stt.transcribe(samples)
        self._send_event_threadsafe("VOICE_ASSISTANT_STT_END", {"text": text})
        if not text.strip():
            self._send_event_threadsafe("VOICE_ASSISTANT_RUN_END")
            return
        print(f"🗣️  [{self.name}] {text}")

        # 2. Essaim en streaming + 3. TTS phrase par phrase renvoyée au satellite
        client_id = f"voice:{self.name}"
        url = f"{self.vc['server_url']}/api/chat/stream"
        self._send_event_threadsafe("VOICE_ASSISTANT_TTS_START")
        buf = {"t": ""}

        def flush(force=False):
            if force:
                seg = buf["t"].strip(); buf["t"] = ""
            else:
                m = list(re.finditer(r"[.!?…:]['\")\]]?\s|\n", buf["t"]))
                if not m:
                    return
                cut = m[-1].end(); seg = buf["t"][:cut].strip(); buf["t"] = buf["t"][cut:]
            if seg:
                self._speak_to_device(seg)

        try:
            with requests.post(url, json={"message": text, "client_id": client_id}, stream=True, timeout=180) as r:
                event = None
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    line = raw.strip()
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        try:
                            d = json.loads(line[5:].strip())
                        except Exception:
                            continue
                        if event == "step" and d.get("type") == "message_delta":
                            buf["t"] += d.get("content", ""); flush()
                        elif event == "done":
                            flush(force=True)
        except Exception as e:
            print(f"[Satellite {self.name}] flux essaim : {e}")
        flush(force=True)
        self._send_event_threadsafe("VOICE_ASSISTANT_TTS_STREAM_END")
        self._send_event_threadsafe("VOICE_ASSISTANT_RUN_END")

    def _speak_to_device(self, sentence: str):
        try:
            wav = self.tts.synth_wav_bytes(sentence)
            pcm, _sr = TTS.wav_to_pcm16(wav, target_sr=OUT_SR)
            # Envoi par trames (depuis le thread worker, planifié sur la loop).
            for i in range(0, len(pcm), 2048):
                self._send_audio_threadsafe(pcm[i:i + 2048])
        except Exception as e:
            print(f"[Satellite {self.name}] TTS : {e}")

    # --- ponts thread worker -> event loop asyncio ---
    def _send_event_threadsafe(self, name, data=None):
        asyncio.run_coroutine_threadsafe(self._event(name, data), self._loop)

    def _send_audio_threadsafe(self, chunk: bytes):
        async def _s():
            try:
                self.client.send_voice_assistant_audio(chunk)
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(_s(), self._loop)


async def run():
    sats = _load_satellites()
    if not sats:
        print(f"Aucun satellite configuré ({SATELLITES_PATH}). Voir satellites.json.example.")
        return
    vc = voice_config()
    stt = STT(vc["stt_model"], vc["stt_device"], vc["stt_compute"], vc["stt_language"])
    tts = TTS(vc["tts_engine"], vc["piper_model"], vc["piper_bin"])
    loop = asyncio.get_event_loop()
    objs = []
    for c in sats:
        s = Satellite(c, vc, stt, tts)
        s._loop = loop
        try:
            await s.connect()
            objs.append(s)
        except Exception as e:
            print(f"[Satellite {c.get('name', c.get('host'))}] connexion impossible : {e}")
    if not objs:
        return
    print(f"🟢 {len(objs)} satellite(s) actif(s). Ctrl+C pour quitter.")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n👋 Arrêt des satellites.")
