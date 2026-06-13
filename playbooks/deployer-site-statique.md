---
name: deployer-site-statique
description: Déployer un site web statique sur un serveur via SSH + nginx (build, copie, conf, reload)
---

## Objectif
Mettre en ligne un site statique (HTML/CSS/JS) sur un serveur distant déjà accessible en SSH,
servi par nginx.

## Pré-requis
- L'hôte SSH cible est enregistré (Réglages → SSH) et autorisé pour ce compte.
- nginx est installé sur la cible.

## Étapes
1. **Vérifier la cible** : `execute_bash_command("nginx -v && ls -d /var/www", host="<hôte>")`.
2. **Construire le site** localement si nécessaire (ex. `npm run build` → dossier `dist/`).
3. **Copier les fichiers** dans le webroot, ex. `/var/www/<site>/` (rsync ou scp).
4. **Configurer le vhost** nginx (`/etc/nginx/sites-available/<site>`) :
   - `root /var/www/<site>;` · `index index.html;` · `server_name <domaine>;`
   - `location / { try_files $uri $uri/ =404; }`
5. **Activer** : lien dans `sites-enabled`, puis `nginx -t` (test) et `systemctl reload nginx`.
6. **Vérifier** : `curl -I http://<domaine>` doit renvoyer `200`.

## Bonnes pratiques
- Toujours `nginx -t` AVANT de recharger (un conf invalide casserait tous les sites).
- Demander une **confirmation** avant toute commande `sudo` / qui écrase un webroot existant.
- Privilégier HTTPS (Let's Encrypt / certbot) en production.

## Pièges
- Permissions du webroot (le user nginx doit pouvoir lire).
- Cache navigateur : tester en navigation privée après un déploiement.
