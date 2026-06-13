# Entraîner un wake word openWakeWord « athena » (→ `athena.onnx`)

But : obtenir un modèle de détection **efficace et always-on** du mot « athena »,
pour `VOICE_WAKE_ENGINE=openwakeword` + `VOICE_WAKE_WORD=athena` (alternative au mode
`stt` par transcription, plus léger pour les satellites multi-flux).

> ⚠️ **C'est un VRAI entraînement ML** : données synthétiques (Piper) + bruit + un DNN.
> Il faut un **GPU** (Colab gratuit suffit) et ~1 h. **Pas sur le R430 (sans GPU)** : très long.

---

## Option A — Colab officiel (le plus simple, c'est la voie testée)
openWakeWord fournit un notebook qui fait TOUT, tu n'as qu'à donner le mot.
1. Ouvre `notebooks/automatic_model_training.ipynb` du dépôt **dscripka/openWakeWord**
   dans **Google Colab** (Runtime → GPU).
2. Dans la cellule de config, mets **`target_word = "athena"`** (et `model_name = "athena"`).
3. Exécute toutes les cellules → il génère les « athena » (Piper), télécharge les
   négatifs/bruits, entraîne, et te sort **`athena.onnx`** (+ `.tflite`).
4. Télécharge `athena.onnx`.

## Option B — Script local sur machine GPU
Reproduit le même pipeline en ligne de commande :
```bash
cd tools/train_wakeword
bash train_athena_wakeword.sh athena.yaml
# → ./athena_model/athena.onnx
```
Le script : clone openWakeWord + piper-sample-generator, installe les deps, télécharge
la voix Piper + les features négatives, puis lance les 3 étapes
(`--generate_clips` → `--augment_clips` → `--train_model`).
Édite **`athena.yaml`** pour ajuster volumes/steps. Les jeux de **bruit/RIR**
(audioset/fma/mit_rirs) sont volumineux : récupère-les via la cellule data du notebook
officiel si le script ne les a pas (voir « Données » plus bas).

---

## Déployer le modèle dans Athena
1. Copie `athena.onnx` dans le dossier modèles d'openWakeWord du venv :
   ```bash
   cp athena.onnx "$(.venv/bin/python -c 'import os,openwakeword; print(os.path.join(os.path.dirname(openwakeword.__file__),"resources","models"))')"/
   ```
   (ou pointe `VOICE_WAKE_MODEL_PATH` vers ton `.onnx` si tu préfères un chemin custom —
   sinon openWakeWord charge tous les `.onnx` du dossier resources/models.)
2. Dans `.env` :
   ```
   VOICE_WAKE_ENGINE=openwakeword
   VOICE_WAKE_WORD=athena
   OWW_INFERENCE_FRAMEWORK=onnx
   ```
3. Redémarre l'assistant vocal. Dis « Athena ».

> Astuce : teste la détection avant de déployer —
> `Model(wakeword_models=["athena.onnx"], inference_framework="onnx")` puis
> `model.predict(frame_int16)` doit faire monter le score quand tu dis « Athena ».

---

## Données (bruit / réverbération) — si tu pars du script local
Le contraste a besoin de :
- **Négatifs massifs** : `openwakeword_features_ACAV100M_2000_hrs_16bit.npy` +
  `validation_set_features.npy` (téléchargés auto depuis HuggingFace par le script).
- **Bruit de fond 16 kHz** (AudioSet/FMA) et **RIRs** (MIT) : volumineux → la cellule
  « training data collection » du notebook officiel les prépare ; copie-les ensuite dans
  `data/audioset_16k`, `data/fma_16k`, `data/mit_rirs`.

## Réglages utiles (`athena.yaml`)
- `n_samples` : + de positifs = + robuste (et + long). 30000 est un bon départ.
- `steps` : itérations. `target_accuracy`/`target_recall` : seuils d'early-stop.
- `target_phrase` : on entraîne « athena » ET « hey athena » pour les deux usages.

---

### Honnêteté
Ce script suit fidèlement le pipeline officiel mais **n'a pas été exécuté ici** (pas de
GPU/datasets dans l'environnement de dev). Si une URL ou un flag a changé dans ta version
d'openWakeWord, le **notebook officiel** (Option A) reste la référence à jour.
