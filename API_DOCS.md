# Documentation de l'API REST - Athena Swarm

Athena est bâti sur **FastAPI**, offrant des routeurs REST complets, asynchrones et sécurisés pour interagir avec l'Essaim (Swarm) de l'extérieur.

## Authentification
Toutes les requêtes (sauf exceptions publiques comme les Webhooks ou les liens d'invitation) nécessitent une authentification par Token Bearer ou Cookie (Architecture Multi-Tenant).
**En-tête requis :** `Authorization: Bearer <votre_token_sso_ou_mot_de_passe>`

---

## 1. Chat & Orchestration (`routers/chat.py`)

### `POST /api/chat`
Envoie un message à l'essaim et récupère la réponse (Streaming ou JSON).
* **Payload (JSON)** :
  * `message` (string) : Le message de l'utilisateur.
  * `agent` (string, optionnel) : Forcer l'utilisation d'un agent spécifique. Par défaut: Orchestrateur.
  * `stream` (boolean) : `true` pour recevoir du Server-Sent Events (SSE).
* **Code d'Erreur :** Peut retourner HTTP 429 (Trop de requêtes) si le **Quota LLM** journalier de l'utilisateur est dépassé.

### `GET /api/history`
Récupère l'historique de la session conversationnelle de l'utilisateur.

---

## 2. Authentification & Profil (`routers/auth.py` / `system.py`)

### `POST /api/login`
Authentification standard ou OIDC/SSO (si configuré).
* Retourne un token JWT de session.

### `GET /api/users/me`
Retourne les données profil (rôle, budget, tokens consommés).
* **Nouveauté :** Contient désormais `quota_max_tokens` et `tokens_used_today`.

---

## 3. Voix & TTS/STT (`routers/config_voice.py`)

### `POST /api/system/tts/restart`
Redémarre le conteneur Docker `kokoro-fastapi-cpu` à chaud (nécessite des droits admin ou accès socket Docker).

### `GET /api/voice/ws`
Websocket pour le streaming audio temps réel (Satellites ESP32-S3 ou UI web). Gère le VAD, STT (Whisper) et la synthèse (Kokoro).

---

## 4. Routines & Planification (`routers/config_routines.py`)

### `GET /api/routines`
Liste toutes les routines programmées et webhooks.

### `POST /api/routines`
Crée ou met à jour une routine.
* **Payload (JSON)** :
  * `name`, `prompt`, `schedule` (type cron ou daily), `agent`.

### `POST /api/hooks/{rid}`
Déclenche un webhook d'entrée (sans auth si le secret est valide). Utile pour **Home Assistant**, **n8n** ou des capteurs externes.

---

## 5. Système & Télémétrie (`routers/system.py`)

### `GET /api/system/telemetry`
Retourne les métriques en direct (CPU, RAM, Coût financier généré par utilisateur).

### `GET /api/system/logs`
Récupère les derniers logs centralisés du système et des outils.

---

## 6. Projets & Espace de Travail (`routers/workspace.py` & `projects.py`)

### `GET /api/projects`
Liste les projets accessibles (personnels ou partagés avec l'utilisateur).

### `GET /api/fs/list`
Liste les fichiers dans le projet actif (scopé par utilisateur).

---

## Modèles de Données & Erreurs

- L'API utilise les standards **HTTP (200, 401, 403, 404, 500)**.
- Les erreurs renvoient systématiquement un JSON au format : `{"detail": "Description claire de l'erreur"}`
