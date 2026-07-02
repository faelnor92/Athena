# Test comparatif qualité vocale FR : Fish-Speech (S1-mini) vs Qwen3-TTS (Alexandria)

Objectif : trancher à l'oreille (pas au marketing) si Fish-Speech S1-mini (6 Go, déjà
documenté dans `docs/fish-speech-server.md`) suffit pour un niveau « roman en librairie »,
ou s'il faut viser Qwen3-TTS + LoRA persona (via Alexandria, cf. `roadmap-tracks`/mémoire).

Aucune des deux docs officielles ne fournit de comparaison indépendante : les benchmarks
Fish-Speech (WER, Audio Turing Test) portent sur **S2-Pro (4B)**, pas sur le S1-mini réellement
utilisable sur la RTX 3050 6 Go. Qwen3-TTS annonce le français en langue « tier 1 » mais sans
benchmark. D'où ce test maison.

## Le texte de test

Même texte des deux côtés (source unique : `scripts/tts_compare.py::SEGMENTS`). Il couvre :
- narration neutre + calme
- registre sérieux puis **chuchoté**
- tristesse, colère, empathie
- excitation puis registre enjoué
- pièges FR : liaisons (« vingt et un ans », « les mains »), un prénom (Élise),
  un toponyme (Strasbourg), une négation avec élision

```
1. [neutral]    La pluie tombait sur les toits de Strasbourg depuis le matin, et Élise
                attendait, assise près de la fenêtre, les mains posées sur ses genoux.
2. [calm]       Elle savait que tout finirait par s'arranger, comme chaque automne
                depuis vingt et un ans.
3. [serious]    Il faut que tu m'écoutes attentivement, dit-il en refermant la porte
                derrière lui.
4. [whisper]    Personne ne doit savoir ce que je vais te confier maintenant.
5. [sad]        Sa mère n'était plus revenue depuis ce jour-là, et le silence pesait
                sur toute la maison.
6. [angry]      Comment as-tu pu me cacher une chose pareille pendant toutes ces années ?
7. [empathetic] Je comprends ta colère, mais je n'avais pas le choix, tu dois me croire.
8. [excited]    Et soudain, la porte s'ouvrit : c'était elle, enfin, après tant d'années
                d'absence !
9. [cheerful]   Les enfants se mirent à rire aux éclats, heureux de retrouver leur
                grand-mère.
```

## Protocole Fish-Speech (local, RTX 3050)

1. Déployer le shim + Fish-Speech si pas déjà fait (`docs/fish-speech-server.md`).
2. Vérifier `.env` : `VOICE_TTS_ENGINE=http`, `VOICE_TTS_HTTP_URL`, `VOICE_TTS_VOICE`,
   `VOICE_TTS_EMOTION_MARKERS=true`.
3. `.venv/bin/python scripts/tts_compare.py` → génère `scratch/tts_compare/fish/01_neutral.wav`
   … `09_cheerful.wav` (réutilise le pipeline émotion→vitesse/gain/marqueur de `voice/tts.py`,
   donc représentatif de ce qu'Athena produirait vraiment en prod).

## Protocole Qwen3-TTS (Alexandria)

Alexandria n'a pas d'API texte+voix simple (juste `/api/chunks/{id}/generate` sur un pipeline
de chunks annotés) — le plus simple et le plus fidèle à l'usage réel est de passer par l'UI :

1. `git clone https://github.com/Finrandojin/alexandria-audiobook.git && docker compose up --build`
   (ou Google Colab si pas de GPU 8 Go+ dispo) → UI sur `http://localhost:4200`.
2. **Setup** : configurer l'endpoint LLM (peut pointer vers le même endpoint custom
   `conversation-test.ia.unistra.fr` qu'Athena, cf. mémoire `modeles-endpoint`) + moteur TTS Qwen3.
3. **Script** : coller le texte des 9 segments ci-dessus comme un seul « chapitre » (un fichier
   `.txt`), lancer l'annotation. Corriger si le LLM a mal découpé les segments/émotions —
   objectif : UN SEUL locuteur/persona sur tout le texte (on ne teste pas le multi-voix ici).
4. **Voices** : assigner une des 9 voix prédéfinies (pas de clonage ni de LoRA pour ce
   premier test — on compare les moteurs de base, pas l'identité vocale).
5. **Editor** : vérifier que l'instruction d'émotion par ligne correspond au tag `[emotion]`
   du texte source (neutral/calm/serious/whisper/sad/angry/empathetic/excited/cheerful) ;
   corriger l'instruction si le LLM l'a mal devinée.
6. **Result** : exporter en WAV/MP3 individuels par ligne → ranger dans
   `scratch/tts_compare/qwen/01_neutral.wav` … `09_cheerful.wav` (même nommage que côté Fish
   pour comparer facilement).

## Grille de notation (écoute à l'aveugle)

Renommer les fichiers en `A_01.wav`/`B_01.wav` (sans savoir quel moteur est A ou B) avant
d'écouter, pour éviter le biais de confirmation. Noter chaque segment de 1 (mauvais) à 5
(irréprochable) :

| # | Segment | Naturel/prosodie | Liaisons & prononciation FR | Émotion rendue | Artefacts/glitches |
|---|---------|:---:|:---:|:---:|:---:|
| 1 | neutral | | | | |
| 2 | calm | | | | |
| 3 | serious | | | | |
| 4 | whisper | | | | |
| 5 | sad | | | | |
| 6 | angry | | | | |
| 7 | empathetic | | | | |
| 8 | excited | | | | |
| 9 | cheerful | | | | |

Colonnes :
- **Naturel/prosodie** : ça sonne humain ou robotique/monotone ?
- **Liaisons & prononciation FR** : « vingt_et_un », « les_mains », « Strasbourg », « Élise »
  correctement enchaînés/prononcés (pas de glotal stop ni de liaison manquante/en trop) ?
- **Émotion rendue** : on identifierait l'émotion cible sans lire le tag ?
- **Artefacts** : coupures, saturation, bruit de fond, débit qui accélère/ralentit bizarrement.

**Verdict** : faire la moyenne par moteur. Si l'écart est net (>0.5 pt en moyenne) en faveur
de Qwen3-TTS, ça confirme que le coût du pipeline LoRA (cf. mémoire `roadmap-tracks`) est
justifié pour un rendu « librairie ». Si c'est serré ou en faveur de Fish-Speech, rester sur
l'infra déjà déployée (`docs/fish-speech-server.md`) et ne pas construire le pipeline LoRA.

## Notes

- Ce test compare les MOTEURS de base (voix prédéfinie), pas le clonage/LoRA — c'est
  volontaire : isoler la variable "qualité brute du moteur" avant d'ajouter la variable
  "fidélité de l'identité vocale par personnage".
- Licences : Qwen3-TTS = Apache 2.0 (usage libre) ; Fish-Speech/OpenAudio = CC-BY-NC
  (déjà noté dans `docs/fish-speech-server.md` — OK pour un usage perso/homelab, pas pour
  vendre les audiobooks générés).
