"""Backend vocal « compatible ESPHome » : Athena se connecte aux satellites
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
        # Pièce (optionnel) : doit correspondre à l'état de l'entité de présence HA
        # pour le follow-me (router la voix vers le satellite de la pièce active).
        "area": (cfg.get("area") or (existing.get("area") if existing else "") or "").strip(),
    }
    key = (cfg.get("encryption_key") or "").strip()
    if not key and existing:
        key = (existing.get("encryption_key") or "").strip()
    if key:
        entry["encryption_key"] = key
    pwd = (cfg.get("password") or "").strip() or (existing.get("password") if existing else "")
    if pwd:
        entry["password"] = pwd
    # Mode de réveil : 'embedded' (microWakeWord sur l'ESP) ou 'server' (openWakeWord
    # dans Athena). En mode serveur, le manager fait tourner la détection.
    entry["wake_mode"] = (cfg.get("wake_mode") or (existing.get("wake_mode") if existing else "") or "server")
    entry["wake_word"] = (cfg.get("wake_word") or (existing.get("wake_word") if existing else "") or "hey_athena")
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
    {"id": "pir", "label": "PIR — détecteur de présence (mouvement)", "group": "Détection (GPIO)", "bus": "gpio", "default_pin": "GPIO5"},
    {"id": "rcwl0516", "label": "RCWL-0516 — radar de présence (suivi de pièce, pas cher)", "group": "Détection (GPIO)", "bus": "gpio", "default_pin": "GPIO5"},
    {"id": "contact", "label": "Contact porte/fenêtre", "group": "Détection (GPIO)", "bus": "gpio", "default_pin": "GPIO5"},
    {"id": "button", "label": "Bouton poussoir", "group": "Détection (GPIO)", "bus": "gpio", "default_pin": "GPIO8"},
    # Sorties
    {"id": "relay", "label": "Relais / interrupteur", "group": "Sorties (GPIO)", "bus": "gpio", "default_pin": "GPIO6"},
    {"id": "led", "label": "LED simple (allumée/éteinte)", "group": "Sorties (GPIO)", "bus": "gpio", "default_pin": "GPIO7"},
    # Analogique
    {"id": "adc", "label": "Entrée analogique (ADC)", "group": "Autre", "bus": "adc", "default_pin": "GPIO1"},
]
_CATALOG_BY_ID = {c["id"]: c for c in SENSOR_CATALOG}


def _sensor_block(module: dict, is_src: bool = False, has_src: bool = False):
    """Retourne un dict décrivant le bloc YAML d'un capteur choisi :
    {section, item, needs_i2c, onewire_pin}. section ∈ {sensor, binary_sensor, switch}.

    is_src  : ce capteur temp/humidité sert de SOURCE de compensation (émet id: ath_temp/ath_hum).
    has_src : une source temp/humidité existe → les capteurs COV/eCO2 ajoutent la compensation
              (précision nettement meilleure)."""
    t = (module.get("type") or "").strip()
    nm = (module.get("name") or t or "capteur").strip()
    pin = (module.get("pin") or "").strip() or (_CATALOG_BY_ID.get(t, {}).get("default_pin") or "GPIO4")
    # Identifiants de source de compensation (posés sur le 1er capteur temp/humidité).
    tid = "\n      id: ath_temp" if is_src else ""
    hid = "\n      id: ath_hum" if is_src else ""
    # Bloc de compensation pour les capteurs de gaz (selon la syntaxe de chaque plateforme).
    comp_src = ("\n    compensation:\n      temperature_source: ath_temp\n      humidity_source: ath_hum"
                if has_src else "")
    comp_ens = ("\n    compensation:\n      temperature: ath_temp\n      humidity: ath_hum"
                if has_src else "")

    def out(section, item, needs_i2c=False, onewire_pin=None, needs_bsec=False):
        return {"section": section, "item": item, "needs_i2c": needs_i2c,
                "onewire_pin": onewire_pin, "needs_bsec": needs_bsec}

    # --- GPIO / 1-wire ---
    if t in ("dht22", "dht11"):
        model = "AM2302" if t == "dht22" else "DHT11"
        return out("sensor",
                   f"  - platform: dht\n    model: {model}\n    pin: {pin}\n"
                   f"    temperature:\n      name: \"Température {nm}\"{tid}\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"{hid}\n    update_interval: 60s")
    if t == "ds18b20":
        return out("sensor",
                   f"  - platform: dallas_temp\n    name: \"Température {nm}\"\n    update_interval: 60s",
                   onewire_pin=pin)
    if t in ("pir", "rcwl0516"):
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
        # BSEC2 (Bosch) : sort un INDICE IAQ lisible (0-500), un CO2 équivalent (ppm) et un
        # COV équivalent — au lieu de la résistance de gaz brute (chiffre obscur en ohms).
        return out("sensor",
                   f"  - platform: bme680_bsec2\n"
                   f"    temperature:\n      name: \"Température {nm}\"\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"\n"
                   f"    pressure:\n      name: \"Pression {nm}\"\n"
                   f"    iaq:\n      name: \"Qualité air {nm} (IAQ)\"\n"
                   f"    co2_equivalent:\n      name: \"CO2 équivalent {nm}\"\n"
                   f"    breath_voc_equivalent:\n      name: \"COV équivalent {nm}\"",
                   needs_i2c=True, needs_bsec=True)
    if t == "bme280":
        return out("sensor",
                   f"  - platform: bme280_i2c\n    address: 0x76\n"
                   f"    temperature:\n      name: \"Température {nm}\"{tid}\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"{hid}\n"
                   f"    pressure:\n      name: \"Pression {nm}\"\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "sht3xd":
        return out("sensor",
                   f"  - platform: sht3xd\n    address: 0x44\n"
                   f"    temperature:\n      name: \"Température {nm}\"{tid}\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"{hid}\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "aht10":
        return out("sensor",
                   f"  - platform: aht10\n"
                   f"    temperature:\n      name: \"Température {nm}\"{tid}\n"
                   f"    humidity:\n      name: \"Humidité {nm}\"{hid}\n    update_interval: 60s",
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
                   f"    aqi:\n      name: \"Qualité air {nm}\"{comp_ens}\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "sgp30":
        return out("sensor",
                   f"  - platform: sgp30\n"
                   f"    eco2:\n      name: \"eCO2 {nm}\"\n"
                   f"    tvoc:\n      name: \"COV {nm}\"{comp_src}\n    update_interval: 60s",
                   needs_i2c=True)
    if t == "sgp40":
        return out("sensor",
                   f"  - platform: sgp40\n    name: \"Indice COV {nm}\"{comp_src}\n    update_interval: 60s",
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

# Modes de réveil (tous mains-libres). Plus de push-to-talk.
ACTIVATION_MODES = [
    {"id": "embedded", "label": "🎤 Embarqué (microWakeWord, sur l'ESP32-S3)"},
    {"id": "server", "label": "🛰️ Serveur (openWakeWord, dans Athena)"},
]
# Wake words embarqués (modèles microWakeWord intégrés à ESPHome).
WAKE_WORDS = [
    {"id": "hey_athena", "label": "Hey Athena"},
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
                  audio: dict = None, activation: dict = None, custom_yaml: str = "",
                  led: dict = None, bt_proxy: bool = False, improv: bool = False,
                  volume: dict = None) -> str:
    """Construit un YAML ESPHome prêt à compiler : base + voix (→ Athena) + capteurs
    choisis dans le catalogue (+ YAML perso optionnel). Injecte automatiquement le
    bus I2C / one_wire si des capteurs en ont besoin. Broches à adapter à la carte.

    activation = {mode: 'embedded'|'server', wake_word: 'hey_athena'}. Tous mains-libres.
    """
    node = f"athena-satellite-{_slug(name)}"
    key = (encryption_key or "").strip() or generate_encryption_key()
    modules = modules or []

    act = {"mode": "server", "wake_word": "hey_athena"}
    act.update({k: v for k, v in (activation or {}).items() if v})
    mode = act["mode"]

    sections = {"sensor": [], "binary_sensor": [], "switch": []}
    needs_i2c = False
    needs_bsec = False
    onewire_pin = None
    # Compensation température/humidité des capteurs de gaz (COV/eCO2) : on désigne le 1er
    # capteur temp+humidité comme SOURCE, et les capteurs de gaz s'y réfèrent (meilleure précision).
    _SRC_TYPES = {"aht10", "sht3xd", "bme280", "dht22", "dht11"}
    _src_module = next((m for m in modules if (m.get("type") or "").strip() in _SRC_TYPES), None)
    _has_src = _src_module is not None
    for m in modules:
        blk = _sensor_block(m, is_src=(m is _src_module), has_src=_has_src)
        if not blk:
            continue
        sections.setdefault(blk["section"], []).append(blk["item"])
        needs_i2c = needs_i2c or blk["needs_i2c"]
        needs_bsec = needs_bsec or blk.get("needs_bsec")
        if blk["onewire_pin"]:
            onewire_pin = blk["onewire_pin"]

    buses = ""
    if needs_i2c:
        buses += f"\ni2c:\n  sda: {i2c_sda or 'GPIO8'}\n  scl: {i2c_scl or 'GPIO9'}\n  scan: true\n"
    if onewire_pin:
        buses += f"\none_wire:\n  - platform: gpio\n    pin: {onewire_pin}\n"
    if needs_bsec:
        # Hub BSEC2 (lib Bosch, téléchargée par ESPHome) : indice IAQ calibré.
        # L'IAQ met ~1 h à se calibrer (précision 0→3) ; l'étalonnage est mémorisé en flash.
        buses += ("\nbme680_bsec2:\n  address: 0x76   # essaie 0x77 si non détecté\n"
                  "  state_save_interval: 6h\n")

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

    # LED de statut (option) : WS2812B. Défaut = LED RGB EMBARQUÉE GPIO48 des devkit S3
    # (aucun composant à ajouter). Feedback couleur selon la phase vocale.
    led = led or {}
    led_block = ""
    led_feedback = ""
    if led.get("enabled"):
        led_pin = (led.get("pin") or "GPIO48").strip()
        led_num = int(led.get("num") or 1)
        multi = led_num > 1   # bandeau adressable → animations par LED ; sinon (LED unique) → pulses.
        led_block = (
            f"\nlight:\n  - platform: esp32_rmt_led_strip\n    id: status_led\n"
            f"    pin: {led_pin}\n    num_leds: {led_num}\n    rgb_order: GRB\n"
            f"    chipset: ws2812\n    name: \"LED statut\"\n    default_transition_length: 0s\n"
            "    effects:\n"
            "      - pulse:\n          name: \"Slow Pulse\"\n          transition_length: 250ms\n          update_interval: 250ms\n"
            "      - pulse:\n          name: \"Fast Pulse\"\n          transition_length: 100ms\n          update_interval: 100ms\n"
            "      - addressable_scan:\n          name: \"Scan\"\n          move_interval: 120ms\n          scan_width: 1\n"
            "      - addressable_rainbow:\n          name: \"Arc\"\n          speed: 12\n          width: 50\n"
            "      - addressable_twinkle:\n          name: \"Twinkle\"\n          twinkle_probability: 12%\n          progress_interval: 60ms\n"
            "      - addressable_flicker:\n          name: \"Flicker\"\n          intensity: 40%\n")

        def _on(color, effect=None):
            r, g, b = color
            s = (f"        id: status_led\n        red: {r}%\n        green: {g}%\n        blue: {b}%\n")
            if effect:
                s += f"        effect: \"{effect}\"\n"
            return "    - light.turn_on:\n" + s

        def _on_eff(effect):   # effet seul (sans couleur imposée) — ex. arc-en-ciel.
            return f"    - light.turn_on:\n        id: status_led\n        effect: \"{effect}\"\n"

        # Machine à états via les événements du voice_assistant + connexion à Athena.
        if multi:
            # Bandeau : animations adressables (point qui défile, arc-en-ciel, scintillement…).
            led_feedback = (
                "  on_client_disconnected:\n" + _on((100, 10, 0), "Scan") +        # rouge qui cherche
                "  on_client_connected:\n    - light.turn_off: status_led\n" +     # prêt (repos)
                "  on_listening:\n" + _on((0, 30, 100), "Scan") +                  # point bleu qui défile
                "  on_stt_vad_end:\n" + _on_eff("Arc") +                           # arc-en-ciel : réflexion
                "  on_tts_start:\n" + _on((0, 100, 50), "Twinkle") +               # scintillement vert : répond
                "  on_end:\n    - light.turn_off: status_led\n" +                  # retour repos
                "  on_error:\n" + _on((100, 0, 0), "Flicker"))                     # vacillement rouge : erreur
        else:
            # LED unique (ex. RGB embarquée) : couleurs unies + pulses.
            led_feedback = (
                "  on_client_disconnected:\n" + _on((100, 0, 0), "Slow Pulse") +   # rouge : Athena déconnectée
                "  on_client_connected:\n    - light.turn_off: status_led\n" +     # prêt (au repos)
                "  on_listening:\n" + _on((0, 0, 100)) +                           # bleu : à l'écoute
                "  on_stt_vad_end:\n" + _on((60, 0, 100), "Fast Pulse") +          # violet : réflexion
                "  on_tts_start:\n" + _on((0, 100, 60)) +                          # cyan : répond
                "  on_end:\n    - light.turn_off: status_led\n" +                  # retour repos
                "  on_error:\n" + _on((100, 0, 0), "Fast Pulse"))                  # rouge clignotant : erreur

    # Bloc d'activation (mains-libres) : wake word embarqué (microWakeWord, sur l'ESP)
    # ou serveur (openWakeWord, dans Athena ; l'ESP streame en continu).
    esphome_extra = ""
    if mode == "server":
        # L'ESP streame en continu vers Athena dès que l'API (Athena) est connectée ;
        # c'est Athena qui détecte le wake word (openWakeWord) puis traite la commande.
        esphome_extra = (
            "\n  on_boot:\n    - wait_until:\n        condition:\n          api.connected:\n"
            "    - voice_assistant.start_continuous:\n"
        )
        voice_block = (
            "# --- Wake word SERVEUR : l'ESP streame en continu, ATHENA détecte le mot ---\n"
            "# (moteur côté serveur selon VOICE_WAKE_ENGINE : 'stt' par défaut → mot custom\n"
            "#  « athena » par transcription ; ou 'openwakeword' pour un modèle efficace.)\n"
            "voice_assistant:\n  microphone: mic\n  speaker: spk\n  use_wake_word: false\n"
        )
    else:
        # microWakeWord n'accepte QUE des modèles PRÉ-ENTRAÎNÉS (pas un mot arbitraire) :
        # un mot custom (« athena ») n'a PAS de modèle embarqué → repli okay_nabu + avertissement.
        _MWW_BUILTIN = {"okay_nabu", "hey_jarvis", "hey_mycroft", "alexa"}
        ww = (act.get("wake_word") or "").strip()
        wwl = ww.lower()
        if wwl in _MWW_BUILTIN or wwl.startswith("http"):
            model_line = f"    - model: {ww}\n"
            warn = ""
        else:
            model_line = "    - model: okay_nabu\n"
            warn = (
                "# ⚠ WAKE WORD EMBARQUÉ : microWakeWord ne connaît que des modèles PRÉ-ENTRAÎNÉS\n"
                "#   (okay_nabu, hey_jarvis, hey_mycroft, alexa). "
                f"« {ww or 'athena'} » n'existe PAS en embarqué.\n"
                "#   → on met 'okay_nabu' par défaut. Pour un mot CUSTOM « athena » : choisis le mode\n"
                "#   SERVEUR (Athena le détecte via STT), ou fournis l'URL d'un modèle entraîné\n"
                "#   (model: https://…/athena.json).\n")
        voice_block = (
            warn +
            "# --- PSRAM requise pour le wake word embarqué (DevKitC-1 N8R8 = octale ;\n"
            "#     passe en 'quad' si ta carte a de la PSRAM quad type N8R2) ---\n"
            "psram:\n  mode: octal\n  speed: 80MHz\n\n"
            "# --- Wake word EMBARQUÉ (microWakeWord) : tourne sur l'ESP32-S3 ---\n"
            "micro_wake_word:\n"
            f"  models:\n{model_line}"
            "  on_wake_word_detected:\n    - voice_assistant.start\n\n"
            "# --- Assistant vocal géré par Athena ---\n"
            "voice_assistant:\n  microphone: mic\n  speaker: spk\n"
        )

    voice_block += led_feedback   # feedback LED sur les phases vocales (si LED activée)

    # --- Options radio (sans GPIO) : bluetooth_proxy + improv BLE ---
    radio_block = ""
    if bt_proxy:
        # COEXISTENCE VOIX + BLE : un satellite vocal streame l'audio en continu ; un scan BLE
        # ACTIF (bursts d'émission) lui vole la radio → coupures audio. On scanne donc en PASSIF
        # basse-conso (interval long / fenêtre courte) : largement suffisant pour la présence
        # (follow-me ESPresense/Bermuda) tout en laissant la radio à l'audio + WiFi.
        radio_block += ("\n# --- Bluetooth proxy : relais BLE vers Home Assistant (présence/follow-me).\n"
                        "#     Scan PASSIF basse-conso pour cohabiter avec la voix (anti-coupures). ---\n"
                        "esp32_ble_tracker:\n  scan_parameters:\n    active: false\n"
                        "    interval: 320ms\n    window: 30ms\n"
                        "bluetooth_proxy:\n  active: true\n")
    if improv:
        radio_block += ("\n# --- Improv BLE : configurer le WiFi par Bluetooth à la 1re install (sans GPIO).\n"
                        "#     authorizer: none = pas de bouton requis (provisionnement libre). ---\n"
                        "esp32_improv:\n  authorizer: none\n")

    # --- Boutons volume (GPIO) — défauts SÛRS, avec détection de conflit ---
    vol = volume or {}
    globals_block = ""
    vol_conflict = ""
    if vol.get("enabled"):
        up = (vol.get("up_pin") or "GPIO47").strip()
        down = (vol.get("down_pin") or "GPIO21").strip()
        # Broches déjà occupées → on prévient (cohérence GPIO).
        used = {a["mic_ws"], a["mic_bclk"], a["mic_din"], a["spk_ws"], a["spk_bclk"], a["spk_dout"]}
        if needs_i2c:
            used |= {i2c_sda, i2c_scl}
        if led.get("enabled"):
            used.add(led.get("pin") or "GPIO48")
        for m in modules:
            mp = (m.get("pin") or "").strip()
            if mp:
                used.add(mp)
        clash = [p for p in (up, down) if p in used]
        if clash:
            vol_conflict = f"#   ⚠️ CONFLIT GPIO volume : {', '.join(clash)} déjà utilisé(s) ailleurs — change la broche !\n"
        globals_block = ("\nglobals:\n  - id: spk_vol\n    type: float\n    restore_value: yes\n    initial_value: '0.7'\n")
        vol_bs = (
            f"  - platform: gpio\n    pin:\n      number: {up}\n      mode: INPUT_PULLUP\n      inverted: true\n"
            f"    name: \"Volume +\"\n    on_press:\n      - lambda: 'id(spk_vol) = min(1.0f, id(spk_vol) + 0.1f);'\n"
            f"      - speaker.set_volume:\n          id: spk\n          volume: !lambda 'return id(spk_vol);'\n"
            f"  - platform: gpio\n    pin:\n      number: {down}\n      mode: INPUT_PULLUP\n      inverted: true\n"
            f"    name: \"Volume -\"\n    on_press:\n      - lambda: 'id(spk_vol) = max(0.0f, id(spk_vol) - 0.1f);'\n"
            f"      - speaker.set_volume:\n          id: spk\n          volume: !lambda 'return id(spk_vol);'\n")
        sections.setdefault("binary_sensor", []).append(vol_bs)
        # extra_sections est déjà construit plus haut → on le régénère pour inclure le volume.
        extra_sections_local = ""
        for key_name in ("sensor", "binary_sensor", "switch"):
            items = sections.get(key_name) or []
            if items:
                extra_sections_local += f"\n{key_name}:\n" + "\n".join(items) + "\n"
        extra_sections = extra_sections_local

    # Schéma de câblage (toujours dans l'en-tête du YAML).
    wiring = (
        f"#   INMP441 (micro)  : VDD→3V3 · GND→GND · L/R→GND · WS→{a['mic_ws']} · "
        f"SCK→{a['mic_bclk']} · SD→{a['mic_din']}\n"
        f"#   MAX98357A (ampli): VIN→5V(ou 3V3) · GND→GND · LRC→{a['spk_ws']} · "
        f"BCLK→{a['spk_bclk']} · DIN→{a['spk_dout']} · HP sur +/-\n")
    if needs_i2c:
        wiring += f"#   Capteur I2C      : VCC→3V3 · GND→GND · SDA→{i2c_sda} · SCL→{i2c_scl}\n"
    if onewire_pin:
        wiring += f"#   Capteur 1-wire   : data→{onewire_pin} (+ résistance 4.7kΩ entre data et 3V3)\n"
    if led.get("enabled"):
        _lp = (led.get("pin") or "GPIO48").strip()
        _ln = int(led.get("num") or 1)
        if _lp.upper() == "GPIO48" and _ln <= 1:
            wiring += "#   LED statut       : GPIO48 = LED RGB EMBARQUÉE sur la devkit (rien à câbler)\n"
        else:
            wiring += (f"#   Bandeau LED ({_ln}×) : 5V→5V · GND→GND · DIN→{_lp} "
                       f"(WS2812B ; 330Ω en série sur DIN conseillée)\n")
    if vol.get("enabled"):
        wiring += (f"#   Boutons volume   : Vol+ →{(vol.get('up_pin') or 'GPIO47')} · "
                   f"Vol- →{(vol.get('down_pin') or 'GPIO21')} (vers GND, INPUT_PULLUP)\n")
    wiring += vol_conflict

    return f"""# Satellite ESP32-S3 piloté DIRECTEMENT par Athena (voix), capteurs visibles aussi par HA.
