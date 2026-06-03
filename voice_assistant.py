#!/usr/bin/env python3
"""Point d'entrée de l'assistant vocal local Athena.

Prérequis :
  - le serveur Athena tourne (python3 server.py) ;
  - dépendances vocales installées : pip install -r requirements-voice.txt ;
  - pour Piper : binaire `piper` + un modèle .onnx (VOICE_PIPER_MODEL) ;
  - configuration via .env (variables VOICE_*).

Usage :
  python3 voice_assistant.py                     # lance l'assistant vocal
  python3 voice_assistant.py enroll <nom> <a.wav>  # enrôle un locuteur
"""
import sys

from dotenv import load_dotenv


def main():
    load_dotenv()
    # Sous-commande d'enrôlement de locuteur.
    if len(sys.argv) >= 2 and sys.argv[1] == "enroll":
        if len(sys.argv) < 4:
            print("Usage : python3 voice_assistant.py enroll <nom> <échantillon.wav>")
            sys.exit(1)
        from voice.speaker_id import enroll
        print(enroll(sys.argv[2], sys.argv[3]))
        return
    from voice.assistant import VoiceAssistant
    VoiceAssistant().run()


if __name__ == "__main__":
    main()
