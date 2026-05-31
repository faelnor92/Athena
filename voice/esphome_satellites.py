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
import base64
import json
import os
import re
import threading

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


def save_satellites(sats: list) -> None:
    """Écrit la liste des satellites dans satellites.json (format {satellites:[...]})."""
    with open(SATELLITES_PATH, "w", encoding="utf-8") as f:
        json.dump({"satellites": sats}, f, ensure_ascii=False, indent=2)


def upsert_satellite(cfg: dict) -> list:
    """Ajoute ou met à jour un satellite (clé = name). Renvoie la liste à jour.

    Si encryption_key est vide à la mise à jour, on conserve l'ancienne clé
    (pratique pour modifier l'IP sans ressaisir la clé)."""
    name = (cfg.get("name") or "").strip()
    if not name:
        raise ValueError("Le nom du satellite est requis.")
    sats = _load_satellites()
    existing = next((s for s in sats if s.get("name") == name), None)
    entry = {
        "name": name,
        "host": (cfg.get("host") or "").strip(),
        "port": int(cfg.get("port") or 6053),
    }
    key = (cfg.get("encryption_key") or "").strip()
    if not key and existing:
        key = (existing.get("encryption_key") or "").strip()
    if key:
        entry["encryption_key"] = key
    pwd = (cfg.get("password") or "").strip() or (existing.get("password") if existing else "")
    if pwd:
        entry["password"] = pwd
    if existing:
        sats = [entry if s.get("name") == name else s for s in sats]
    else:
        sats.append(entry)
    save_satellites(sats)
    return sats


def delete_satellite(name: str) -> list:
    sats = [s for s in _load_satellites() if s.get("name") != name]
    save_satellites(sats)
    return sats


def generate_encryption_key() -> str:
    """Génère une clé d'API ESPHome (32 octets, base64) à recopier dans le YAML
    de l'ESP (api: encryption: key:) puis ici."""
    return base64.b64encode(os.urandom(32)).decode("ascii")


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", (name or "satellite").lower()).strip("-")
    return s or "satellite"


# Catalogue des capteurs/sorties ESPHome les plus courants, exposé à l'UI.
# group = catégorie d'affichage ; bus = comment il se câble (décide du champ broche
# côté UI et des dépendances i2c/one_wire à injecter dans le YAML).
SENSOR_CATALOG = [
    # Environnement (I2C, tout-en-un)
    {"id": "bme680", "label": "BME680 — temp + humidité + pression + qualité air", "group": "Environnement (I2C)", "bus": "i2c"},
    {"id": "bme280", "label": "BME280 — temp + humidité + pression", "group": "Environnement (I2C)", "bus": "i2c"},
    {"id": "sht3xd", "label": "SHT3x — temp + humidité", "group": "Environnement (I2C)", "bus": "i2c"},
    {"id": "aht10", "label": "AHT10/AHT20 — temp + humidité", "group": "Environnement (I2C)", "bus": "i2c"},
    # Qualité de l'air / CO2 (I2C)
    {"id": "scd4x", "label": "SCD40/41 — CO2 + temp + humidité", "group": "Qualité de l'air (I2C)", "bus": "i2c"},
    {"id": "ens160", "label": "ENS160 — qualité air (eCO2 + COV)", "group": "Qualité de l'air (I2C)", "bus": "i2c"},
    {"id": "sgp30", "label": "SGP30 — eCO2 + COV", "group": "Qualité de l'air (I2C)", "bus": "i2c"},
    {"id": "sgp40", "label": "SGP40 — indice COV", "group": "Qualité de l'air (I2C)", "bus": "i2c"},
    {"id": "ccs811", "label": "CCS811 — eCO2 + COV", "group": "Qualité de l'air (I2C)", "bus": "i2c"},
    # Lumière (I2C)
    {"id": "bh1750", "label": "BH1750 — luminosité (lux)", "group": "Lumière (I2C)", "bus": "i2c"},
    # Température/humidité (GPIO / 1-wire)
    {"id": "dht22", "label": "DHT22/AM2302 — temp + humidité", "group": "Température (GPIO)", "bus": "gpio", "default_pin": "GPIO4"},
    {"id": "dht11", "label": "DHT11 — temp + humidité", "group": "Température (GPIO)", "bus": "gpio", "default_pin": "GPIO4"},
    {"id": "ds18b20", "label": "DS18B20 — température (1-wire)", "group": "Température (GPIO)", "bus": "onewire", "default_pin": "GPIO4"},
    # Détection (GPIO binaire)
    {"id": "pir", "label": "PIR — détecteur de présence", "group": "Détection (GPIO)", "bus": "gpio", "default_pin": "GPIO5"},
    {"id": "contact", "label": "Contact porte/fenêtre", "group": "Détection (GPIO)", "bus": "gpio", "default_pin": "GPIO5"},
    {"id": "button", "label": "Bouton poussoir", "group": "Détection (GPIO)", "bus": "gpio", "default_pin": "GPIO8"},
    # Sorties
    {"id": "relay", "label": "Relais / interrupteur", "group": "Sorties (GPIO)", "bus": "gpio", "default_pin": "GPIO6"},
    {"id": "led", "label": "LED simple (allumée/éteinte)", "group": "Sorties (GPIO)", "bus": "gpio", "default_pin": "GPIO7"},
    # Analogique
    {"id": "adc", "label": "Entrée analogique (ADC)", "group": "Autre", "bus": "adc", "default_pin": "GPIO1"},
]
_CATALOG_BY_ID = {c["id"]: c for c in SENSOR_CATALOG}


