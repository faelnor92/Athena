"""Garde anti-SSRF partagé par les outils web (web_scrape, render_page).

Bloque l'accès aux adresses internes / loopback / link-local / métadonnées cloud,
y compris quand un nom de domaine PUBLIC résout vers une IP interne (DNS rebinding) :
on résout réellement le hostname et on vérifie TOUTES les IP retournées.
"""
import ipaddress
import socket
import urllib.parse

_BLOCKED_NAMES = {"localhost", "metadata.google.internal"}


def _ip_is_internal(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # non résoluble proprement → on bloque par prudence
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def is_blocked_url(url: str) -> bool:
    """Vrai si l'URL pointe (directement ou après résolution DNS) vers une cible interne."""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").strip().lower()
    except Exception:
        return True
    if not host or host in _BLOCKED_NAMES:
        return True
    # IP littérale dans l'URL : vérification directe.
    try:
        ipaddress.ip_address(host)
        return _ip_is_internal(host)
    except ValueError:
        pass
    # Nom de domaine : on résout et on vérifie chaque IP (anti DNS rebinding).
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True  # résolution impossible → bloqué
    return any(_ip_is_internal(info[4][0]) for info in infos)


def check_url(url: str):
    """Renvoie un message d'erreur si l'URL est bloquée, sinon None."""
    if is_blocked_url(url):
        return ("Erreur : accès bloqué (localhost / adresse interne / métadonnées) "
                "pour des raisons de sécurité (anti-SSRF).")
    return None
