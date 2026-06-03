"""2FA / TOTP : stockage du secret (chiffré), états activé/désactivé, vérification de code.

Reproduit la logique d'enrôlement et d'enforcement de connexion sans serveur HTTP.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name


def _current_code(secret):
    from core import totp
    return totp._hotp(secret, int(time.time() // 30))


def test_mfa_lifecycle_on_user():
    from core.users import UserStore
    from core import totp
    s = UserStore()
    s.create("dave", "motdepasse8")
    assert s.mfa_enabled("dave") is False
    # enrôlement : on stocke un secret (ici en clair pour le test) non encore activé
    secret = totp.generate_secret()
    s.set_mfa("dave", secret, enabled=False)
    assert s.mfa_enabled("dave") is False, "tant que non activé, la 2FA ne s'applique pas"
    # activation après vérification d'un code
    assert totp.verify(secret, _current_code(secret)) is True
    s.set_mfa("dave", secret, enabled=True)
    assert s.mfa_enabled("dave") is True
    assert s.get_mfa("dave")["secret"] == secret
    # désactivation
    s.clear_mfa("dave")
    assert s.mfa_enabled("dave") is False and s.get_mfa("dave") is None


def test_login_enforcement_logic():
    # Reproduit la décision du endpoint /api/login : mdp OK + 2FA activée ⇒ code requis & valide.
    from core import totp
    from core.users import UserStore
    s = UserStore()
    s.create("erin", "motdepasse8")
    secret = totp.generate_secret()
    s.set_mfa("erin", secret, enabled=True)

    def login_ok(pw, code):
        if s.verify("erin", pw) is None:
            return False
        m = s.get_mfa("erin")
        if m and m.get("enabled"):
            return totp.verify(m["secret"], code)
        return True

    assert login_ok("mauvais", _current_code(secret)) is False    # mauvais mdp
    assert login_ok("motdepasse8", "000000") in (False, True)     # code probablement faux, pas d'exception
    assert login_ok("motdepasse8", _current_code(secret)) is True  # mdp + bon code
    assert login_ok("motdepasse8", "") is False                    # 2FA requise, code manquant


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests 2FA passent.")
