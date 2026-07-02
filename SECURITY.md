# Politique de sécurité

## Signaler une vulnérabilité

**Ne créez pas d'issue publique pour une faille de sécurité.**

- De préférence : ouvrez un **avis privé** via l'onglet *Security* du dépôt GitHub
  (« Report a vulnerability » — GitHub Private Vulnerability Reporting).
- À défaut : contactez le mainteneur à **faelnor92@gmail.com** avec pour objet
  `[SECURITY] <résumé court>`.

Merci d'inclure : la version affectée (`VERSION` / tag), les étapes de reproduction,
l'impact estimé, et si possible un correctif suggéré. Une réponse est apportée sous
**7 jours** ; la divulgation publique se fait de façon coordonnée une fois le correctif
publié.

## Versions supportées

Seule la dernière version publiée (branche `main`) reçoit des correctifs de sécurité.

## Périmètre

Sont notamment dans le périmètre : contournement d'authentification/autorisation (RBAC),
échappement des sandbox d'exécution de code (Docker, AST), SSRF malgré `tools/net_guard`,
path traversal, fuite de secrets ou de données inter-comptes, injection via contenus
non fiables (mails, pages web, réponses MCP).

Hors périmètre : vulnérabilités nécessitant un accès admin déjà acquis, déploiements
ignorant la checklist `docs/DEPLOYMENT.md` (ex. exposition sans HTTPS ni reverse proxy),
et l'auto-hébergement de dépendances tierces (Ollama, Nextcloud…).

## Durcissement recommandé

Avant toute exposition réseau, suivez `docs/DEPLOYMENT.md` et l'audit
`docs/SECURITY_AUDIT.md` : HTTPS via reverse proxy, `ADMIN_PASSWORD` fort puis comptes
nominatifs + 2FA, ne jamais poser `SENSITIVE_TOOLS=none` sur une instance exposée,
sauvegardes de la clé `DB_ENCRYPTION_KEY` séparées de celles de la base.
