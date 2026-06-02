# Documentation de l'API REST - Jarvis Swarm

Jarvis est bâti sur **FastAPI**, offrant des routeurs REST complets, asynchrones et sécurisés pour interagir avec l'Essaim (Swarm) de l'extérieur.

## Authentification
Toutes les requêtes (sauf exceptions publiques comme les Webhooks) nécessitent une authentification par Token Bearer ou Cookie.
**En-tête requis :** `Authorization: Bearer <votre_token_ou_mot_de_passe>`

---

## 1. Chat & Orchestration (`routers/chat.py`)

### `POST /api/chat`
Envoie un message à l'essaim et récupère la réponse (Streaming ou JSON).
* **Payload (JSON)** :
  * `message` (string) : Le message de l'utilisateur.
  * `agent` (string, optionnel) : Forcer l'utilisation d'un agent spécifique. Par défaut: Orchestrateur.
  * `stream` (boolean) : `true` pour recevoir du Server-Sent Events (SSE).
* **Réponse (si stream=false)** :
  ```json
  {
    "status": "success",
    "response": "Voici la réponse de l'agent",
    "agent": "Orchestrateur"
  }
  ```

### `GET /api/history`
Récupère l'historique de la session conversationnelle en cours (depuis `conversations.sqlite3`).
* **Réponse** : Liste des messages (rôles `user`, `assistant`, `tool`).

### `POST /api/clear`
Efface l'historique conversationnel de la session active.

---

## 2. Routines & Planification (`routers/config.py`)

### `GET /api/routines`
Liste toutes les routines programmées et webhooks.

### `POST /api/routines`
Crée ou met à jour une routine.
* **Payload (JSON)** :
  * `id` (string, optionnel)
  * `name` (string)
  * `prompt` (string) : La tâche que l'agent doit accomplir.
  * `schedule` (object) : ex: `{"type": "daily", "time": "03:00"}`
  * `agent` (string) : Nom de l'agent à invoquer (ou `_nightly_agent` pour la maintenance).

### `POST /api/hooks/{rid}`
Déclenche un webhook d'entrée (sans authentification si le secret est valide). Utile pour **Home Assistant**, **n8n** ou des capteurs externes.

---

## 3. Système & Télémétrie (`routers/system.py`)

### `GET /api/system/telemetry`
Retourne les métriques en direct (CPU, RAM, Tokens consommés, Coût financier généré). Les données sont tirées de `runs.sqlite3`.

### `GET /api/system/runs`
Liste l'historique de toutes les exécutions d'agents (tâches accomplies, erreurs, requêtes d'outils).

---

## 4. Espace de Travail (`routers/workspace.py`)

### `GET /api/fs/list`
Liste les fichiers dans le dossier de travail courant de l'agent.
* **Query Params** : `path` (chemin relatif).

### `GET /api/fs/read`
Lit le contenu d'un fichier textuel.

---

## Modèles de Données & Code de Retour

- L'API utilise les standards **HTTP (200, 400, 403, 404, 500)**.
- Les erreurs renvoient systématiquement un JSON au format :
  ```json
  {"detail": "Description claire de l'erreur"}
  ```
- Les CORS sont strictement limités aux origines de confiance (cf. `server.py`).