# Généré par Athena pour « {name} ». Adapte les broches (I2S + capteurs) à ta carte.
#
# --- CÂBLAGE ---
{wiring}#
# Compiler + flasher (USB la 1re fois, OTA WiFi ensuite) :
#   pip install esphome
#   esphome run {node}.yaml
# Les capteurs restent diffusés à TOUS les clients API (HA ET Athena en parallèle).

esphome:
  name: {node}{esphome_extra}

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
{radio_block}{globals_block}{buses}
{audio_block}
{voice_block}{led_block}{extra_sections}{custom_part}"""


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
        # Mode de réveil : 'server' => Athena détecte le wake word (openWakeWord) ;
        # 'embedded' => l'ESP a déjà déclenché (microWakeWord), on traite directement.
        self.wake_mode = cfg.get("wake_mode", "embedded")
        self._wake = None

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

    def _detect_wake(self, pcm_in: bytes) -> bool:
        """Mode serveur : détecte le wake word dans le segment audio. Moteur 'stt'
        (recommandé pour un mot custom comme « Athena ») = transcription + recherche du
        mot ; sinon openWakeWord. En cas d'erreur/lib absente, on ne bloque pas."""
        try:
            import numpy as np
            engine = self.vc.get("wake_engine", "openwakeword")
            phrase = self.vc.get("wake_word", "hey athena")
            # STT : on transcrit le segment et on cherche le mot d'activation.
            if engine == "stt":
                from .wakeword import phrase_in_text
                samples = np.frombuffer(pcm_in, dtype=np.int16).astype("float32") / 32768.0
                text = self.stt.transcribe(samples)
                return phrase_in_text(text, phrase)
            # openWakeWord (modèles intégrés).
            if self._wake is None:
                from .wakeword import WakeWord
                self._wake = WakeWord(engine, phrase, self.vc.get("porcupine_key", ""), 16000)
            samples = np.frombuffer(pcm_in, dtype=np.int16)
            for i in range(0, max(0, len(samples) - 1280), 1280):
                if self._wake.detect(samples[i:i + 1280]):
                    return True
            return False
        except Exception as e:
            print(f"[Satellite {self.name}] wake word serveur indisponible ({e}) — segment traité par défaut.")
            return True

    def _pipeline(self, pcm_in: bytes):
        """STT -> essaim (streaming) -> TTS phrase par phrase -> audio vers le satellite."""
        import numpy as np
        loop = asyncio.get_event_loop() if False else None  # exécuté hors-loop (to_thread)

        # 0. Mode serveur : ne traiter que si le wake word est détecté dans le segment.
        if self.wake_mode == "server" and not self._detect_wake(pcm_in):
            self._send_event_threadsafe("VOICE_ASSISTANT_RUN_END")
            return

        # 1. STT
        samples = np.frombuffer(pcm_in, dtype=np.int16).astype("float32") / 32768.0
        text = self.stt.transcribe(samples)
        self._send_event_threadsafe("VOICE_ASSISTANT_STT_END", {"text": text})
        if not text.strip():
            self._send_event_threadsafe("VOICE_ASSISTANT_RUN_END")
            return
        print(f"🗣️  [{self.name}] {text}")

        # 2. Essaim en streaming + 3. TTS phrase par phrase renvoyée au satellite
        client_id = "voice_home"  # Mémoire partagée entre tous les satellites de la maison
        url = f"{self.vc['server_url']}/api/chat/stream"
        self._send_event_threadsafe("VOICE_ASSISTANT_TTS_START")
        buf = {"t": ""}

        def flush(force=False):
            if force:
                seg = buf["t"].strip(); buf["t"] = ""
            else:
                # Micro-chunking S2S (avec les virgules)
                m = list(re.finditer(r"[.!?…:,]['\")\]]?\s|\n", buf["t"]))
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
            # Streaming direct HTTP -> PCM -> ESP32
            for pcm_chunk in self.tts.synth_stream(sentence, target_sr=OUT_SR):
                # Envoi par trames
                for i in range(0, len(pcm_chunk), 2048):
                    self._send_audio_threadsafe(pcm_chunk[i:i + 2048])
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
