# 🔒 Déploiement & sécurité (checklist production / homelab)

Athena est conçue pour l'auto-hébergement. Cette checklist liste les points à vérifier
**avant d'exposer une instance**. Le scan automatique (`bash scripts/security_scan.sh`, aussi
en CI) couvre le code et les dépendances ; cette page couvre la **configuration de déploiement**.

## 1. Authentification & comptes
- [ ] **Activer l'authentification** : définir `ADMIN_PASSWORD` (ou créer au moins un compte).
      Sans `ADMIN_PASSWORD` **ni** utilisateur, l'API est **ouverte** (pratique en dev local,
      jamais en exposition réseau).
- [ ] **Mot de passe fort** : `MIN_PASSWORD_LENGTH` ≥ 12 conseillé.
- [ ] **MFA (TOTP)** activée pour les comptes admin (onglet Utilisateurs).
- [ ] **Durée de session** raisonnable : `SESSION_TTL_HOURS` (défaut 168 h = 7 j).

## 2. Exposition réseau
- [ ] **HTTPS obligatoire** dès qu'on sort du LAN : terminer le TLS via un reverse-proxy
      (Caddy/Traefik/Nginx). Athena détecte `x-forwarded-proto=https` pour activer HSTS.
- [ ] **`HOST`** : garder `127.0.0.1` derrière le proxy ; n'exposer `0.0.0.0` que si nécessaire
      (un garde-fou réseau refuse certaines opérations sur hôte exposé sans auth).
- [ ] **`ALLOWED_ORIGINS`** : restreindre aux origines réelles (CORS).
- [ ] **Rate-limit** : `RATE_LIMIT_PER_MIN` (défaut 300/worker) adapté à l'exposition.
- [ ] **CSP** : stricte par défaut (rétablie en v0.26.0). Ne l'élargir (`CONTENT_SECURITY_POLICY`)
      qu'en connaissance de cause ; le studio AthenaDesign a déjà sa CSP permissive isolée sur
      `/athenadesign`.

## 3. Garde anti-SSRF (outils web / intégrations internes)
- [ ] `tools/net_guard.py` bloque par défaut les IP privées/loopback et **toujours**
      `169.254.169.254` (métadonnées cloud).
- [ ] Pour autoriser un service interne de confiance (Nextcloud/HA en IP privée) : renseigner
      `NET_GUARD_ALLOW_HOSTS` (CSV) — **liste blanche minimale**, jamais l'IP de métadonnées.

## 4. Secrets
- [ ] **`.env` non versionné** (vérifié par le scan : échec si `.env` est suivi par git).
- [ ] Pas de secret en clair dans le code (le scan détecte les motifs courants : clés OpenAI/AWS,
      clés privées, tokens GitHub).
- [ ] Clés LLM / mots de passe d'app (CalDAV, IMAP, Proxmox…) saisis via l'UI/`.env`, pas en dur.

## 5. Exécution de code (sandbox)
- [ ] Le sandbox d'exécution (`code_sandbox`/`dev_container`) tourne en **Docker** avec
      `--cap-drop ALL`, `--no-new-privileges`, limites mem/cpu/pids et **réseau désactivable**.
      Vérifier que Docker est présent en prod (sinon repli local moins isolé).
- [ ] **Approbations sensibles** : garder `AUTO_APPROVE_SENSITIVE=false` (l'agent demande
      confirmation avant les actions à risque : shell, SSH, écritures système).

## 6. Données & sauvegardes
- [ ] L'état vit dans `athena_state.sqlite3` (WAL) + bases dédiées (runs, conversations) +
      `chroma`. **Sauvegarder** ces fichiers (cf. `core/backup.py`).
- [ ] Les projets/partages : vérifier les permissions de fichiers du dossier `athena_projects/`.

## 7. CI / qualité (garde-fous automatiques)
- [ ] `pytest tests/ -m "not network"` vert (suite hermétique).
- [ ] `bash scripts/security_scan.sh` sans **alerte bloquante** (bandit HIGH/HIGH, secrets, `.env`
      suivi). Les CVE transitives (pip-audit) sont **informatives**.

> Mise à jour : `./update.sh` (installe les nouvelles dépendances de `requirements.txt`, dont
> `basedpyright`, puis redémarre). Voir le `CHANGELOG.md` pour les changements de version.
