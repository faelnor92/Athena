"""Détection de mot-clé d'activation (wake word).

Moteurs supportés :
  - "openwakeword" : local, libre, recommandé.
  - "porcupine"    : Picovoice (nécessite une clé d'accès).
  - "none"         : pas de wake word, activation par la touche Entrée (push-to-talk).
"""


class WakeWordUnavailable(RuntimeError):
    pass


def _norm(s: str) -> str:
    """Minuscule + sans accents + sans ponctuation (pour comparer des transcriptions)."""
    import unicodedata
    import re
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def phrase_in_text(text: str, phrase: str) -> bool:
    """Vrai si le mot d'activation apparaît dans la transcription (tolérant aux
    accents/variantes phonétiques courantes, ex. « athena »/« athéna »/« atena »)."""
    t = _norm(text)
    p = _norm(phrase).strip()
    if not p:
        return False
    if p in t:
        return True
    # Petites variantes phonétiques pour les noms courants.
    variants = {p}
    if "athena" in p:
        variants |= {"atena", "atena", "atenna", "athina", "atina", "hathena"}
    return any(v in t for v in variants)


class WakeWord:
    def __init__(self, engine="openwakeword", wake_word="hey athena",
                 porcupine_key="", sample_rate=16000):
        self.engine = engine
        self.wake_word = wake_word
        self.porcupine_key = porcupine_key
        self.sample_rate = sample_rate
        self._impl = None

    @property
    def enabled(self) -> bool:
        return self.engine not in ("none", "", None)

    def _ensure(self):
        if self._impl is not None or not self.enabled:
            return
        if self.engine == "openwakeword":
            try:
                from openwakeword.model import Model
            except ImportError as e:
                raise WakeWordUnavailable(
                    "openwakeword non installé (`pip install openwakeword`)."
                ) from e
            import os
            # Backend ONNX par défaut : tflite-runtime n'a pas de wheel pour Python ≥3.10
            # (dont 3.13), alors qu'onnxruntime oui. Surchargeable via OWW_INFERENCE_FRAMEWORK.
            _fw = os.getenv("OWW_INFERENCE_FRAMEWORK", "onnx")
            self._impl = ("oww", Model(inference_framework=_fw))
        elif self.engine == "porcupine":
            try:
                import pvporcupine
            except ImportError as e:
                raise WakeWordUnavailable("pvporcupine non installé.") from e
            if not self.porcupine_key:
                raise WakeWordUnavailable("VOICE_PORCUPINE_KEY requis pour Porcupine.")
            handle = pvporcupine.create(access_key=self.porcupine_key,
                                        keywords=[self.wake_word.split()[-1]])
            self._impl = ("porcupine", handle)
        else:
            raise WakeWordUnavailable(f"Moteur wake word inconnu : {self.engine}")

    def detect(self, frame_int16) -> bool:
        """frame_int16 : tableau numpy int16. Renvoie True si le wake word est détecté."""
        if not self.enabled:
            return False
        self._ensure()
        kind, impl = self._impl
        if kind == "oww":
            preds = impl.predict(frame_int16)
            return any(score > 0.5 for score in preds.values())
        if kind == "porcupine":
            return impl.process(frame_int16) >= 0
        return False
