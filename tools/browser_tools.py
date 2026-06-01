"""Navigation web headless : rend le JavaScript d'une page (via un navigateur Chromium)
et renvoie son texte lisible + ses liens. Complète web_scrape (qui ne voit pas le
contenu généré côté client) pour les sites dynamiques (SPA, contenu chargé en JS).

Utilise le Chromium du système (léger, pas de dépendance Playwright). Si aucun
navigateur n'est trouvé, renvoie une erreur explicite (repli : web_scrape).
"""
import os
import re
import shutil
import subprocess
import tempfile
import html as _html
import ipaddress
import urllib.parse


def _find_chromium():
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    env = os.getenv("CHROMIUM_BIN", "").strip()
    return env or None


def _is_blocked_host(url: str) -> bool:
    """Bloque localhost et les IP internes/métadonnées (anti-SSRF basique)."""
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return True
    if host in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False  # nom de domaine public


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def render_page(url: str) -> str:
    """
    Charge une page web dans un navigateur headless (exécute le JavaScript) et renvoie
    son TEXTE lisible + ses principaux liens. À utiliser quand web_scrape ne renvoie rien
    d'utile (sites dynamiques / SPA / contenu chargé en JS).
    url: L'URL http(s) de la page à charger.
    """
    url = (url or "").strip()
    if not re.match(r"^https?://", url):
        return "Erreur : fournis une URL http(s) valide."
    if _is_blocked_host(url):
        return "Erreur : accès bloqué (localhost / adresse interne) pour des raisons de sécurité."
    chrome = _find_chromium()
    if not chrome:
        return ("Erreur : aucun navigateur Chromium trouvé. Installe chromium (ou définis "
                "CHROMIUM_BIN), ou utilise web_scrape pour les pages statiques.")
    profile = tempfile.mkdtemp(prefix="jarvis-chrome-")
    try:
        out = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
             "--disable-extensions", f"--user-data-dir={profile}",
             "--virtual-time-budget=9000", "--dump-dom", url],
            capture_output=True, text=True, timeout=int(os.getenv("BROWSER_TIMEOUT", "35")),
        )
        dom = out.stdout or ""
        if not dom.strip():
            return f"Page chargée mais vide (ou bloquée). Détail : {(out.stderr or '')[:200]}"
        # Liens (avant strip)
        links = []
        for m in re.finditer(r'<a\b[^>]*\bhref="([^"#?][^"]*)"[^>]*>(.*?)</a>', dom, re.I | re.S):
            href = m.group(1).strip()
            label = re.sub(r"(?s)<[^>]+>", "", m.group(2))
            label = _html.unescape(label).strip()
            if href.startswith("http") and label:
                links.append(f"- {label[:70]} → {href}")
            if len(links) >= 15:
                break
        text = _html_to_text(dom)[:6000]
        result = f"[Page rendue : {url}]\n\n{text}"
        if links:
            result += "\n\n— Liens principaux —\n" + "\n".join(links)
        return result
    except subprocess.TimeoutExpired:
        return "Erreur : délai dépassé lors du rendu de la page."
    except Exception as e:
        return f"Erreur lors du rendu de la page : {e}"
    finally:
        shutil.rmtree(profile, ignore_errors=True)
