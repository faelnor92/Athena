import os
import asyncio
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["Config Voice & Satellites"])

class VoiceWakeRequest(BaseModel):
    engine: str = "stt"
    word: str = "Athena"

@router.get("/api/config/voice-wake")
async def get_voice_wake() -> Dict[str, str]:
    """Mot d'activation vocal courant (moteur + mot)."""
    return {
        "engine": os.getenv("VOICE_WAKE_ENGINE", "stt"),
        "word": os.getenv("VOICE_WAKE_WORD", "Athena")
    }

@router.post("/api/config/voice-wake")
async def set_voice_wake(req: VoiceWakeRequest) -> Dict[str, str]:
    """Change le mot d'activation vocal : persiste dans .env, applique À CHAUD."""
    engine = (req.engine or "stt").strip() or "stt"
    word = (req.word or "Athena").strip() or "Athena"
    try:
        from setup_wizard import set_env_var
        set_env_var("VOICE_WAKE_ENGINE", engine)
        set_env_var("VOICE_WAKE_WORD", word)
    except Exception as e:
        import logging
        logging.exception("Erreur écriture .env pour VOICE_WAKE")
        raise HTTPException(status_code=500, detail=f"Écriture .env impossible : {e}")
        
    os.environ["VOICE_WAKE_ENGINE"] = engine
    os.environ["VOICE_WAKE_WORD"] = word
    
    try:
        from voice.esphome_satellites import manager as sat_mgr, _load_satellites
        if _load_satellites():
            await asyncio.to_thread(sat_mgr.restart)
    except Exception as e:
        import logging
        logging.warning(f"Impossible de redémarrer les satellites : {e}")
        
    return {"status": "success", "engine": engine, "word": word}

class SaveSatelliteRequest(BaseModel):
    name: str
    host: str = ""
    port: int = 6053
    encryption_key: str = ""
    password: str = ""
    wake_mode: str = "embedded"
    wake_word: str = "hey_athena"

@router.get("/api/config/satellites")
async def get_config_satellites() -> Dict[str, Any]:
    """Liste les satellites configurés (clé masquée) + état de connexion live."""
    try:
        from voice import esphome_satellites as es
        sats = es._load_satellites()
        safe = [{
            "name": s.get("name"),
            "host": s.get("host", ""),
            "port": int(s.get("port", 6053)),
            "key_set": bool(s.get("encryption_key") or s.get("password")),
            "wake_mode": s.get("wake_mode", "embedded"),
            "wake_word": s.get("wake_word", "hey_athena"),
        } for s in sats]
        return {"satellites": safe, "status": es.manager.status()}
    except Exception as e:
        import logging
        logging.exception("Erreur récupération des satellites")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/config/satellites/genkey")
async def gen_satellite_key() -> Dict[str, str]:
    """Génère une clé d'API ESPHome (base64) à recopier dans le YAML de l'ESP."""
    try:
        from voice import esphome_satellites as es
        return {"key": es.generate_encryption_key()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/config/satellites")
async def save_config_satellite(req: SaveSatelliteRequest) -> Dict[str, Any]:
    """Ajoute/met à jour un satellite puis reconnecte le listener."""
    from voice import esphome_satellites as es
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Le nom du satellite est requis.")
    if not req.host.strip():
        raise HTTPException(status_code=400, detail="L'adresse (IP/host) du satellite est requise.")
    try:
        es.upsert_satellite(req.model_dump())
        await asyncio.to_thread(es.manager.restart)
    except Exception as e:
        import logging
        logging.exception("Erreur sauvegarde du satellite")
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "success", "satellites": es.manager.status()}

