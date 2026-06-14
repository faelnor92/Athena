# Connecter ton compte Google (Calendar + Gmail) à Athena — OAuth

Permet à l'agent de **lire/écrire dans TON Google Calendar** et de **lire tes mails Gmail**
(lecture seule), avec **ton propre compte**, sans partager d'agenda ni uploader de clé de
compte de service.

> ⚠️ Contrainte Google : une URI de redirection en `http://` sur une **IP** privée
> (ex. `http://192.168.1.50:8000`) est **refusée**. Deux solutions ci-dessous.
> Le consentement n'est demandé qu'**une seule fois** : ensuite l'agenda et l'agent
> fonctionnent depuis n'importe où (y compris l'accès par IP LAN), car le renouvellement
> du jeton se fait serveur↔Google sans navigateur.

---

## 1. Créer les identifiants OAuth (une fois, commun aux deux solutions)

1. [Google Cloud Console](https://console.cloud.google.com/) → crée/sélectionne un projet.
2. **API et services → Bibliothèque** : active **Google Calendar API** et **Gmail API**.
3. **API et services → Écran de consentement OAuth** :
   - Type **Externe**, renseigne le nom de l'app + ton email.
   - **Utilisateurs test** : ajoute ton adresse Gmail (tant que l'app est en mode « test »,
     seuls les comptes listés peuvent se connecter — c'est suffisant pour un usage perso).
   - Scopes : tu peux laisser vide ici (Athena les demande au moment de l'autorisation).
4. **API et services → Identifiants → Créer des identifiants → ID client OAuth** :
   - Type d'application : **Application Web**.
   - **URI de redirection autorisés** : ajoute l'URI correspondant à ta solution (cf. §2 ou §3).
5. Récupère le **Client ID** et le **Client secret** → dans le `.env` d'Athena :
   ```ini
   GOOGLE_OAUTH_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=xxxxxxxx
   ```

---

## 2. Solution A — Consentement unique via `localhost` (zéro infra)

Idéale si tu veux tester vite, sans tunnel ni domaine.

1. URI de redirection à enregistrer dans Google (étape 1.4) :
   ```
   http://localhost:8000/api/oauth/google/callback
   ```
2. Dans le `.env` :
   ```ini
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/oauth/google/callback
   ```
3. Fais l'autorisation depuis un navigateur qui atteint `localhost:8000` **du serveur** :
   - soit directement le navigateur **sur le serveur** (s'il a un bureau graphique),
   - soit depuis ton poste via un **tunnel SSH** :
     ```bash
     ssh -L 8000:localhost:8000 <utilisateur>@<serveur>
     # puis, sur ton poste, ouvre http://localhost:8000
     ```
4. Réglages → 📅 Agenda → **« Connecter Google »** → consens dans la fenêtre Google.
5. C'est tout : reviens à ton accès habituel par IP LAN, l'agenda et Gmail fonctionnent.

---

## 3. Solution B — Cloudflare Tunnel (recommandé, pérenne)

Donne une URL **HTTPS publique stable** vers ton Athena, acceptée par Google et utilisable
depuis n'importe quel appareil.

1. Installe `cloudflared` sur le serveur, connecte ton compte Cloudflare, crée un tunnel
   pointant vers `http://localhost:8000` et associe un hostname, par ex.
   `athena.tondomaine.fr` (Cloudflare gère le certificat HTTPS).
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create athena
   # route le hostname vers le service local :
   cloudflared tunnel route dns athena athena.tondomaine.fr
   cloudflared tunnel run --url http://localhost:8000 athena
   ```
2. URI de redirection à enregistrer dans Google (étape 1.4) :
   ```
   https://athena.tondomaine.fr/api/oauth/google/callback
   ```
3. Dans le `.env` :
   ```ini
   GOOGLE_OAUTH_REDIRECT_URI=https://athena.tondomaine.fr/api/oauth/google/callback
   ```
   Pense aussi à autoriser l'origine côté Athena si besoin :
   ```ini
   ALLOWED_ORIGINS=https://athena.tondomaine.fr
   ```
4. Réglages → 📅 Agenda → **« Connecter Google »** depuis n'importe quel navigateur.

---

## Vérifier / dépanner

- Le bouton **« Connecter Google »** n'apparaît que si `GOOGLE_OAUTH_CLIENT_ID` **et**
  `GOOGLE_OAUTH_CLIENT_SECRET` sont définis (statut via `GET /api/oauth/google/status`).
- Après connexion, le statut affiche ✅ + ton adresse. Tu peux **Déconnecter** (révoque le
  jeton côté Google et l'efface localement).
- Calendrier ciblé : par défaut `primary` (ton agenda principal). Pour un autre calendrier,
  renseigne son ID dans Réglages → Agenda (`GOOGLE_CALENDAR_ID`).
- Gmail : **lecture seule** (scope `gmail.readonly`) — Athena ne peut ni envoyer ni supprimer.
- `redirect_uri_mismatch` : l'URI dans `.env` doit être **identique au caractère près** à
  celle enregistrée dans Google Cloud (schéma, hôte, port, chemin).
- `access_denied` / app en test : ajoute ton compte dans **Utilisateurs test** de l'écran de
  consentement.
