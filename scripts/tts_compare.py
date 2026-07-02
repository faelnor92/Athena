#!/usr/bin/env python3
"""Test comparatif de qualité vocale FR : Fish-Speech (S1-mini, local) vs Qwen3-TTS (Alexandria).

Génère UN wav par segment du texte de test via le serveur Fish-Speech déjà documenté
(docs/fish-speech-server.md), en réutilisant EXACTEMENT le pipeline de prod
(voice/tts.py : mêmes marqueurs d'émotion, même vitesse/gain) pour que le test reflète
ce qu'Athena produirait vraiment.

Qwen3-TTS/Alexandria n'a pas d'API texte+voix simple (cf. docs/tts-quality-comparison.md,
section « Protocole Qwen3-TTS ») : à générer à la main via l'UI Alexandria avec le MÊME texte.

Prérequis : le shim Fish-Speech doit tourner et VOICE_TTS_HTTP_URL/VOICE_TTS_VOICE être
définis dans .env (cf. docs/fish-speech-server.md).

    .venv/bin/python scripts/tts_compare.py                  # génère scratch/tts_compare/fish/*.wav
    .venv/bin/python scripts/tts_compare.py --out scratch/x  # dossier de sortie custom
"""
import os
import sys
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for _cand in (".venv/bin/python", "venv/bin/python", ".venv/bin/python3", "venv/bin/python3"):
    _vp = os.path.join(ROOT, _cand)
    if os.path.exists(_vp) and os.path.realpath(_vp) != os.path.realpath(sys.executable):
        os.execv(_vp, [_vp, os.path.abspath(__file__)] + sys.argv[1:])
_env = os.path.join(ROOT, ".env")
if os.path.exists(_env):
    for _l in open(_env, encoding="utf-8"):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import argparse

# Même texte que docs/tts-quality-comparison.md (source unique : ne modifier qu'à un endroit).
# Chaque segment couvre un registre différent : liaisons, chiffres, émotion, chuchoté...
SEGMENTS = [
    ("neutral", "La pluie tombait sur les toits de Strasbourg depuis le matin, "
                "et Élise attendait, assise près de la fenêtre, les mains posées sur ses genoux."),
    ("calm", "Elle savait que tout finirait par s'arranger, comme chaque automne "
             "depuis vingt et un ans."),
    ("serious", "Il faut que tu m'écoutes attentivement, dit-il en refermant "
                "la porte derrière lui."),
    ("whisper", "Personne ne doit savoir ce que je vais te confier maintenant."),
    ("sad", "Sa mère n'était plus revenue depuis ce jour-là, et le silence "
            "pesait sur toute la maison."),
    ("angry", "Comment as-tu pu me cacher une chose pareille pendant toutes ces années ?"),
    ("empathetic", "Je comprends ta colère, mais je n'avais pas le choix, tu dois me croire."),
    ("excited", "Et soudain, la porte s'ouvrit : c'était elle, enfin, après tant "
                "d'années d'absence !"),
    ("cheerful", "Les enfants se mirent à rire aux éclats, heureux de retrouver "
                 "leur grand-mère."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="scratch/tts_compare/fish")
    args = ap.parse_args()

    from voice.tts import TTS, TTSUnavailable

    out_dir = os.path.join(ROOT, args.out)
    os.makedirs(out_dir, exist_ok=True)

    tts = TTS(engine="http")
    ok, failed = 0, []
    for i, (emotion, text) in enumerate(SEGMENTS, start=1):
        dest = os.path.join(out_dir, f"{i:02d}_{emotion}.wav")
        try:
            tmp = tts._http_to_wav(text, emotion)
            shutil.move(tmp, dest)
            print(f"[OK]   {dest}")
            ok += 1
        except TTSUnavailable as e:
            print(f"[FAIL] segment {i} ({emotion}) : {e}")
            failed.append(i)

    print(f"\n{ok}/{len(SEGMENTS)} segments générés dans {out_dir}")
    if failed:
        print(f"Échecs : {failed} — vérifie VOICE_TTS_HTTP_URL et que le shim Fish-Speech tourne "
              f"(docs/fish-speech-server.md).")
        sys.exit(1)
    print("\nÉtape suivante : génère le MÊME texte avec Qwen3-TTS/Alexandria "
          "(cf. docs/tts-quality-comparison.md) puis compare à l'oreille avec la grille de notation.")


if __name__ == "__main__":
    main()
