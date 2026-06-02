"""Outil de Computer Use (RPA 2.0) pour l'automatisation web interactive.

Utilise Playwright pour piloter un navigateur de manière persistante (Headless).
Contrairement à browser_tools.py qui ne fait qu'un rendu statique (dump-dom), 
cet outil permet de cliquer, taper, et naviguer sur plusieurs requêtes.

L'accès concurrentiel et le thread-safety sont gérés par un Thread dédié.
"""
import os
import threading
import queue
import time
from tools.net_guard import is_blocked_url

try:
    import playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False


class PlaywrightWorker(threading.Thread):
    """Un thread dédié pour posséder la boucle d'événements Playwright.
    Évite les erreurs si FastAPI appelle l'outil depuis différents worker threads."""
    def __init__(self):
        super().__init__(daemon=True)
        self.req_queue = queue.Queue()
        self.res_queue = queue.Queue()
        
    def run(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return
            
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            last_used = time.time()
            
            while True:
                try:
                    # Timeout pour libérer la RAM après 2 minutes d'inactivité
                    req = self.req_queue.get(timeout=1.0)
                    last_used = time.time()
                except queue.Empty:
                    if time.time() - last_used > 120:
                        break  # Auto-shutdown
                    continue
                    
                if req["action"] == "close":
                    self.res_queue.put("Navigateur fermé.")
                    break
                    
                try:
                    action = req["action"]
                    target = req.get("target", "")
                    text = req.get("text", "")
                    
                    if action == "navigate":
                        page.goto(target, wait_until="domcontentloaded", timeout=15000)
                        self.res_queue.put(f"Navigation réussie vers {target}.")
                        
                    elif action == "click":
                        page.locator(target).first.click(timeout=5000)
                        self.res_queue.put(f"Clic effectué sur {target}.")
                        
                    elif action == "type":
                        page.locator(target).first.fill(text, timeout=5000)
                        self.res_queue.put(f"Texte tapé dans {target}.")
                        
                    elif action == "press_key":
                        page.locator(target).first.press(text, timeout=5000)
                        self.res_queue.put(f"Touche '{text}' pressée sur {target}.")
                        
                    elif action == "get_dom":
                        # Injection de JS pour extraire un DOM allégé, optimisé pour le LLM.
                        # Exclut les balises invisibles et affiche les sélecteurs cliquables.
                        script = '''
                        () => {
                            let text = "";
                            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
                            while(walker.nextNode()) {
                                const node = walker.currentNode;
                                if(node.nodeType === Node.ELEMENT_NODE) {
                                    if(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG'].includes(node.tagName)) continue;
                                    const rect = node.getBoundingClientRect();
                                    if(rect.width === 0 || rect.height === 0) continue;
                                    
                                    // Identify interactables for the agent
                                    if(['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(node.tagName)) {
                                        let selector = node.id ? "#" + node.id : "";
                                        if(!selector && node.className && typeof node.className === 'string') {
                                            selector = "." + node.className.split(" ").filter(c => c)[0];
                                        }
                                        text += `\\n[ÉLÉMENT INTERACTIF: <${node.tagName.toLowerCase()}> sélecteur="${node.tagName.toLowerCase()}${selector}"] `;
                                    }
                                } else if(node.nodeType === Node.TEXT_NODE) {
                                    const val = node.nodeValue.trim();
                                    if(val) text += val + " ";
                                }
                            }
                            return text;
                        }
                        '''
                        dom_text = page.evaluate(script)
                        import re
                        dom_text = re.sub(r" +", " ", dom_text)
                        self.res_queue.put(f"--- CONTENU DU NAVIGATEUR ---\n{dom_text[:10000]}")
                        
                    else:
                        self.res_queue.put(Exception(f"Action '{action}' non reconnue."))
                        
                except Exception as e:
                    self.res_queue.put(Exception(f"Erreur Playwright: {str(e)}"))
                    
            # Libération propre des ressources
            try: page.close()
            except: pass
            try: context.close()
            except: pass
            try: browser.close()
            except: pass


# Singleton global
_worker = None
_worker_lock = threading.Lock()

def _get_worker() -> PlaywrightWorker:
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = PlaywrightWorker()
            _worker.start()
        return _worker


def computer_use_action(action: str, target: str = "", text: str = "") -> str:
    """
    Pilote un navigateur web interactif de manière persistante (RPA / Computer Use).
    L'agent peut enchaîner plusieurs requêtes (ex: 'navigate', puis 'get_dom', puis 'click').
    
    Args:
        action (str): L'action à effectuer ("navigate", "click", "type", "press_key", "get_dom", "close").
        target (str): L'URL absolue (pour "navigate") ou le sélecteur CSS (pour "click", "type", "press_key").
        text (str): Le texte à taper (pour "type") ou la touche à presser (ex: "Enter" pour "press_key").
        
    Returns:
        str: Le résultat de l'action ou le contenu de la page (DOM simplifié).
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return "Erreur : La bibliothèque 'playwright' n'est pas installée. Impossible d'utiliser cet outil."
        
    action = action.lower()
    
    # Garde-fou de sécurité : empêcher l'accès aux IPs locales/cloud internes
    if action == "navigate":
        if not target.startswith("http"):
            target = "https://" + target
        if is_blocked_url(target):
            return "Erreur : URL interdite par mesure de sécurité anti-SSRF (accès local bloqué)."
            
    worker = _get_worker()
    worker.req_queue.put({
        "action": action,
        "target": target,
        "text": text
    })
    
    res = worker.res_queue.get(timeout=30.0)
    if isinstance(res, Exception):
        return str(res)
    return res

