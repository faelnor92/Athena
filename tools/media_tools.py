import requests
import urllib.parse
import os
import random
import base64

def generate_image(prompt: str, filename: str = None) -> str:
    """
    Génère une image de haute qualité en direct à partir d'une description textuelle (Prompt)
    et l'enregistre à la racine de l'espace de travail.
    S'adapte automatiquement à l'API sélectionnée par l'utilisateur :
    - Pollinations AI (Gratuit)
    - OpenAI DALL-E 3 (Payant, nécessite OPENAI_API_KEY)
    - Stability AI Core (Payant, nécessite STABILITY_API_KEY)
    - Google Gemini Imagen 3 (Payant, utilise GEMINI_API_KEY)
    - Custom Endpoint (Utilise CUSTOM_IMAGE_API_BASE & CUSTOM_IMAGE_API_KEY)
    """
    try:
        # Générer un nom unique si vide
        if not filename:
            random_id = random.randint(1000, 9999)
            filename = f"image_generee_{random_id}.png"
        else:
            filename = os.path.basename(filename)
            if not filename.endswith((".png", ".jpg", ".jpeg")):
                filename += ".png"

        provider = os.environ.get("IMAGE_GENERATOR_PROVIDER", "pollinations").strip().lower()
        img_content = None
        engine_name = "Pollinations AI (Gratuit)"
        
        # =========================================================================
        # 1. MOTEUR OPENAI DALL-E 3
        # =========================================================================
        if provider == "openai":
            openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not openai_key:
                return "❌ Erreur : Vous avez choisi le moteur **OpenAI** mais votre clé `OPENAI_API_KEY` n'est pas configurée dans les paramètres !"
            
            engine_name = "OpenAI DALL-E 3"
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024"
            }
            r = requests.post("https://api.openai.com/v1/images/generations", json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                img_url = r.json()["data"][0]["url"]
                r_img = requests.get(img_url, timeout=30)
                if r_img.status_code == 200:
                    img_content = r_img.content
                else:
                    return f"Erreur lors du téléchargement de l'image DALL-E 3 (HTTP {r_img.status_code})"
            else:
                err_msg = r.json().get("error", {}).get("message", "Erreur inconnue")
                return f"Erreur DALL-E 3 : {err_msg}"

        # =========================================================================
        # 2. MOTEUR STABILITY AI CORE
        # =========================================================================
        elif provider == "stability":
            stability_key = os.environ.get("STABILITY_API_KEY", "").strip()
            if not stability_key:
                return "❌ Erreur : Vous avez choisi le moteur **Stability AI** mais votre clé `STABILITY_API_KEY` n'est pas configurée dans les paramètres !"
            
            engine_name = "Stability AI Core"
            url = "https://api.stability.ai/v2beta/stable-image/generate/core"
            headers = {
                "authorization": f"Bearer {stability_key}",
                "accept": "image/*"
            }
            files = {
                "prompt": (None, prompt),
                "output_format": (None, "png"),
                "aspect_ratio": (None, "1:1")
            }
            r = requests.post(url, headers=headers, files=files, timeout=60)
            if r.status_code == 200:
                img_content = r.content
            else:
                err_msg = r.json().get("errors", ["Erreur inconnue"])[0]
                return f"Erreur Stability AI : {err_msg}"

        # =========================================================================
        # 3. MOTEUR GOOGLE GEMINI (IMAGEN 3)
        # =========================================================================
        elif provider == "gemini":
            gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not gemini_key:
                return "❌ Erreur : Vous avez choisi le moteur **Google Gemini** mais votre clé `GEMINI_API_KEY` n'est pas configurée dans les paramètres !"
            
            engine_name = "Google Gemini Imagen 3"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:generateImages?key={gemini_key}"
            headers = {
                "Content-Type": "application/json"
            }
            payload = {
                "prompt": prompt,
                "numberOfImages": 1,
                "outputMimeType": "image/jpeg",
                "aspectRatio": "1:1"
            }
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                img_b64 = data["generatedImages"][0]["image"]["imageBytes"]
                img_content = base64.b64decode(img_b64)
            else:
                try:
                    err_msg = r.json().get("error", {}).get("message", "Erreur inconnue")
                except Exception:
                    err_msg = f"HTTP {r.status_code}"
                return f"Erreur Google Gemini Imagen 3 : {err_msg}"

        # =========================================================================
        # 4. MOTEUR ENDPOINT CUSTOM / LOCAL / BANANA
        # =========================================================================
        elif provider == "custom":
            custom_base = os.environ.get("CUSTOM_IMAGE_API_BASE", "").strip()
            custom_key = os.environ.get("CUSTOM_IMAGE_API_KEY", "").strip()
            if not custom_base:
                return "❌ Erreur : Vous avez choisi le moteur **Custom** mais l'URL `CUSTOM_IMAGE_API_BASE` n'est pas configurée dans les paramètres !"
            
            engine_name = "Endpoint Custom / Local"
            endpoint = custom_base
            if not endpoint.endswith("/images/generations"):
                endpoint = endpoint.rstrip("/") + "/images/generations"
                
            headers = {
                "Content-Type": "application/json"
            }
            if custom_key:
                headers["Authorization"] = f"Bearer {custom_key}"
                
            payload = {
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024"
            }
            r = requests.post(endpoint, json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                img_obj = data["data"][0]
                if "url" in img_obj:
                    img_url = img_obj["url"]
                    r_img = requests.get(img_url, timeout=30)
                    if r_img.status_code == 200:
                        img_content = r_img.content
                    else:
                        return f"Erreur de téléchargement Custom (HTTP {r_img.status_code})"
                elif "b64_json" in img_obj:
                    img_content = base64.b64decode(img_obj["b64_json"])
                else:
                    return "Erreur : Format de réponse Custom non supporté (ni 'url' ni 'b64_json' trouvés)."
            else:
                try:
                    err_msg = r.json().get("error", {}).get("message", "Erreur inconnue")
                except Exception:
                    err_msg = f"HTTP {r.status_code}"
                return f"Erreur Endpoint Custom : {err_msg}"

        # =========================================================================
        # 5. MOTEUR POLLINATIONS AI (GRATUIT & ROBUSTE)
        # =========================================================================
        else:
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&private=true"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            r = requests.get(url, headers=headers, timeout=25)
            if r.status_code == 200:
                img_content = r.content
            else:
                return f"Erreur lors de la génération d'image Pollinations (HTTP {r.status_code})."

        # =========================================================================
        # ENREGISTREMENT ET FINALISATION
        # =========================================================================
        if img_content:
            with open(filename, "wb") as f:
                f.write(img_content)
                
            return (
                f"Image générée avec succès via **{engine_name}** ! 🎉\n"
                f"💾 Enregistrée sous le nom : `{filename}` dans le projet.\n"
                f"👉 Tu peux la voir, la prévisualiser et la télécharger directement depuis l'onglet 'Espace Fichiers' à gauche !"
            )
        else:
            return "❌ Erreur : Données d'image corrompues."

    except Exception as e:
        return f"Erreur lors de la génération d'image : {str(e)}"
