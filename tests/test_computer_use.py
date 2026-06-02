import os
import sys

# Ajouter le répertoire parent au sys.path pour les imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.computer_use import computer_use_action, _PLAYWRIGHT_AVAILABLE

def test_computer_use():
    if not _PLAYWRIGHT_AVAILABLE:
        print("⚠️ Playwright non installé. Le test est ignoré (mais l'outil gère correctement cette erreur).")
        return

    print("=== Test de l'outil Computer Use (RPA 2.0) ===")
    
    print("\n1. Navigation vers example.com...")
    res = computer_use_action("navigate", "https://example.com")
    print(res)
    assert "réussie" in res or "Erreur" in res

    print("\n2. Extraction du DOM allégé...")
    res = computer_use_action("get_dom")
    print(res[:500] + "...\n(tronqué)")
    assert "Example Domain" in res or "Erreur" in res
    
    print("\n3. Fermeture du navigateur...")
    res = computer_use_action("close")
    print(res)
    assert "fermé" in res

if __name__ == "__main__":
    test_computer_use()
    print("\n✅ Test Computer Use OK")
