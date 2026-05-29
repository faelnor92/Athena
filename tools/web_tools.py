import requests
import re
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
        
        # Trouver tous les liens et résumés des résultats
        results = []
        
        # Regex pour capturer les blocs de résultats dans DuckDuckGo HTML
        blocks = re.findall(r'<div class="result__body">.*?</div>\s*</div>', html, re.DOTALL)
        
        for block in blocks[:5]:
            title_match = re.search(r'<a class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL)
            href_match = re.search(r'href="([^"]+)"', block)
            snippet_match = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
            
            if title_match and href_match:
                title = re.sub(r'<[^>]*>', '', title_match.group(1)).strip()
                url_raw = href_match.group(1)
                
                # Nettoyer l'URL de redirection de DuckDuckGo
                if "uddg=" in url_raw:
                    try:
                        url_part = url_raw.split("uddg=")[1].split("&")[0]
                        url_clean = unquote(url_part)
                    except Exception:
                        url_clean = url_raw
                else:
                    url_clean = url_raw
                
                snippet = ""
                if snippet_match:
                    snippet = re.sub(r'<[^>]*>', '', snippet_match.group(1)).strip()
                
                results.append(f"🔹 **{title}**\n🔗 Lien: {url_clean}\n📝 Extrait: {snippet}\n")
                
        if not results:
            # Fallback regex simple
            links = re.findall(r'<a class="result__a" href="([^"]+)">(.*?)</a>', html)
            for href, text in links[:5]:
                title = re.sub(r'<[^>]*>', '', text).strip()
                results.append(f"🔹 **{title}**\n🔗 Lien: {href}\n")
                
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