@router.delete("/api/config/satellites/{name}")
async def delete_config_satellite(name: str) -> Dict[str, Any]:
    """Supprime un satellite puis reconnecte le listener."""
    try:
        from voice import esphome_satellites as es
        es.delete_satellite(name)
        await asyncio.to_thread(es.manager.restart)
        return {"status": "success", "satellites": es.manager.status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/config/satellites/sensor-catalog")
async def get_sensor_catalog() -> Dict[str, Any]:
    """Catalogue capteurs + types audio (micro/sortie) proposés dans l'UI (source unique)."""
    try:
        from voice import esphome_satellites as es
        return {
            "catalog": getattr(es, "SENSOR_CATALOG", {}),
            "mic_types": getattr(es, "MIC_TYPES", {}),
            "speaker_types": getattr(es, "SPEAKER_TYPES", {}),
            "audio_defaults": getattr(es, "DEFAULT_AUDIO", {}),
            "activation_modes": getattr(es, "ACTIVATION_MODES", {}),
            "wake_words": getattr(es, "WAKE_WORDS", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SatelliteYamlRequest(BaseModel):
    name: str
    encryption_key: str = ""
    modules: List[Dict[str, Any]] = []
    i2c_sda: str = "GPIO8"
    i2c_scl: str = "GPIO9"
    audio: Dict[str, Any] = {}
    activation: Dict[str, Any] = {}
    custom_yaml: str = ""
    led: Dict[str, Any] = {}

@router.post("/api/config/satellites/yaml")
async def gen_satellite_yaml(req: SatelliteYamlRequest) -> Dict[str, str]:
    """Génère le YAML ESPHome prêt à compiler."""
    try:
        from voice import esphome_satellites as es
        name = (req.name or "").strip() or "salon"
        key = (req.encryption_key or "").strip()
        if not key:
            existing = next((s for s in es._load_satellites() if s.get("name") == name), None)
            if existing:
                key = (existing.get("encryption_key") or "").strip()
                
        yaml_text = es.generate_yaml(
            name, key, modules=req.modules,
            i2c_sda=req.i2c_sda, i2c_scl=req.i2c_scl, audio=req.audio,
            activation=req.activation, custom_yaml=req.custom_yaml, led=req.led,
        )
        return {"yaml": yaml_text, "filename": f"athena-satellite-{es._slug(name)}.yaml"}
    except Exception as e:
        import logging
        logging.exception("Erreur lors de la génération du YAML satellite")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/config/satellites/connect")
async def connect_satellites() -> Dict[str, Any]:
    """(Re)connecte tous les satellites configurés."""
    try:
        from voice import esphome_satellites as es
        await asyncio.to_thread(es.manager.restart)
        return {"status": "success", "satellites": es.manager.status()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/system/tts/restart")
async def restart_kokoro_tts() -> Dict[str, Any]:
    """Redémarre le conteneur Docker Kokoro-TTS s'il existe."""
    import subprocess
    import shutil
    if not shutil.which("docker"):
        raise HTTPException(status_code=400, detail="Docker n'est pas installé sur la machine.")
    try:
        res = await asyncio.to_thread(subprocess.run, ["docker", "ps", "-a", "-q", "-f", "name=kokoro-tts"], capture_output=True, text=True)
        if not res.stdout.strip():
            raise HTTPException(status_code=404, detail="Conteneur 'kokoro-tts' introuvable.")

        await asyncio.to_thread(subprocess.run, ["docker", "restart", "kokoro-tts"], check=True)
        return {"status": "success", "message": "Serveur TTS redémarré avec succès."}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Erreur Docker: {e}")


# ----------------------------------------------------------------- TTS (chat + satellites)
def _kokoro_voices_url() -> str:
    """Déduit l'URL de la liste des voix Kokoro depuis VOICE_TTS_HTTP_URL (…/v1/audio/speech)."""
    base = (os.getenv("VOICE_TTS_HTTP_URL", "") or "").strip()
    if not base:
        return ""
    if "/audio/speech" in base:
        return base.replace("/audio/speech", "/audio/voices")
    return base.rstrip("/") + "/v1/audio/voices"


@router.get("/api/config/voice-tts")
async def get_voice_tts() -> Dict[str, Any]:
    """Réglages TTS courants (moteur, voix, URL serveur, émotion par marqueur, vitesse)."""
    return {
        "engine": os.getenv("VOICE_TTS_ENGINE", "http"),
        "voice": _clean_voice(os.getenv("VOICE_TTS_VOICE", "")),
        "http_url": (os.getenv("VOICE_TTS_HTTP_URL", "") or "").strip(),
        "emotion_markers": os.getenv("VOICE_TTS_EMOTION_MARKERS", "false").lower() in ("true", "1", "yes"),
        "speed": (os.getenv("VOICE_TTS_SPEED", "1.0") or "1.0").strip(),
    }


_LANG_FLAG = {"a": "🇺🇸", "b": "🇬🇧", "e": "🇪🇸", "f": "🇫🇷", "h": "🇮🇳",
              "i": "🇮🇹", "j": "🇯🇵", "p": "🇧🇷", "z": "🇨🇳"}


def _voice_label(vid: str) -> str:
    """Transforme un ID de voix Kokoro (ex. « ff_siwis », « am_adam ») en libellé lisible
    « 🇫🇷 Siwis (féminine) ». Conventions Kokoro : 1ʳᵉ lettre = langue, 2ᵉ = genre (f/m)."""
    # Défensif : si un objet {id/name} arrive ici, on en extrait l'ID (jamais de dict brut affiché).
    if isinstance(vid, dict):
        vid = vid.get("id") or vid.get("name") or vid.get("voice") or ""
    s = str(vid).strip()
    flag, gender, name = "", "", s
    if len(s) >= 3 and s[2] == "_":
        flag = _LANG_FLAG.get(s[0].lower(), "")
        gender = {"f": "féminine", "m": "masculine"}.get(s[1].lower(), "")
        name = s[3:]
    name = name.replace("_", " ").strip().title() or s
    parts = [p for p in (flag, name, (f"({gender})" if gender else "")) if p]
    return " ".join(parts)


def _extract_voice_id(item) -> str:
    """Récupère l'ID propre d'une voix, que Kokoro renvoie une chaîne ou un objet {id/name}."""
    if isinstance(item, dict):
        return str(item.get("id") or item.get("name") or item.get("voice") or "").strip()
    return str(item).strip()


def _normalize_wav(b: bytes) -> bytes:
    """Rend lisible par les navigateurs un WAV « streaming » à la Kokoro :
    1) corrige les tailles bidon (RIFF/data = 0xFFFFFFFF) pour pouvoir le parser ;
    2) RÉÉMET un WAV CANONIQUE (uniquement `fmt `+`data`) — ça supprime le chunk `LIST/INFO`
       (métadonnées libav) que des décodeurs navigateur (Edge/Firefox) refusent.
    No-op si ce n'est pas un WAV."""
    import struct
    if len(b) < 44 or b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        return b
    # 1) Réparation des tailles d'en-tête.
    buf = bytearray(b)
    total = len(buf)
    struct.pack_into("<I", buf, 4, total - 8)          # taille du chunk RIFF
    i = 12
    while i + 8 <= total:
        cid = bytes(buf[i:i + 4])
        size = struct.unpack_from("<I", buf, i + 4)[0]
        if cid == b"data":
            real = total - (i + 8)
            if size != real:                            # taille data réelle
                struct.pack_into("<I", buf, i + 4, real)
            break
        if size == 0xFFFFFFFF or i + 8 + size > total:  # taille bidon sur un autre chunk → stop
            break
        i += 8 + size + (size & 1)                       # word-aligned
    fixed = bytes(buf)
    # 2) Réémission canonique (fmt + data uniquement) via le module wave.
    try:
        import io
        import wave
        with wave.open(io.BytesIO(fixed), "rb") as r:
            p = r.getparams()
            frames = r.readframes(r.getnframes())
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(p.nchannels)
            w.setsampwidth(p.sampwidth)
            w.setframerate(p.framerate)
            w.writeframes(frames)
        return out.getvalue()
    except Exception:
        return fixed   # au pire, le WAV à tailles corrigées (mieux que rien)


def _audio_media_type(b: bytes):
    """Devine le Content-Type d'un buffer audio par ses octets magiques. Renvoie None si ce
    n'est manifestement PAS de l'audio (erreur JSON/HTML renvoyée en 200 par le serveur)."""
    if not b or len(b) < 4:
        return None
    if b[:4] == b"RIFF":
        return "audio/wav"
    if b[:4] == b"OggS":
        return "audio/ogg"
    if b[:4] == b"fLaC":
        return "audio/flac"
    if b[:3] == b"ID3" or b[0] == 0xFF and (b[1] & 0xE0) == 0xE0:
        return "audio/mpeg"
    head = b[:64].lstrip()
    if head[:1] in (b"{", b"[", b"<"):   # JSON / XML / HTML → pas de l'audio
        return None
    return "audio/wav"   # défaut prudent (PCM brut éventuel)


def _clean_voice(v) -> str:
    """Assainit une valeur de voix : ignore une valeur CORROMPUE héritée (un dict str()-isé
    enregistré par erreur, ex. « {'id': 'af_bella', 'name': 'af_bella'} ») → renvoie "" pour
    forcer le repli sur une vraie voix."""
    s = str(v or "").strip()
    if not s:
        return ""
    if s[:1] in ("{", "[") or "'id'" in s or '"id"' in s or "'name'" in s:
        return ""
    return s


@router.get("/api/voice/voices")
async def list_voices() -> Dict[str, Any]:
    """Liste DYNAMIQUE des voix Kokoro (ID propre + libellé lisible) pour le menu déroulant."""
    url = _kokoro_voices_url()
    if not url:
        return {"voices": [], "error": "VOICE_TTS_HTTP_URL non configuré."}
    try:
        import requests
        r = await asyncio.to_thread(lambda: requests.get(url, timeout=8))
        if r.status_code != 200:
            return {"voices": [], "error": f"Kokoro a répondu {r.status_code}."}
        data = r.json()
        # Kokoro-FastAPI : {"voices": [...]} (chaînes OU objets) ; on reste tolérant.
        voices = data.get("voices") if isinstance(data, dict) else data
        if isinstance(voices, dict):
            voices = list(voices.keys())
        out = []
        for it in (voices or []):
            vid = _extract_voice_id(it)
            if vid:
                out.append({"id": vid, "label": _voice_label(vid)})
        return {"voices": out}
    except Exception as e:
        return {"voices": [], "error": f"Kokoro injoignable : {e}"}


class VoiceTtsSelect(BaseModel):
    voice: str = ""
    http_url: str | None = None        # None = ne pas toucher ce réglage
    emotion_markers: bool | None = None
    speed: str | None = None


@router.post("/api/config/voice-tts")
async def set_voice_tts(req: VoiceTtsSelect) -> Dict[str, Any]:
    """Règle le TTS (voix + URL serveur + émotion par marqueur + vitesse), partagé CHAT +
    SATELLITES. Les champs non fournis (None) sont laissés inchangés. Persisté en .env + à chaud."""
    def _apply(key, val):
        from setup_wizard import set_env_var
        set_env_var(key, val)
        os.environ[key] = val
    try:
        _apply("VOICE_TTS_VOICE", _clean_voice(req.voice))
        if req.http_url is not None:
            _apply("VOICE_TTS_HTTP_URL", req.http_url.strip())
        if req.emotion_markers is not None:
            _apply("VOICE_TTS_EMOTION_MARKERS", "true" if req.emotion_markers else "false")
        if req.speed is not None:
            try:
                sp = max(0.5, min(2.0, float(str(req.speed).replace(",", "."))))
            except Exception:
                sp = 1.0
            _apply("VOICE_TTS_SPEED", str(sp))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Écriture .env impossible : {e}")
    return {"status": "success", "voice": (req.voice or "").strip()}


class TtsSpeakRequest(BaseModel):
    text: str
    voice: str = ""        # override ponctuel (sinon VOICE_TTS_VOICE)


@router.post("/api/voice/tts")
async def voice_tts(req: TtsSpeakRequest):
    """Synthétise du texte avec le MÊME moteur que les satellites (Kokoro via voice/tts.py) et
    renvoie un WAV → le chat le joue (au lieu de la voix robotique du navigateur)."""
    from fastapi.responses import Response
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texte vide.")
    text = text[:2000]  # garde-fou longueur
    prev = os.environ.get("VOICE_TTS_VOICE")
    prev_fmt = os.environ.get("VOICE_TTS_FORMAT")
    # Aperçu/chat NAVIGATEUR : on demande du MP3 (lu par TOUS les navigateurs, aucun souci
    # d'en-tête WAV). N'affecte PAS les satellites (autre chemin, voice/assistant.py).
    os.environ["VOICE_TTS_FORMAT"] = (os.getenv("BROWSER_TTS_FORMAT", "mp3") or "mp3").strip()
    try:
        from voice.config import voice_config
        from voice.tts import TTS, TTSUnavailable
        chosen = _clean_voice(req.voice) or _clean_voice(os.getenv("VOICE_TTS_VOICE", ""))
        # Aucune voix définie → on prend AUTOMATIQUEMENT la 1ʳᵉ voix Kokoro dispo (sinon l'ancien
        # défaut « alloy » — inconnu de Kokoro — faisait échouer la synthèse → voix robotique).
        if not chosen:
            try:
                vres = await list_voices()
                vlist = vres.get("voices") or []
                if vlist:
                    chosen = vlist[0]["id"]
            except Exception:
                pass
        if chosen:
            os.environ["VOICE_TTS_VOICE"] = chosen
        c = voice_config()
        tts = TTS(c["tts_engine"], c["piper_model"], c["piper_bin"])
        wav = await asyncio.to_thread(tts.synth_wav_bytes, text)
        if not wav:
            raise HTTPException(status_code=502, detail="Synthèse vide.")
        # Le serveur TTS peut renvoyer du WAV, du MP3 ou de l'OGG (selon sa config). On
        # DÉTECTE le vrai format (octets magiques) pour poser le bon Content-Type — sinon le
        # navigateur reçoit du mp3 étiqueté « audio/wav » et refuse (NotSupportedError).
        media = _audio_media_type(wav)
        if media is None:
            # Pas de l'audio (probablement une erreur JSON/HTML renvoyée en 200).
            raise HTTPException(status_code=502,
                                detail=f"Réponse du serveur TTS non audio : {wav[:160]!r}")
        if media == "audio/wav":
            wav = _normalize_wav(wav)   # répare l'en-tête « streaming » (taille bidon)
        return Response(content=wav, media_type=media)
    except HTTPException:
        raise
    except Exception as e:
        # 502 → le front retombe proprement sur la voix du navigateur.
        raise HTTPException(status_code=502, detail=f"TTS indisponible : {e}")
    finally:
        # Restaure l'état d'origine (on a pu surcharger VOICE_TTS_VOICE/FORMAT pour ce seul appel).
        if prev is None:
            os.environ.pop("VOICE_TTS_VOICE", None)
        else:
            os.environ["VOICE_TTS_VOICE"] = prev
        if prev_fmt is None:
            os.environ.pop("VOICE_TTS_FORMAT", None)
        else:
            os.environ["VOICE_TTS_FORMAT"] = prev_fmt
