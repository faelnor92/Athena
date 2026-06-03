"""Pipeline vocal local pour Athena (STT faster-whisper, TTS Piper, wake word).

Tous les imports lourds (faster_whisper, piper, sounddevice, openwakeword) sont
PARESSEUX : importer ce package ne nécessite aucune de ces dépendances. Elles ne
sont chargées qu'à l'utilisation effective, avec un message clair si absentes.

Dépendances : voir requirements-voice.txt.

⚠️ Ce module n'a pas pu être testé sur la machine de développement (pas de
micro/haut-parleur). Le code est structuré pour être robuste, mais à valider sur
le matériel cible.
"""
