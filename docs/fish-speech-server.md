# Serveur TTS émotionnel Fish-Speech / OpenAudio S1 (français + émotion pilotée + clonage)

Objectif : voix **française**, **émotion par marqueur** (`(happy)`, `(sad)`…), **clonage**, sur la
machine GPU dédiée (portable RTX 3050 6 Go). Athena s'y branche via `VOICE_TTS_HTTP_URL`.

Athena envoie déjà l'émotion DANS le texte sous forme de marqueur (`VOICE_TTS_EMOTION_MARKERS=true`
→ « (sad) ton texte »). Fish-Speech rend l'émotion correspondante. Un petit **shim** rend
Fish-Speech compatible OpenAI (`/v1/audio/speech` + `/v1/audio/voices`) pour brancher Athena sans
rien changer d'autre.

```
Athena ──(/v1/audio/speech, OpenAI)──▶ shim ──(/v1/tts, API Fish-Speech)──▶ Fish-Speech (GPU)
```

## 1. Arborescence sur le portable
```
fishtts/
├── docker-compose.yml
├── shim/
│   ├── Dockerfile
│   └── app.py
└── references/            # voix clonées : un sous-dossier par voix
    └── athena/
        ├── ref.wav        # 10–20 s, voix claire, mono
        └── ref.lab        # la TRANSCRIPTION exacte de ref.wav
```

## 2. docker-compose.yml
```yaml
services:
  fish-speech:
    image: fishaudio/fish-speech:latest
    container_name: fish-speech
    restart: unless-stopped
    command: >
      python tools/api_server.py --listen 0.0.0.0:8080
      --llama-checkpoint-path checkpoints/openaudio-s1-mini
      --decoder-checkpoint-path checkpoints/openaudio-s1-mini/codec.pth
    volumes:
      - ./references:/opt/fish-speech/references
      - hf-cache:/root/.cache/huggingface
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]

  tts-shim:
    build: ./shim
    container_name: tts-shim
    restart: unless-stopped
    environment:
      FISH_URL: "http://fish-speech:8080"
      FISH_USE_MSGPACK: "true"      # mettre false si ton API Fish accepte du JSON
      REFERENCES_DIR: "/references"
      DEFAULT_LANG: "fr"
    volumes:
      - ./references:/references:ro
    ports:
      - "8001:8001"                 # ← c'est CE port qu'Athena appelle

volumes:
  hf-cache:
```
> Le nom exact des checkpoints (`openaudio-s1-mini`) et la commande peuvent varier selon la version
> de l'image Fish-Speech — vérifie le README de l'image. La S1-mini tient sur 6 Go.

## 3. shim/Dockerfile
```dockerfile
FROM python:3.11-slim
RUN pip install --no-cache-dir fastapi uvicorn requests ormsgpack
COPY app.py /app/app.py
WORKDIR /app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
```

## 4. shim/app.py  (pont OpenAI ↔ Fish-Speech)
```python
import os, glob
import requests, ormsgpack
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse

FISH = os.getenv("FISH_URL", "http://fish-speech:8080").rstrip("/")
REFDIR = os.getenv("REFERENCES_DIR", "/references")
LANG = os.getenv("DEFAULT_LANG", "fr")
USE_MSGPACK = os.getenv("FISH_USE_MSGPACK", "true").lower() in ("true", "1", "yes")
app = FastAPI()

def _voices():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(REFDIR, "*")) if os.path.isdir(p))

@app.get("/v1/audio/voices")
def voices():
    return {"voices": _voices()}

@app.post("/v1/audio/speech")
async def speech(req: Request):
    body = await req.json()
    text = body.get("input") or body.get("text") or ""
    voice = (body.get("voice") or "").strip()
    fmt = body.get("response_format") or body.get("format") or "wav"
    # Le marqueur d'émotion « (sad) … » est DÉJÀ dans `text` (injecté par Athena) → rien à faire.
    payload = {"text": text, "format": fmt, "reference_id": voice or None,
               "chunk_length": 200, "normalize": True, "streaming": False}
    headers = {}
    if USE_MSGPACK:
        data = ormsgpack.packb(payload); headers["Content-Type"] = "application/msgpack"
        r = requests.post(f"{FISH}/v1/tts", data=data, headers=headers, timeout=120)
    else:
        r = requests.post(f"{FISH}/v1/tts", json=payload, timeout=120)
    if r.status_code != 200:
        return JSONResponse({"error": r.text[:300]}, status_code=502)
    media = {"wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac"}.get(fmt, "audio/wav")
    return Response(content=r.content, media_type=media)
```

## 5. Côté Athena (.env)
```
VOICE_TTS_ENGINE=http
VOICE_TTS_HTTP_URL=http://<IP_DU_PORTABLE>:8001/v1/audio/speech
VOICE_TTS_EMOTION_MARKERS=true     # ← active la traduction [emotion:X] → (happy)/(sad)/…
VOICE_TTS_VOICE=athena             # = nom du dossier dans references/ (choisi dans le menu déroulant)
VOICE_TTS_FORMAT=wav
```
Redémarre Athena. Le menu déroulant (Réglages → Satellites) listera les voix via le shim
(`/v1/audio/voices`). L'émotion des agents (`[emotion: …]`) est rendue par Fish-Speech.

## 6. Clonage d'une voix
1. `references/<nom>/ref.wav` (10–20 s, propre, mono) + `references/<nom>/ref.lab` (transcription).
2. `docker compose restart` → la voix `<nom>` apparaît dans le menu déroulant d'Athena.

## 7. Sécuriser le portable 24/7 (écran cassé, headless)
```bash
# Pare-feu : seul Athena joint le shim ; pas d'expo Internet
sudo ufw default deny incoming
sudo ufw allow from <IP_ATHENA> to any port 8001
sudo ufw allow from 192.168.1.0/24 to any port 22
sudo ufw enable
# Capot ignoré + pas de veille + boot serveur
sudo sed -i 's/^#\?HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
sudo systemctl restart systemd-logind
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
sudo systemctl set-default multi-user.target
```
Docker `restart: unless-stopped` relance tout au boot. `nvidia-smi` doit marcher dans un conteneur
(NVIDIA Container Toolkit installé).

## Notes
- Émotions mappées par Athena : enjoué→(happy), excité→(excited), triste→(sad), calme→(calm),
  sérieux→(serious), empathique→(gentle), fâché→(angry), chuchoté→(whispering). Modifiable dans
  `voice/tts.py` (_EMOTION_MARKER).
- Repli : shim/Fish éteint → Athena retombe sur la voix du navigateur (chat). Rien ne bloque.
- `FISH_USE_MSGPACK` : les versions récentes de l'API Fish attendent du msgpack ; si la tienne
  accepte du JSON sur `/v1/tts`, mets-le à `false`.
- Licence Fish-Speech : non-commerciale (CC-BY-NC) — OK pour usage perso/homelab.
