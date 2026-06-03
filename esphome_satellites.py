#!/usr/bin/env python3
"""Point d'entrée : backend vocal ESPHome (satellites ESP32-S3 → Athena, sans HA).

Prérequis :
  - le serveur Athena tourne (python3 server.py) ;
  - pip install -r requirements-voice.txt (faster-whisper, aioesphomeapi…) + Piper ;
  - satellites.json (cf. .example) ;
  - ESPHome flashé avec le composant voice_assistant (cf. docs/esphome-satellite.yaml).

Usage : python3 esphome_satellites.py
"""
import asyncio

from dotenv import load_dotenv


def main():
    load_dotenv()
    from voice.esphome_satellites import run
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n👋 Arrêt des satellites.")


if __name__ == "__main__":
    main()
