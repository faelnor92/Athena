import os
import time
import uuid
import requests
import urllib.parse
import base64

# En-têtes HTTP simulant un navigateur standard pour contourner les limitations de sécurité
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def ensure_generator_directories():
    """ Assure que les répertoires d'images et vidéos existent dans le workspace. """
    os.makedirs("workspace/generated_images", exist_ok=True)
    os.makedirs("workspace/generated_videos", exist_ok=True)

def generate_artistic_image(prompt: str) -> str:
    """
    Génère une image d'art IA haute définition avec support multi-moteurs :
    - Pollinations AI (Gratuit)
    - OpenAI DALL-E 3 (Payant, nécessite OPENAI_API_KEY)
    - Stability AI Core (Payant, nécessite STABILITY_API_KEY)
    - Google Gemini Imagen 3 (Payant, utilise GEMINI_API_KEY)
    - Custom Endpoint (Utilise CUSTOM_IMAGE_API_BASE & CUSTOM_IMAGE_API_KEY)
    
    Applique un recadrage intelligent local (Cinéma 16:9, Portrait 9:16, Carré 1:1)
    et un upscaling Lanczos de qualité 2K.
    """
    from PIL import Image
    import io
    
    ensure_generator_directories()
    
    # Détecter le format souhaité par l'utilisateur
    prompt_lower = prompt.lower()
    if "vertical" in prompt_lower or "portrait" in prompt_lower or "phone" in prompt_lower:
        format_type = "portrait"
        target_w, target_h = 1152, 2048
        format_name = "Portrait 2K (1152x2048)"
    elif "square" in prompt_lower or "1:1" in prompt_lower or "avatar" in prompt_lower:
        format_type = "square"
        target_w, target_h = 2048, 2048
        format_name = "Carré UHD (2048x2048)"
    else:
        format_type = "cinema"
        target_w, target_h = 2048, 1152
        format_name = "Cinéma 2K (2048x1152)"
        
    provider = os.environ.get("IMAGE_GENERATOR_PROVIDER", "pollinations").strip().lower()
    img_data = None
    engine_name = "Pollinations AI (Gratuit)"
    
    print(f"🎨 [Image Gen] Lancement de la génération d'image via le moteur : {provider}")
    
    try:
        # =========================================================================
        # MOTEUR 1 : OPENAI DALL-E 3
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
                "size": "1024x1024",
                "quality": "standard"
            }
            
            r = requests.post("https://api.openai.com/v1/images/generations", json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                img_url = data["data"][0]["url"]
                r_img = requests.get(img_url, timeout=30)
                if r_img.status_code == 200:
                    img_data = r_img.content
                else:
                    return f"❌ Erreur lors du téléchargement de l'image DALL-E 3 (HTTP {r_img.status_code})"
            else:
                err_msg = r.json().get("error", {}).get("message", "Erreur inconnue")
                return f"❌ Erreur DALL-E 3 : {err_msg}"
                
        # =========================================================================
        # MOTEUR 2 : STABILITY AI CORE
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
                img_data = r.content
            else:
                err_msg = r.json().get("errors", ["Erreur inconnue"])[0]
                return f"❌ Erreur Stability AI : {err_msg}"

        # =========================================================================
        # MOTEUR 3 : GOOGLE GEMINI (IMAGEN 3)
        # =========================================================================
        elif provider == "gemini":
            gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not gemini_key:
                return "❌ Erreur : Vous avez choisi le moteur **Google Gemini** mais votre clé `GEMINI_API_KEY` n'est pas configurée dans les paramètres !"
            
            engine_name = "Google Gemini Imagen 3"
            print(f"🎨 [Image Gen] Requête Gemini Imagen 3 pour : '{prompt}'")
            
            # Google AI Studio REST Endpoint pour Imagen 3
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
                img_data = base64.b64decode(img_b64)
            else:
                try:
                    err_msg = r.json().get("error", {}).get("message", "Erreur inconnue")
                except Exception:
                    err_msg = f"HTTP {r.status_code}"
                return f"❌ Erreur Google Gemini Imagen 3 : {err_msg}"

        # =========================================================================
        # MOTEUR 4 : ENDPOINT CUSTOM / LOCAL / BANANA
        # =========================================================================
        elif provider == "custom":
            custom_base = os.environ.get("CUSTOM_IMAGE_API_BASE", "").strip()
            custom_key = os.environ.get("CUSTOM_IMAGE_API_KEY", "").strip()
            if not custom_base:
                return "❌ Erreur : Vous avez choisi le moteur **Custom** mais l'URL `CUSTOM_IMAGE_API_BASE` n'est pas configurée dans les paramètres !"
            
            engine_name = "Endpoint Custom / Local / Banana"
            print(f"🎨 [Image Gen] Requête Custom Endpoint ({custom_base}) pour : '{prompt}'")
            
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
                        img_data = r_img.content
                    else:
                        return f"❌ Erreur de téléchargement depuis Custom URL (HTTP {r_img.status_code})"
                elif "b64_json" in img_obj:
                    img_data = base64.b64decode(img_obj["b64_json"])
                else:
                    return "❌ Erreur : Format de réponse Custom non supporté (ni 'url' ni 'b64_json' trouvés)."
            else:
                try:
                    err_msg = r.json().get("error", {}).get("message", "Erreur inconnue")
                except Exception:
                    err_msg = f"HTTP {r.status_code}"
                return f"❌ Erreur Endpoint Custom : {err_msg}"
                
        # =========================================================================
        # MOTEUR 5 : POLLINATIONS AI (GRATUIT & ROBUSTE)
        # =========================================================================
        else:
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&private=true&enhance=true"
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                img_data = r.content
            else:
                return f"❌ Erreur Pollinations AI (HTTP {r.status_code})"
                
        # =========================================================================
        # RECADRAGE & UPSCALING LANCZOS 2K
        # =========================================================================
        if img_data:
            img = Image.open(io.BytesIO(img_data))
            w, h = img.size
            
            # Recadrage intelligent local
            if format_type == "cinema":
                crop_h = int(w * 9 / 16)
                top = (h - crop_h) // 2
                bottom = top + crop_h
                img = img.crop((0, top, w, bottom))
            elif format_type == "portrait":
                crop_w = int(h * 9 / 16)
                left = (w - crop_w) // 2
                right = left + crop_w
                img = img.crop((left, 0, right, h))
                
            # Super-échantillonnage Lanczos vers résolution cible
            try:
                resampling = Image.Resampling.LANCZOS
            except AttributeError:
                resampling = Image.ANTIALIAS
                
            upscaled_img = img.resize((target_w, target_h), resampling)
            
            filename = f"art_{int(time.time())}_{uuid.uuid4().hex[:6]}.jpg"
            filepath = os.path.join("workspace/generated_images", filename)
            
            upscaled_img.save(filepath, "JPEG", quality=95)
            relative_path = f"workspace/generated_images/{filename}"
            
            print(f"🎨 [Image Gen] Chef-d'œuvre sauvegardé ({engine_name}) : {relative_path}")
            return f"Voici votre œuvre d'art IA générée via **{engine_name}** et upscalée en format **{format_name}** :\n\n![{prompt}](/api/workspace/download?path={relative_path})"
        else:
            return "❌ Erreur : Données d'image corrompues ou indisponibles."
            
    except Exception as e:
        return f"❌ Exception lors de la génération de l'image : {str(e)}"

def generate_artistic_video(prompt: str) -> str:
    """
    Génère une animation de haute qualité avec sélection du type de moteur :
    1. local : Cinémagraphe respirant local à base d'image IA (instant & gratuit).
    2. fal : Hunyuan Video / Luma AI cloud via Fal.ai (asynchrone avec polling).
    3. replicate : Stable Video Diffusion / Hunyuan via Replicate (asynchrone).
    4. custom : Endpoint custom vidéo tiers.
    """
    ensure_generator_directories()
    
    video_provider = os.environ.get("VIDEO_GENERATOR_PROVIDER", "local").strip().lower()
    
    # =========================================================================
    # OPTION A : PRODUCTION VIDÉO CLOUD (FAL.AI / REPLICATE / CUSTOM)
    # =========================================================================
    if video_provider in ["fal", "replicate", "custom"]:
        print(f"🎬 [Video Cloud] Lancement de la génération vidéo cloud ({video_provider}) : '{prompt}'")
        video_url = None
        
        try:
            # ----------------------------------------------------
            # 1. GENERATION VIA FAL.AI
            # ----------------------------------------------------
            if video_provider == "fal":
                fal_key = os.environ.get("FAL_API_KEY", "").strip()
                if not fal_key:
                    print("⚠️ Clé FAL_API_KEY manquante, repli sur le cinémagraphe local.")
                    return compile_local_cinemagraph(prompt, "Fal Key manquante")
                
                url = "https://queue.fal.run/fal-ai/hunyuan-video"
                headers = {
                    "Authorization": f"Key {fal_key}",
                    "Content-Type": "application/json"
                }
                payload = {"prompt": prompt}
                
                # Envoyer la requête asynchrone
                r = requests.post(url, json=payload, headers=headers, timeout=30)
                if r.status_code == 200:
                    req_id = r.json().get("request_id")
                    poll_url = f"https://queue.fal.run/fal-ai/hunyuan-video/requests/{req_id}"
                    
                    # Boucle de polling (max 2 minutes)
                    print(f"🎬 [Video Cloud] Requête Fal soumise (ID: {req_id}). Démarrage du polling...")
                    for _ in range(24):
                        time.sleep(5)
                        r_poll = requests.get(poll_url, headers=headers, timeout=20)
                        if r_poll.status_code == 200:
                            status_data = r_poll.json()
                            # Fal status keys
                            if "logs" in status_data:
                                print(f"🎬 [Video Cloud] Fal logs: {status_data['logs'][-1].get('message') if status_data['logs'] else 'En attente...'}")
                            if "video" in status_data:
                                video_url = status_data["video"].get("url")
                                break
                            elif status_data.get("status") == "COMPLETED":
                                video_url = status_data.get("video", {}).get("url")
                                break
                            elif status_data.get("status") == "FAILED":
                                return f"❌ Erreur de génération Fal.ai : {status_data.get('error', 'Inconnue')}"
                else:
                    return f"❌ Erreur d'initialisation Fal (HTTP {r.status_code})"

            # ----------------------------------------------------
            # 2. GENERATION VIA REPLICATE
            # ----------------------------------------------------
            elif video_provider == "replicate":
                replicate_token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
                if not replicate_token:
                    print("⚠️ Token REPLICATE_API_TOKEN manquant, repli sur le cinémagraphe local.")
                    return compile_local_cinemagraph(prompt, "Replicate Token manquant")
                
                url = "https://api.replicate.com/v1/predictions"
                headers = {
                    "Authorization": f"Token {replicate_token}",
                    "Content-Type": "application/json"
                }
                # Utiliser Hunyuan Video model standard sur Replicate
                payload = {
                    "version": "a827b508f7aa94d4d5e8e815668e146ef9386d755490bc1f308a0d01ad28b80e",
                    "input": {"prompt": prompt}
                }
                
                r = requests.post(url, json=payload, headers=headers, timeout=30)
                if r.status_code == 201:
                    pred_id = r.json().get("id")
                    poll_url = f"https://api.replicate.com/v1/predictions/{pred_id}"
                    
                    # Polling
                    print(f"🎬 [Video Cloud] Requête Replicate soumise (ID: {pred_id}). Polling...")
                    for _ in range(24):
                        time.sleep(5)
                        r_poll = requests.get(poll_url, headers=headers, timeout=20)
                        if r_poll.status_code == 200:
                            pred_data = r_poll.json()
                            status = pred_data.get("status")
                            print(f"🎬 [Video Cloud] Replicate Status: {status}")
                            if status == "succeeded":
                                out = pred_data.get("output")
                                if isinstance(out, list):
                                    video_url = out[0]
                                else:
                                    video_url = out
                                break
                            elif status in ["failed", "canceled"]:
                                return f"❌ Erreur de génération Replicate : {pred_data.get('error', 'Inconnue')}"
                else:
                    return f"❌ Erreur d'initialisation Replicate (HTTP {r.status_code})"

            # ----------------------------------------------------
            # 3. GENERATION VIA ENDPOINT CUSTOM VIDÉO
            # ----------------------------------------------------
            elif video_provider == "custom":
                custom_video_base = os.environ.get("CUSTOM_VIDEO_API_BASE", "").strip()
                custom_video_key = os.environ.get("CUSTOM_VIDEO_API_KEY", "").strip()
                if not custom_video_base:
                    print("⚠️ Endpoint CUSTOM_VIDEO_API_BASE absent, repli sur le cinémagraphe local.")
                    return compile_local_cinemagraph(prompt, "Custom base vide")
                
                headers = {"Content-Type": "application/json"}
                if custom_video_key:
                    headers["Authorization"] = f"Bearer {custom_video_key}"
                    
                payload = {"prompt": prompt}
                r = requests.post(custom_video_base, json=payload, headers=headers, timeout=60)
                if r.status_code == 200:
                    data = r.json()
                    # Tenter d'extraire le champ vidéo ou URL
                    video_url = data.get("video_url") or data.get("url") or data.get("video")
                    if isinstance(video_url, dict):
                        video_url = video_url.get("url")
                else:
                    return f"❌ Erreur Custom Video Endpoint (HTTP {r.status_code})"

            # ----------------------------------------------------
            # TÉLÉCHARGEMENT ET RÉSOU-LOCALISATION DU FICHIER CLOUD
            # ----------------------------------------------------
            if video_url:
                print(f"🎬 [Video Cloud] Téléchargement de la vidéo : {video_url}")
                r_vid = requests.get(video_url, timeout=45)
                if r_vid.status_code == 200:
                    ext = ".mp4"
                    if "gif" in video_url.lower():
                        ext = ".gif"
                        
                    filename = f"video_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
                    filepath = os.path.join("workspace/generated_videos", filename)
                    
                    with open(filepath, "wb") as f:
                        f.write(r_vid.content)
                        
                    relative_path = f"workspace/generated_videos/{filename}"
                    engine_label = video_provider.upper()
                    print(f"🎬 [Video Cloud] Vidéo cloud sauvegardée : {relative_path}")
                    
                    # Renvoyer une balise vidéo html5 si c'est un mp4, ou image si c'est un gif !
                    if ext == ".mp4":
                        return (
                            f"Voici votre vidéo cinématographique générée via **{engine_label} Hunyuan Video** :\n\n"
                            f'<video src="/api/workspace/download?path={relative_path}" controls autoplay loop style="width: 100%; border-radius: 12px; border: 1px solid var(--border-color); box-shadow: 0 8px 32px rgba(0,0,0,0.5);"></video>'
                        )
                    else:
                        return f"Voici votre animation générée via **{engine_label}** :\n\n![{prompt}](/api/workspace/download?path={relative_path})"
                else:
                    return f"❌ Impossible de télécharger la vidéo finale depuis le cloud (HTTP {r_vid.status_code})"
            else:
                return "❌ Erreur : Temps d'attente d'API vidéo dépassé ou réponse vide."
                
        except Exception as e:
            print(f"⚠️ Exception durant la génération cloud : {str(e)}. Repli local.")
            return compile_local_cinemagraph(prompt, f"Exception: {str(e)}")

    # =========================================================================
    # OPTION B : ANIMATION LOCALE INSTANTANÉE (GIF PAR DÉFAUT / REPLI)
    # =========================================================================
    else:
        # Si le fournisseur vidéo est explicitement Gemini, on force temporairement
        # IMAGE_GENERATOR_PROVIDER à "gemini" le temps de générer la graine image
        old_provider = os.environ.get("IMAGE_GENERATOR_PROVIDER")
        if video_provider == "gemini":
            os.environ["IMAGE_GENERATOR_PROVIDER"] = "gemini"
        try:
            reason_label = f"Mode Local Configuré ({video_provider.upper()})"
            return compile_local_cinemagraph(prompt, reason_label)
        finally:
            if old_provider is not None:
                os.environ["IMAGE_GENERATOR_PROVIDER"] = old_provider
            elif "IMAGE_GENERATOR_PROVIDER" in os.environ:
                del os.environ["IMAGE_GENERATOR_PROVIDER"]


def compile_local_cinemagraph(prompt: str, reason: str = "") -> str:
    """
    Compile instantanément un cinémagraphe local GIF en se basant sur une image IA
    produite par le moteur d'images configuré.
    """
    from PIL import Image
    import io
    
    print(f"🎬 [Animation Locale] Lancement du compilateur instantané (Raison : {reason})")
    img_provider = os.environ.get("IMAGE_GENERATOR_PROVIDER", "pollinations").strip().lower()
    
    frames = []
    duration = 200
    
    try:
        # 1. Générer l'image clé HD initiale avec l'API d'image configurée
        res = generate_artistic_image(prompt + ", square format, 1:1, super detailed")
        
        # 2. Extraire le chemin de l'image locale dans le résultat
        import re
        match = re.search(r"path=(workspace/generated_images/art_[a-zA-Z0-9_-]+\.jpg)", res)
        if match:
            key_img_path = match.group(1)
            img = Image.open(key_img_path)
            frames.append(img)
        else:
            # Essayer de récupérer Pollinations en urgence
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&private=true"
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                frames.append(Image.open(io.BytesIO(r.content)))
                
        if len(frames) == 0:
            return "❌ Erreur : Impossible de générer l'image clé initiale pour le cinémagraphe local."
            
        # 3. Créer l'effet de zoom respirant 3D local
        base_img = frames[0]
        
        def zoom_frame(img, factor):
            w, h = img.size
            new_w, new_h = int(w / factor), int(h / factor)
            left = (w - new_w) // 2
            top = (h - new_h) // 2
            right = left + new_w
            bottom = top + new_h
            cropped = img.crop((left, top, right, bottom))
            try:
                resampling = Image.Resampling.LANCZOS
            except AttributeError:
                resampling = Image.ANTIALIAS
            return cropped.resize((w, h), resampling)
            
        factors = [1.0, 1.02, 1.04, 1.06, 1.04, 1.02]
        frames = [zoom_frame(base_img, f) for f in factors]
        
        # 4. Enregistrer l'animation compilée
        filename = f"anim_{int(time.time())}_{uuid.uuid4().hex[:6]}.gif"
        filepath = os.path.join("workspace/generated_videos", filename)
        
        frames[0].save(
            filepath,
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0
        )
        
        relative_path = f"workspace/generated_videos/{filename}"
        print(f"🎬 [Animation Locale] Cinémagraphe compilé avec succès : {relative_path}")
        return f"Voici votre animation GIF générée (*Moteur : Cinémagraphe Respirant {img_provider.upper()}*) :\n\n![{prompt}](/api/workspace/download?path={relative_path})"
        
    except Exception as e:
        return f"❌ Exception lors de la compilation locale : {str(e)}"