def _sensor_block(module: dict):
    """Retourne un dict décrivant le bloc YAML d'un capteur choisi :
    {section, item, needs_i2c, onewire_pin}. section ∈ {sensor, binary_sensor, switch}."""
    t = (module.get("type") or "").strip()
    nm = (module.get("name") or t or "capteur").strip()
    pin = (module.get("pin") or "").strip() or (_CATALOG_BY_ID.get(t, {}).get("default_pin") or "GPIO4")

    def out(section, item, needs_i2c=False, onewire_pin=None):
        return {"section": section, "item": item, "needs_i2c": needs_i2c, "onewire_pin": onewire_pin}

    # --- GPIO / 1-wire ---
    if t in ("dht22", "dht11"):
        model = "AM2302" if t == "dht22" else "DHT11"
        return out("sensor",
                   f"  - platform: dht\n    model: {model}\n    pin: {pin}\n"
                   f"    temperature:\n      name: \"Température {nm}\"\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"\n    update_interval: 60s")
    if t == "ds18b20":
        return out("sensor",
                   f"  - platform: dallas_temp\n    name: \"Température {nm}\"\n    update_interval: 60s",
                   onewire_pin=pin)
    if t == "pir":
        return out("binary_sensor",
                   f"  - platform: gpio\n    pin: {pin}\n    name: \"Présence {nm}\"\n    device_class: motion")
    if t == "contact":
        return out("binary_sensor",
                   f"  - platform: gpio\n    pin: {pin}\n    name: \"{nm}\"\n    device_class: door")
    if t == "button":
        return out("binary_sensor", f"  - platform: gpio\n    pin: {pin}\n    name: \"{nm}\"")
    if t in ("relay", "led"):
        return out("switch", f"  - platform: gpio\n    pin: {pin}\n    name: \"{nm}\"")
    if t == "adc":
        return out("sensor",
                   f"  - platform: adc\n    pin: {pin}\n    name: \"{nm}\"\n    attenuation: 12db\n    update_interval: 60s")

    # --- I2C ---
    if t == "bme680":
        return out("sensor",
                   f"  - platform: bme680\n    address: 0x76\n"
                   f"    temperature:\n      name: \"Température {nm}\"\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"\n"
                   f"    pressure:\n      name: \"Pression {nm}\"\n"
                   f"    gas_resistance:\n      name: \"Qualité air {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "bme280":
        return out("sensor",
                   f"  - platform: bme280_i2c\n    address: 0x76\n"
                   f"    temperature:\n      name: \"Température {nm}\"\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"\n"
                   f"    pressure:\n      name: \"Pression {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "sht3xd":
        return out("sensor",
                   f"  - platform: sht3xd\n    address: 0x44\n"
                   f"    temperature:\n      name: \"Température {nm}\"\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "aht10":
        return out("sensor",
                   f"  - platform: aht10\n"
                   f"    temperature:\n      name: \"Température {nm}\"\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "scd4x":
        return out("sensor",
                   f"  - platform: scd4x\n"
                   f"    co2:\n      name: \"CO2 {nm}\"\n"
                   f"    temperature:\n      name: \"Température {nm}\"\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "ens160":
        return out("sensor",
                   f"  - platform: ens160_i2c\n    address: 0x53\n"
                   f"    eco2:\n      name: \"eCO2 {nm}\"\n"
                   f"    tvoc:\n      name: \"COV {nm}\"\n"
                   f"    aqi:\n      name: \"Qualité air {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "sgp30":
        return out("sensor",
                   f"  - platform: sgp30\n"
                   f"    eco2:\n      name: \"eCO2 {nm}\"\n"
                   f"    tvoc:\n      name: \"COV {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "sgp40":
        return out("sensor",
                   f"  - platform: sgp40\n    name: \"Indice COV {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "ccs811":
        return out("sensor",
                   f"  - platform: ccs811\n"
                   f"    eco2:\n      name: \"eCO2 {nm}\"\n"
                   f"    tvoc:\n      name: \"COV {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "bh1750":
        return out("sensor",
                   f"  - platform: bh1750\n    name: \"Luminosité {nm}\"\n    address: 0x23\n    update_interval: 60s",
                   needs_i2c=True)
    return None


# Carte + audio par défaut (ESP32-S3, micro I2S standard, ampli I2S externe).
DEFAULT_AUDIO = {
    "board": "esp32-s3-devkitc-1",
    "mic_type": "i2s",   # "i2s" (INMP441/ICS-43434…) ou "pdm" (micro MEMS PDM)
    "mic_ws": "GPIO2", "mic_bclk": "GPIO1", "mic_din": "GPIO3",
    "spk_type": "i2s",   # "i2s" (DAC externe type MAX98357A) ou "analog" (DAC interne, ESP32 classique)
    "spk_ws": "GPIO6", "spk_bclk": "GPIO5", "spk_dout": "GPIO7",
}

# Catalogue audio exposé à l'UI (types de micro / sortie).
MIC_TYPES = [
    {"id": "i2s", "label": "I²S numérique standard (INMP441, ICS-43434…)"},
    {"id": "pdm", "label": "I²S PDM (micro MEMS PDM)"},
]
SPEAKER_TYPES = [
    {"id": "i2s", "label": "Numérique I²S (ampli type MAX98357A)"},
    {"id": "analog", "label": "Analogique — DAC interne (ESP32 classique, pas S3)"},
]

# Modes d'activation (comment réveiller le satellite) + wake words embarqués dispo.
ACTIVATION_MODES = [
    {"id": "wakeword", "label": "🎤 Wake word embarqué (mains-libres, ESP32-S3)"},
    {"id": "button", "label": "🔘 Bouton (push-to-talk)"},
]
WAKE_WORDS = [
    {"id": "hey_jarvis", "label": "Hey Jarvis"},
    {"id": "okay_nabu", "label": "Okay Nabu"},
    {"id": "hey_mycroft", "label": "Hey Mycroft"},
    {"id": "alexa", "label": "Alexa"},
]


def _audio_block(audio: dict) -> str:
    """Construit i2s_audio + microphone + speaker selon le type de micro (I2S/PDM)
    et de sortie (I2S externe / DAC interne analogique)."""
    a = dict(DEFAULT_AUDIO)
    a.update({k: v for k, v in (audio or {}).items() if v})
    mic_pdm = (a["mic_type"] == "pdm")
    spk_analog = (a["spk_type"] == "analog")

    # Bus i2s_audio : entrée (micro) + sortie (si I2S externe).
    i2s = "i2s_audio:\n"
    i2s += f"  - id: i2s_in\n    i2s_lrclk_pin: {a['mic_ws']}"
    if not mic_pdm:  # le PDM n'utilise pas de bclk
        i2s += f"\n    i2s_bclk_pin: {a['mic_bclk']}"
    i2s += "\n"
    if not spk_analog:
        i2s += f"  - id: i2s_out\n    i2s_lrclk_pin: {a['spk_ws']}\n    i2s_bclk_pin: {a['spk_bclk']}\n"

    mic = ("microphone:\n  - platform: i2s_audio\n    id: mic\n    i2s_audio_id: i2s_in\n"
           f"    i2s_din_pin: {a['mic_din']}\n    adc_type: external\n    pdm: {'true' if mic_pdm else 'false'}\n")

    if spk_analog:
        spk = ("speaker:\n  - platform: i2s_audio\n    id: spk\n    i2s_audio_id: i2s_in\n"
               "    dac_type: internal   # DAC interne ESP32 classique (GPIO25/26) — PAS sur ESP32-S3\n")
    else:
        spk = ("speaker:\n  - platform: i2s_audio\n    id: spk\n    i2s_audio_id: i2s_out\n"
               f"    i2s_dout_pin: {a['spk_dout']}\n    dac_type: external\n")

    note = "# --- Audio (ADAPTE LES BROCHES) "
    note += f": micro {'PDM' if mic_pdm else 'I2S standard'}, sortie {'analogique (DAC interne)' if spk_analog else 'I2S numérique'} ---\n"
    return note + i2s + "\n" + mic + "\n" + spk


def generate_yaml(name: str, encryption_key: str = "", modules=None,
                  i2c_sda: str = "GPIO8", i2c_scl: str = "GPIO9",
                  audio: dict = None, activation: dict = None, custom_yaml: str = "") -> str:
    """Construit un YAML ESPHome prêt à compiler : base + voix (→ Jarvis) + capteurs
    choisis dans le catalogue (+ YAML perso optionnel). Injecte automatiquement le
    bus I2C / one_wire si des capteurs en ont besoin. Broches à adapter à la carte.

    activation = {mode: 'wakeword'|'button', wake_word: 'hey_jarvis', button_pin: 'GPIO0'}.
    """
    node = f"jarvis-satellite-{_slug(name)}"
    key = (encryption_key or "").strip() or generate_encryption_key()
    modules = modules or []

    act = {"mode": "wakeword", "wake_word": "hey_jarvis", "button_pin": "GPIO0"}
    act.update({k: v for k, v in (activation or {}).items() if v})
    mode = act["mode"]

    sections = {"sensor": [], "binary_sensor": [], "switch": []}
    if mode == "button":
        sections["binary_sensor"].append(
            f"  - platform: gpio\n    pin: {act['button_pin']}          # bouton (push-to-talk)\n"
            "    name: \"Parler\"\n    on_press:\n      - voice_assistant.start\n"
            "    on_release:\n      - voice_assistant.stop"
        )
    needs_i2c = False
    onewire_pin = None
    for m in modules:
        blk = _sensor_block(m)
        if not blk:
            continue
        sections.setdefault(blk["section"], []).append(blk["item"])
        needs_i2c = needs_i2c or blk["needs_i2c"]
        if blk["onewire_pin"]:
            onewire_pin = blk["onewire_pin"]

    buses = ""
    if needs_i2c:
        buses += f"\ni2c:\n  sda: {i2c_sda or 'GPIO8'}\n  scl: {i2c_scl or 'GPIO9'}\n  scan: true\n"
    if onewire_pin:
        buses += f"\none_wire:\n  - platform: gpio\n    pin: {onewire_pin}\n"

    extra_sections = ""
    for key_name in ("sensor", "binary_sensor", "switch"):
        items = sections.get(key_name) or []
        if items:
            extra_sections += f"\n{key_name}:\n" + "\n".join(items) + "\n"

    custom = (custom_yaml or "").strip()
    custom_part = ""
    if custom:
        custom_part = "\n# --- Blocs YAML personnalisés (avancé) ---\n" + custom + "\n"

    a = dict(DEFAULT_AUDIO)
    a.update({k: v for k, v in (audio or {}).items() if v})
    board = a["board"]
    audio_block = _audio_block(a)

    # Bloc d'activation : wake word embarqué (mains-libres) ou bouton.
    if mode == "wakeword":
        ww = act.get("wake_word") or "hey_jarvis"
        voice_block = (
            "# --- PSRAM requise pour le wake word embarqué (adapte au besoin) ---\n"
            "psram:\n\n"
            "# --- Wake word embarqué (mains-libres) : tourne sur l'ESP32-S3 ---\n"
            "micro_wake_word:\n"
            f"  models:\n    - model: {ww}\n"
            "  on_wake_word_detected:\n    - voice_assistant.start\n\n"
            "# --- Assistant vocal géré par Jarvis ---\n"
            "voice_assistant:\n  microphone: mic\n  speaker: spk\n"
        )
    else:
        voice_block = (
            "# --- Assistant vocal : push-to-talk (bouton), géré par Jarvis ---\n"
            "voice_assistant:\n  microphone: mic\n  speaker: spk\n  use_wake_word: false\n"
        )

    return f"""# Satellite ESP32-S3 piloté DIRECTEMENT par Jarvis (voix), capteurs visibles aussi par HA.
# Généré par Jarvis pour « {name} ». Adapte les broches (I2S + capteurs) à ta carte.
#
# Compiler + flasher (USB la 1re fois, OTA WiFi ensuite) :
#   pip install esphome
#   esphome run {node}.yaml
# Les capteurs restent diffusés à TOUS les clients API (HA ET Jarvis en parallèle).

esphome:
  name: {node}

esp32:
  board: {board}
  framework:
    type: esp-idf

logger:
api:
  encryption:
    key: "{key}"
ota:
wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
{buses}
{audio_block}
{voice_block}{extra_sections}{custom_part}"""


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


async def _connect_all(loop, sats):
    """Construit STT/TTS et connecte chaque satellite. Renvoie (objs, errors)."""
    vc = voice_config()
    stt = STT(vc["stt_model"], vc["stt_device"], vc["stt_compute"], vc["stt_language"])
    tts = TTS(vc["tts_engine"], vc["piper_model"], vc["piper_bin"])
    objs, errors = [], {}
    for c in sats:
        s = Satellite(c, vc, stt, tts)
        s._loop = loop
        label = c.get("name", c.get("host", "?"))
        try:
            # Bornage : un ESP injoignable ne doit pas bloquer le statut indéfiniment.
            await asyncio.wait_for(s.connect(), timeout=15)
            objs.append(s)
        except asyncio.TimeoutError:
            errors[label] = "délai de connexion dépassé (ESP injoignable ?)"
            print(f"[Satellite {label}] timeout de connexion.")
        except Exception as e:
            errors[label] = str(e)
            print(f"[Satellite {label}] connexion impossible : {e}")
    return objs, errors


async def run():
    """Mode autonome (script) : connecte et tourne jusqu'à Ctrl+C."""
    sats = _load_satellites()
    if not sats:
        print(f"Aucun satellite configuré ({SATELLITES_PATH}). Voir satellites.json.example.")
        return
    loop = asyncio.get_event_loop()
    objs, _errors = await _connect_all(loop, sats)
    if not objs:
        return
    print(f"🟢 {len(objs)} satellite(s) actif(s). Ctrl+C pour quitter.")
    while True:
        await asyncio.sleep(3600)


class SatelliteManager:
    """Pilote le listener satellites dans un thread/loop dédié, intégré au serveur.

    Permet de connecter/déconnecter les ESP depuis l'UI, sans script séparé, et
    sans planter le serveur si les dépendances vocales (aioesphomeapi, whisper,
    Piper) sont absentes — l'erreur est alors remontée dans status()."""

    def __init__(self):
        self._thread = None
        self._loop = None
        self._stop = None
        self._objs = []
        self._lock = threading.Lock()
        self._status = {"running": False, "deps_ok": None, "connected": [], "errors": {}}

    def status(self) -> dict:
        with self._lock:
            s = dict(self._status)
            s["connected"] = list(self._status["connected"])
            s["errors"] = dict(self._status["errors"])
        s["configured"] = len(_load_satellites())
        return s

    def _set(self, **kw):
        with self._lock:
            self._status.update(kw)

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
        self._thread = threading.Thread(target=self._run_thread, daemon=True, name="satellites")
        self._thread.start()

    def _run_thread(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._amain())
        except Exception as e:
            self._set(running=False, errors={"_loop": str(e)})
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._set(running=False, connected=[])

    async def _amain(self):
        self._stop = asyncio.Event()
        sats = _load_satellites()
        if not sats:
            self._set(running=False, connected=[], errors={"_": "Aucun satellite configuré."})
            return
        # Vérifier la présence de la lib ESPHome avant de tenter une connexion.
        try:
            import aioesphomeapi  # noqa: F401
        except Exception as e:
            self._set(running=False, deps_ok=False,
                      errors={"_deps": f"aioesphomeapi manquant (pip install -r requirements-voice.txt) : {e}"})
            return
        try:
            objs, errors = await _connect_all(self._loop, sats)
        except Exception as e:
            self._set(running=False, deps_ok=False, errors={"_init": str(e)})
            return
        self._objs = objs
        self._set(running=bool(objs), deps_ok=True,
                  connected=[o.name for o in objs], errors=errors)
        if not objs:
            return
        print(f"🛰️  [Satellites] {len(objs)} connecté(s) : {', '.join(o.name for o in objs)}")
        await self._stop.wait()
        for o in objs:
            try:
                await o.client.disconnect()
            except Exception:
                pass
        self._set(running=False, connected=[])

    def stop(self):
        loop, stop = self._loop, self._stop
        if loop and stop and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(stop.set)
            except Exception:
                pass
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=10)
        self._set(running=False, connected=[])

    def restart(self):
        self.stop()
        self.start()


# Singleton utilisé par le serveur.
manager = SatelliteManager()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n👋 Arrêt des satellites.")
