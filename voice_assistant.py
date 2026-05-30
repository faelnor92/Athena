#!/usr/bin/env python3
"""Point d'entrée de l'assistant vocal local Jarvis.

Prérequis :
  - le serveur Jarvis tourne (python3 server.py) ;
  - dépendances vocales installées : pip install -r requirements-voice.txt ;
  - pour Piper : binaire `piper` + un modèle .onnx (VOICE_PIPER_MODEL) ;
  - configuration via .env (variables VOICE_*).

Usage : python3 voice_assistant.py
"""
from dotenv import load_dotenv


def main():
    load_dotenv()
    from voice.assistant import VoiceAssistant
    VoiceAssistant().run()


if __name__ == "__main__":
    main()
