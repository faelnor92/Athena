#!/usr/bin/env bash
# =========================================================================
# Entraînement d'un modèle openWakeWord « athena » → athena.onnx
# =========================================================================
# Suit le pipeline OFFICIEL openWakeWord (dscripka/openWakeWord,
# notebooks/automatic_model_training.ipynb) : positifs synthétiques (Piper)
# + bruit/réverbération + négatifs massifs (features pré-calculées) → DNN.
#
# ⚠️ À LANCER SUR UNE MACHINE GPU (ou Google Colab). Sur CPU c'est très long.
#    NON testé par l'auteur (pas de GPU dispo) : si une URL/CLI a changé dans
#    ta version d'openWakeWord, compare avec le notebook officiel à jour.
#
# Sortie : ./athena_model/athena.onnx  →  à déposer dans openWakeWord (voir README).
# =========================================================================
set -u

CFG="${1:-$(dirname "$0")/athena.yaml}"
echo "📋 Config : $CFG"
mkdir -p data athena_model

# --- 0. Vérif GPU (informatif) -------------------------------------------
python -c "import torch; print('CUDA dispo :', torch.cuda.is_available())" 2>/dev/null \
  || echo "⚠ PyTorch/CUDA non détecté — l'entraînement sera LENT sur CPU."

# --- 1. Dépendances -------------------------------------------------------
echo "📦 Installation des dépendances d'entraînement..."
pip install -q "openwakeword[training]" 2>/dev/null || pip install -q openwakeword
pip install -q torch torchaudio numpy scipy scikit-learn onnx onnxruntime \
               webrtcvad tqdm datasets soundfile pronouncing acoustics mutagen torchinfo speechbrain

# --- 2. openWakeWord (source) + piper-sample-generator -------------------
[ -d openWakeWord ] || git clone https://github.com/dscripka/openWakeWord.git
[ -d piper-sample-generator ] || git clone https://github.com/rhasspy/piper-sample-generator.git

# Modèle de voix Piper multi-voix (synthétise « athena » en de nombreuses voix)
mkdir -p piper-sample-generator/models
if [ ! -f piper-sample-generator/models/en_US-libritts_r-medium.pt ]; then
  echo "⬇️  Voix Piper (libritts_r)..."
  wget -q -O piper-sample-generator/models/en_US-libritts_r-medium.pt \
    https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt
fi

# --- 3. Données négatives / FP (features pré-calculées, gros .npy) --------
HF="https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main"
[ -f data/openwakeword_features_ACAV100M_2000_hrs_16bit.npy ] || {
  echo "⬇️  Features négatives ACAV100M (~2 Go)..."
  wget -q -O data/openwakeword_features_ACAV100M_2000_hrs_16bit.npy \
    "$HF/openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
}
[ -f data/validation_set_features.npy ] || {
  echo "⬇️  Features de validation (faux positifs)..."
  wget -q -O data/validation_set_features.npy "$HF/validation_set_features.npy"
}

# --- 4. Bruit de fond + réverbération (RIRs) -----------------------------
#   Le notebook officiel télécharge MIT RIRs + AudioSet/FMA 16 kHz via la lib
#   `datasets`. Ces jeux sont volumineux → on délègue au helper du dépôt si
#   présent, sinon prépare-les toi-même (voir README, section « Données »).
if [ ! -d data/mit_rirs ] || [ ! -d data/audioset_16k ]; then
  echo "ℹ️  Prépare les données de bruit/RIR (data/mit_rirs, data/audioset_16k, data/fma_16k)."
  echo "    Le notebook officiel automatic_model_training.ipynb a la cellule de téléchargement."
  echo "    (On continue : si elles manquent, l'augmentation sera limitée.)"
fi

# --- 5. Pipeline d'entraînement openWakeWord -----------------------------
TRAIN="openWakeWord/openwakeword/train.py"
echo "🔊 1/3 Génération des clips positifs « athena » (Piper)..."
python "$TRAIN" --training_config "$CFG" --generate_clips
echo "🌫️  2/3 Augmentation (bruit + réverbération)..."
python "$TRAIN" --training_config "$CFG" --augment_clips
echo "🧠 3/3 Entraînement du modèle..."
python "$TRAIN" --training_config "$CFG" --train_model

echo ""
echo "✅ Terminé. Modèle attendu : ./athena_model/athena.onnx"
echo "   Déploiement → voir tools/train_wakeword/README.md"
