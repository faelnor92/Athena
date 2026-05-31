"""Modélisation de l'utilisateur : un profil curé qui s'enrichit au fil des échanges.

Contrairement aux faits clé-valeur (CoreMemory), c'est un texte synthétique et évolutif
(préférences, ton, contexte projet, habitudes) réinjecté dans le system prompt pour
personnaliser durablement les réponses — équivalent du « user modeling » de Hermes.
"""
import os
import threading


class UserProfile:
    def __init__(self, path: str = None):
        self.path = path or os.getenv("USER_PROFILE_PATH", "user_profile.md")
        self._lock = threading.Lock()

    def get(self) -> str:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""
        except Exception:
            return ""

    def set(self, text: str):
        with self._lock:
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write((text or "").strip() + "\n")
            except Exception as e:
                print(f"[Profil utilisateur] écriture impossible : {e}")

    def as_prompt(self) -> str:
        prof = self.get()
        if not prof:
            return ""
        return ("\n=== PROFIL UTILISATEUR (à respecter pour personnaliser tes réponses) ===\n"
                f"{prof}\n===============================================================\n")

    def update_from_exchange(self, transcript: str, complete_fn, model: str):
        """Met à jour le profil à partir d'un nouvel échange via un appel LLM.
        complete_fn(model, messages) doit renvoyer un objet réponse type OpenAI."""
        current = self.get() or "(profil vide)"
        try:
            resp = complete_fn(model, [
                {"role": "system", "content": (
                    "Tu maintiens un PROFIL UTILISATEUR concis et durable. À partir du profil actuel "
                    "et du nouvel échange, renvoie le profil MIS À JOUR : conserve les infos stables, "
                    "ajoute les préférences/faits/contexte durables NOUVEAUX, corrige ce qui est "
                    "contredit, supprime l'éphémère. Format : puces courtes, < 250 mots, en français. "
                    "N'invente rien. Si rien de durable n'a changé, renvoie EXACTEMENT le profil actuel."
                )},
                {"role": "user", "content": f"PROFIL ACTUEL :\n{current}\n\nNOUVEL ÉCHANGE :\n{transcript}"},
            ])
            new = (resp.choices[0].message.content or "").strip()
            # Garde-fous : non vide, taille raisonnable, et réellement différent.
            if new and len(new) < 4000 and new != current and new != "(profil vide)":
                self.set(new)
                return True
        except Exception as e:
            print(f"[Profil utilisateur] mise à jour impossible : {e}")
        return False


# Singleton.
user_profile = UserProfile()
