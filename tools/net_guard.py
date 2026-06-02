"""Garde anti-SSRF partagé par les outils web (web_scrape, render_page).

Bloque l'accès aux adresses internes / loopback / link-local / métadonnées cloud,
y compris quand un nom de domaine PUBLIC résout vers une IP interne (DNS rebinding) :
on résout réellement le hostname et on vérifie TOUTES les IP retournées.
"""
import contextlib
import ipaddress
import socket
import threading
import urllib.parse

_BLOCKED_NAMES = {"localhost", "metadata.google.internal"}

# Verrou pour l'épinglage d'IP (monkeypatch global de la résolution urllib3).
_pin_lock = threading.Lock()


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


_SSRF_ERR = ("Erreur : accès bloqué (localhost / adresse interne / métadonnées) "
             "pour des raisons de sécurité (anti-SSRF).")


def safe_resolve(url: str):
    """Valide l'URL et renvoie (host, ip_validée, None) ou (None, None, message).

    On résout le DNS, on vérifie TOUTES les IP, et on renvoie l'IP retenue afin de
    pouvoir y ÉPINGLER la connexion (cf. pin_host) — c'est ce qui ferme la fenêtre
    TOCTOU / DNS-rebinding entre la vérification et la connexion réelle du client HTTP.
    """
    try:
        host = (urllib.parse.urlparse(url).hostname or "").strip().lower()
    except Exception:
        return None, None, _SSRF_ERR
    if not host or host in _BLOCKED_NAMES:
        return None, None, _SSRF_ERR
    try:
        ipaddress.ip_address(host)  # IP littérale
        return (None, None, _SSRF_ERR) if _ip_is_internal(host) else (host, host, None)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return None, None, _SSRF_ERR
    ips = [info[4][0] for info in infos]
    if not ips or any(_ip_is_internal(ip) for ip in ips):
        return None, None, _SSRF_ERR
    return host, ips[0], None


@contextlib.contextmanager
def pin_host(host: str, ip: str):
    """Force la résolution de `host` vers `ip` validée pendant la requête (épinglage
    TCP). La SNI/validation de certificat restent sur le hostname réel (urllib3 ne
    change que l'adresse de connexion). Sérialisé par verrou (patch global)."""
    import urllib3.util.connection as _u3c
    with _pin_lock:
        orig = _u3c.create_connection

        def _patched(address, *args, **kwargs):
            h, port = address
            if h == host:
                address = (ip, port)
            return orig(address, *args, **kwargs)

        _u3c.create_connection = _patched
        try:
            yield
        finally:
            _u3c.create_connection = orig
