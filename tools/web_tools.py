import requests
import re
import html as _html
from urllib.parse import unquote

def web_search(query: str) -> str:
    """
    Effectue une recherche sur le Web en direct via DuckDuckGo et renvoie les 5 meilleurs résultats (titre, lien, extrait).
    
    Args:
        query (str): Le terme ou la phrase à rechercher sur le Web.
        
    Returns:
        str: Liste textuelle formatée des résultats de recherche ou un message d'erreur.
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        r = requests.post(url, data={"q": query}, headers=headers, timeout=10)
        if r.status_code != 200:
            return f"Erreur : Impossible de contacter le moteur de recherche (Code {r.status_code})"
            
        html = r.text

        def _clean_ddg_url(raw: str) -> str:
            # DuckDuckGo enveloppe les liens : //duckduckgo.com/l/?uddg=<URL>&...
            if "uddg=" in raw:
                try:
                    return unquote(raw.split("uddg=")[1].split("&")[0])
                except Exception:
                    return raw
            return raw

        # Robuste à l'ordre des attributs : on capture chaque <a ... class="result__a" ...>
        results = []
        snippets = re.findall(
            r'<a\b[^>]*\bclass="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            html, re.DOTALL,
        )
        for i, m in enumerate(re.finditer(
            r'<a\b([^>]*\bclass="[^"]*result__a[^"]*"[^>]*)>(.*?)</a>', html, re.DOTALL,
        )):
            if len(results) >= 5:
                break
            attrs, text = m.group(1), m.group(2)
            href_m = re.search(r'href="([^"]+)"', attrs)
            if not href_m:
                continue
            title = _html.unescape(re.sub(r"<[^>]*>", "", text)).strip()
            url_clean = _clean_ddg_url(href_m.group(1))
            snippet = _html.unescape(re.sub(r"<[^>]*>", "", snippets[i])).strip() if i < len(snippets) else ""
            results.append(f"🔹 **{title}**\n🔗 Lien: {url_clean}\n📝 Extrait: {snippet}\n")

        if not results:
            return "Aucun résultat trouvé sur le Web."

        return "\n".join(results)
    except Exception as e:
        return f"Erreur lors de la recherche Web : {str(e)}"

def web_scrape(url: str) -> str:
    """
    Récupère le contenu textuel nettoyé d'une page Web (scraping).
    
    Args:
        url (str): L'adresse URL complète de la page Web à lire (ex: https://example.com/article).
        
    Returns:
        str: Le contenu textuel principal de la page, débarrassé du code HTML/scripts/style.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return f"Erreur : Code HTTP {r.status_code} lors du chargement de la page."
            
        html = r.text
        
        # 1. Retirer les scripts, styles, et balises de structure lourde
        html = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<head\b[^<]*(?:(?!<\/head>)<[^<]*)*<\/head>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<header\b[^<]*(?:(?!<\/header>)<[^<]*)*<\/header>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<footer\b[^<]*(?:(?!<\/footer>)<[^<]*)*<\/footer>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<nav\b[^<]*(?:(?!<\/nav>)<[^<]*)*<\/nav>', '', html, flags=re.IGNORECASE)
        
        # 2. Aérer le texte
        html = re.sub(r'</?(?:div|p|h[1-6]|li|tr|br\s*/?)>', '\n', html, flags=re.IGNORECASE)
        
        # 3. Supprimer toutes les autres balises HTML
        text = re.sub(r'<[^>]+>', '', html)
        
        # 4. Nettoyer les sauts de lignes multiples
        lines = [line.strip() for line in text.splitlines()]
        clean_lines = [line for line in lines if line]
        
        clean_text = "\n".join(clean_lines)
        
        # 5. Tronquer le texte pour éviter d'exploser le contexte LLM (max 3500 caractères)
        if len(clean_text) > 3500:
            return clean_text[:3500] + "\n\n... [CONTENU TRONQUÉ POUR PRÉSERVER LE CONTEXTE LLM] ..."
            
        return clean_text
    except Exception as e:
        return f"Erreur lors du scraping de la page Web : {str(e)}"
