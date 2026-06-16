# Serveur TTS expressif XTTS (machine dédiée, ex. portable RTX 3050)

But : une voix **bien plus expressive/naturelle** que Kokoro, avec **clonage de voix**, branchée sur
Athena **sans modifier le code** — Athena pointe simplement `VOICE_TTS_HTTP_URL` vers ce serveur.

La RTX 3050 (≥4 Go VRAM) fait tourner **XTTS v2** proche du temps réel. Sur CPU, XTTS est trop lent
→ on l'installe sur la machine GPU.

## 1. Choisir un serveur XTTS *compatible OpenAI*

Le plus simple = un serveur qui expose `POST /v1/audio/speech` (même API qu'Athena attend déjà) :
**openedai-speech** (OpenAI-compatible, supporte XTTS/Coqui + clonage). Les voix sont mappées à des
échantillons `.wav` de référence (le clonage).

## 2. docker-compose (sur le portable GPU)

Prérequis : Docker + **NVIDIA Container Toolkit** (`nvidia-smi` doit marcher dans un conteneur).

```yaml
# docker-compose.yml — sur le portable RTX 3050
services:
  xtts:
    image: ghcr.io/matatonic/openedai-speech:latest
    container_name: xtts
    restart: unless-stopped
    ports:
      - "8001:8000"            # API exposée sur le port 8001 du portable
    volumes:
      - ./voices:/app/voices   # tes .wav de référence (clonage)
      - ./config:/app/config
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Lancer : `docker compose up -d` puis vérifier : `curl http://localhost:8001/v1/audio/voices`.

## 3. Côté Athena (.env)

```
VOICE_TTS_HTTP_URL=http://<IP_DU_PORTABLE>:8001/v1/audio/speech
VOICE_TTS_VOICE=<nom_de_voix>          # à choisir dans le menu déroulant (Réglages → Satellites)
VOICE_TTS_FORMAT=wav
```
Redémarre Athena. Le mapping émotion→vitesse/volume continue de s'appliquer ; la voix de base est
celle d'XTTS (bien plus expressive).

## 4. Sécuriser le portable (24/7, écran cassé, headless)

**Réseau — jamais exposé à Internet, accès limité à Athena :**
```bash
sudo ufw default deny incoming
sudo ufw allow from <IP_ATHENA> to any port 8001   # seul Athena joint le TTS
sudo ufw allow from 192.168.1.0/24 to any port 22  # SSH admin (LAN)
sudo ufw enable
```
Aucun port-forward sur la box pour le 8001.

**Permanence — survit aux reboots et au capot fermé :**
```bash
# Ignorer la fermeture du capot (écran cassé / headless)
sudo sed -i 's/^#\?HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
sudo sed -i 's/^#\?HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
sudo systemctl restart systemd-logind
# Pas de mise en veille
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
# Boot en mode serveur (pas d'environnement graphique requis)
sudo systemctl set-default multi-user.target
```
Docker `restart: unless-stopped` relance le conteneur au boot. Pour les MAJ sécurité auto :
`sudo apt-get install -y unattended-upgrades`.

## 5. Clonage de voix (le vrai gain expressif)

Dépose un échantillon propre (~10-20 s, voix claire, mono) dans `./voices/mavoix.wav`, déclare-le
dans la config openedai-speech, et il apparaîtra dans le menu déroulant d'Athena. La voix clonée
est nettement plus naturelle/émotionnelle que les voix synthétiques génériques.

## Notes
- Latence : sur RTX 3050, XTTS ≈ temps réel par phrase ; le streaming phrase-par-phrase d'Athena
  masque le reste.
- Repli : si le serveur XTTS est éteint, Athena retombe automatiquement sur la voix du navigateur
  (chat) — donc pas de blocage.
- L'« émotion » fine reste limitée (vitesse/volume côté Athena) ; XTTS améliore surtout le
  NATUREL de la voix de base + le clonage.
