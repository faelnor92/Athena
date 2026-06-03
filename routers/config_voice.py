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
            activation=req.activation, custom_yaml=req.custom_yaml,
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
