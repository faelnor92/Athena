"""TOTP (RFC 6238) en Python pur — 2FA optionnelle, sans dépendance externe.

Compatible avec Google Authenticator / Authy / FreeOTP (SHA1, 6 chiffres, période 30 s).
Le secret (base32) est généré côté serveur, stocké CHIFFRÉ (cf. UserStore), et exporté à
l'utilisateur sous forme d'URI `otpauth://` (à scanner) lors de l'enrôlement.
"""
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret(length: int = 20) -> str:
    """Secret base32 (sans padding) pour un authentificateur."""
    return base64.b32encode(secrets.token_bytes(length)).decode("utf-8").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    s = (secret_b32 or "").upper().replace(" ", "")
    s += "=" * ((8 - len(s) % 8) % 8)  # padding base32
    key = base64.b32decode(s)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify(secret_b32: str, code: str, window: int = 1, period: int = 30, digits: int = 6) -> bool:
    """Vérifie un code TOTP avec une tolérance de ±`window` pas (dérive d'horloge)."""
    code = re.sub(r"\D", "", str(code or ""))
    if not secret_b32 or len(code) != digits:
        return False
    counter = int(time.time() // period)
    for w in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + w, digits), code):
            return True
    return False


def provisioning_uri(secret_b32: str, account: str, issuer: str = "Athena") -> str:
    """URI otpauth:// pour QR code / saisie manuelle dans l'app d'authentification."""
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")
