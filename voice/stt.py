"""Reconnaissance vocale (STT) locale via faster-whisper."""


class STTUnavailable(RuntimeError):
    pass


class STT:
    def __init__(self, model="base", device="cpu", compute="int8", language="fr"):
        self.model_name = model
        self.device = device
        self.compute = compute
        self.language = language
        self._model = None

    def _ensure(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise STTUnavailable(
                "faster-whisper non installé. `pip install faster-whisper` "
                "(voir requirements-voice.txt)."
            ) from e
        self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute)

    def transcribe(self, audio) -> str:
        """audio : chemin .wav OU tableau numpy float32 mono @16kHz. Renvoie le texte."""
        self._ensure()
        segments, _info = self._model.transcribe(
            audio, language=self.language, vad_filter=True
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
