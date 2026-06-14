#!/usr/bin/env python3
"""Diagnostic Gemini / Google AI Studio pour Athena.

Lancement (depuis le dossier d'Athena, ex. /root/athena) :
    .venv/bin/python scripts/diag_gemini.py

Il teste, dans l'ordre :
  1. la présence/forme de GEMINI_API_KEY (lue depuis .env) ;
  2. la liste RÉELLE des modèles que ta clé peut utiliser (appel direct à l'API Google) ;
  3. un vrai appel de génération via litellm (comme le fait Athena) sur quelques modèles.

Aucune modification : lecture seule. Colle la sortie complète pour diagnostic.
"""
import os
import sys

# Se placer à la racine du projet (le script est dans scripts/).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

print("=" * 70)
print("DIAGNOSTIC GEMINI / GOOGLE AI STUDIO — Athena")
print("=" * 70)

# --- 1. Clé ---------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception as e:
    print(f"[!] dotenv indisponible ({e}) — on lit quand même os.environ.")

key = (os.getenv("GEMINI_API_KEY") or "").strip()
print("\n[1] Clé GEMINI_API_KEY")
print(f"    présente : {bool(key)}")
print(f"    longueur : {len(key)}")
print(f"    forme    : {key[:4]+'…'+key[-2:] if len(key) > 8 else '(trop courte)'}")
print(f"    commence par 'AIza' (forme attendue AI Studio) : {key.startswith('AIza')}")
if not key:
    print("\n=> STOP : aucune clé. Renseigne GEMINI_API_KEY (Réglages → Clés API, ou .env).")
    sys.exit(1)

# --- 2. Modèles RÉELLEMENT disponibles pour cette clé ---------------------
print("\n[2] Modèles disponibles pour TA clé (API Google directe)")
usable = []
try:
    import requests
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": key}, timeout=15,
    )
    print(f"    HTTP {r.status_code}")
    if r.status_code == 200:
        for m in r.json().get("models", []):
            name = m.get("name", "").replace("models/", "")
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in methods and name.startswith("gemini"):
                usable.append(name)
        print(f"    {len(usable)} modèle(s) Gemini utilisable(s) :")
        for n in usable:
            print(f"      - gemini/{n}   (à saisir tel quel dans Athena)")
    else:
        print(f"    Réponse : {r.text[:400]}")
        print("    => Clé probablement INVALIDE/expirée ou API 'Generative Language' non activée.")
except Exception as e:
    print(f"    Erreur appel API : {type(e).__name__}: {e}")

# --- 3. Vrai appel via litellm (comme Athena) -----------------------------
print("\n[3] Test de génération via litellm (comme Athena)")
# On teste en priorité un modèle RÉELLEMENT dispo (point 2), + des classiques.
candidates = []
for pref in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
    if pref in usable:
        candidates.append(pref)
if not candidates and usable:
    candidates = usable[:2]
if not candidates:
    candidates = ["gemini-2.5-flash", "gemini-1.5-flash"]

try:
    import litellm
    print(f"    version litellm : {getattr(litellm, '__version__', '?')}")
    for name in candidates:
        model = f"gemini/{name}"
        try:
            resp = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": "Réponds juste: OK"}],
                api_key=key, timeout=30,
            )
            txt = resp.choices[0].message.content
            print(f"    ✅ {model} -> {txt!r}")
        except Exception as e:
            print(f"    ❌ {model} -> {type(e).__name__}: {str(e)[:300]}")
except Exception as e:
    print(f"    litellm indisponible : {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("INTERPRÉTATION")
print("  - [1] présente:False        -> la clé n'est pas chargée (mauvais .env).")
print("  - [2] HTTP 400/403          -> clé invalide / API non activée sur le projet Google.")
print("  - [2] liste OK + [3] ✅      -> Gemini marche : utilise un 'gemini/<nom>' de la liste [2]")
print("                                 dans Athena (Réglages → Agents → Modèle).")
print("  - [2] OK mais [3] ❌ 404     -> le NOM du modèle choisi dans Athena n'existe pas pour")
print("                                 ta clé : prends-en un de la liste [2].")
print("=" * 70)
