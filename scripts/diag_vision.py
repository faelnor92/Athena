"""Diagnostic VISION : teste si ton endpoint LLM accepte une IMAGE en entrée, en réutilisant
EXACTEMENT la config qu'Athena utilise déjà (URL + clé + routage litellm). Pas de devinette
d'URL → si le texte marche dans Athena, ce test utilise le même chemin.

Usage (sur le homelab, depuis le dossier Athena) :
    .venv/bin/python scripts/diag_vision.py            # teste le modèle « gemma »
    .venv/bin/python scripts/diag_vision.py qwen3       # teste un autre modèle
    .venv/bin/python scripts/diag_vision.py gemma /chemin/vers/une/image.png   # image locale

Résultat :
  ✅ une DESCRIPTION de l'image  → le modèle a la VISION activée sur ton endpoint.
  ❌ une erreur (champ non supporté / invalid) → endpoint en mode texte seul → VLM local requis.
"""
import os
import sys
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Petite image PNG publique (dégradé) pour le test par défaut.
_DEFAULT_URL = ("https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/"
                "PNG_transparency_demonstration_1.png/240px-PNG_transparency_demonstration_1.png")


def _image_part(arg_path: str):
    if arg_path and os.path.isfile(arg_path):
        with open(arg_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        ext = (os.path.splitext(arg_path)[1].lstrip(".") or "png").lower()
        return {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}}
    return {"type": "image_url", "image_url": {"url": _DEFAULT_URL}}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "gemma"
    img = _image_part(sys.argv[2] if len(sys.argv) > 2 else "")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "Décris cette image en une phrase."},
        img,
    ]}]
    try:
        from core.state import swarm
    except Exception as e:
        print(f"❌ Impossible de charger Athena : {e}")
        return
    print(f"→ Test vision sur le modèle « {model} » via l'endpoint configuré d'Athena…\n")
    try:
        resp = swarm._complete(model, messages, tools_schema=None)
        out = (resp.choices[0].message.content or "").strip()
        if out:
            print("✅ VISION OK — le modèle a décrit l'image :\n")
            print("   " + out)
            print("\n→ La vision passe par TON endpoint existant (pas besoin de VLM local).")
        else:
            print("⚠️ Réponse vide — le modèle a accepté l'image mais n'a rien renvoyé "
                  "(vision peut-être non réellement supportée).")
    except Exception as e:
        print(f"❌ Échec — l'endpoint n'a pas accepté l'image :\n   {e}\n")
        print("→ L'endpoint est probablement en mode TEXTE SEUL → il faudrait un VLM local "
              "(UI-TARS / Qwen-VL sur la RTX 3050) pour la vision.")


if __name__ == "__main__":
    main()
