# 🔄 Reprendre le développement sur un autre poste

Le code et la configuration *modèle* sont versionnés ; **les secrets et l'état local
ne le sont pas** (cf. `.gitignore`). Voici comment repartir d'un poste neuf.

## 1. Prérequis
- **Python 3.13+**, **git**, et **Docker** (requis pour la sandbox d'exécution de code).
- Un endpoint LLM (cloud ou local) — par défaut le projet utilise `CUSTOM_LLM_API_BASE`.

## 2. Cloner
```bash
git clone <URL_DU_DEPOT> athena
cd athena
```

## 3. Dépendances
```bash
# RECOMMANDÉ : un environnement virtuel ISOLÉ en Python 3.13. Évite tout conflit
# avec d'anciennes versions installées au niveau système (ex. un vieux chromadb 0.5.x
# qui casse la mémoire). NE PAS installer au niveau système.
python3.13 -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -r requirements.txt
# Optionnel — assistant vocal local « Jarvis » (STT/wakeword) :
#   pip install -r requirements-voice.txt
# Optionnel — transcription de réunion + dictée vocale du chat (Whisper local) :
#   pip install openai-whisper        # ⚠️ tire PyTorch (~poids important)
#   (sinon : la transcription bascule sur un LLM cloud si GEMINI/OPENAI_API_KEY est défini)
# Sandbox : l'image est tirée au 1er usage, ou manuellement :
docker pull python:3.13-slim
```

## 4. Configuration (à recréer — non versionnée)
```bash
cp .env.example .env       # puis renseigner CUSTOM_LLM_API_BASE / CUSTOM_LLM_API_KEY, etc.
```
- **Test local** : laisser `HOST=127.0.0.1` (aucun mot de passe requis).
- **Accès réseau** : `HOST=0.0.0.0` **et** `ADMIN_PASSWORD=...` (idéalement derrière un reverse-proxy HTTPS).
- Fichiers optionnels (depuis leurs `.example` si besoin) :
  - `mcp_servers.json` (serveurs MCP),
  - `channel_policies.json` (permissions par canal).

## 5. Lancer
```bash
# (venv activé — cf. étape 3 ; utilise le python du venv, PAS le python3 système)
python server.py           # interface web -> http://localhost:8000
# ou
python main.py             # CLI interactif
python voice_assistant.py  # assistant vocal (serveur lancé à côté)
```
> ⚠️ Lance toujours avec le **python du venv** (venv activé, ou `.venv/bin/python server.py`).
> Le `python3` système utiliserait d'autres dépendances (potentiellement périmées).

## 6. Tests
```bash
for t in tests/test_*.py; do python3 "$t"; done
```

## 7. Ce qui NE transfère PAS par git (état local)
Recréé automatiquement, ou à **copier manuellement** si vous voulez migrer vos données :
- `conversations*.json` (fils de discussion), `core_memory.json` (faits mémorisés),
- `.chroma_db/` (mémoire vectorielle / RAG), `runs.sqlite3` (historique des runs),
- `workspace/` (sauf `pricing_config.json`), `logs/`,
- `skills/*.py` (compétences générées par les agents).

> Pour transporter une compétence précise dans le dépôt : `git add -f skills/<nom>.py`.
