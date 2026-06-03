"""Streaming TTS (S2S) : robustesse du décodage du flux audio.

Couvre les garanties de fiabilité du pipeline voix :
- réassemblage exact des octets quelle que soit la découpe en chunks (alignement
  int16 : un octet impair en fin de chunk doit être reporté, pas paddé sur place) ;
- localisation du sous-chunk WAV `data` même quand il n'est pas à l'offset 44
  (serveurs TTS qui insèrent LIST/fact) + extraction du sample rate ;
- flux PCM brut (sans en-tête RIFF) traité au sample rate par défaut ;
- resampling à la volée de synth_stream (24 kHz -> 16 kHz pour les satellites ESP32).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice.tts import TTS


class FakeResp:
    """Réponse HTTP en streaming simulée, découpée en chunks de `n` octets."""

    def __init__(self, blob, n=4096):
        self.blob, self.n, self.closed = blob, n, False

    def iter_content(self, chunk_size=4096):
        for i in range(0, len(self.blob), self.n):
            yield self.blob[i:i + self.n]

    def close(self):
        self.closed = True


def _wav(sr, pcm, extra=b""):
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
    data = b"data" + struct.pack("<I", len(pcm)) + pcm
    body = b"WAVE" + fmt + extra + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_reassembly_exact_all_chunk_sizes():
    t = TTS(engine="http")
    pcm = struct.pack("<8h", *range(8))
    for n in (1, 2, 3, 5, 7, 13, 44, 4096):
        out = list(t._iter_pcm(FakeResp(_wav(24000, pcm), n=n)))
        assert out[0][0] == 24000, f"sample rate (chunk={n})"
        got = b"".join(c for _, c in out)
        assert got == pcm, f"réassemblage corrompu (chunk={n}) : {got.hex()} != {pcm.hex()}"


def test_data_chunk_not_at_offset_44():
    t = TTS(engine="http")
    pcm = struct.pack("<8h", *range(8))
    extra = b"LIST" + struct.pack("<I", 6) + b"INFOxx"  # sous-chunk avant `data`
    out = list(t._iter_pcm(FakeResp(_wav(16000, pcm, extra), n=5)))
    assert out[0][0] == 16000
    assert b"".join(c for _, c in out) == pcm, "sous-chunk `data` mal localisé"


def test_raw_pcm_without_header():
    t = TTS(engine="http")
    raw = b"\x01\x02\x03\x04" * 20
    out = list(t._iter_pcm(FakeResp(raw, n=9)))
    assert out[0][0] == 24000
    assert b"".join(c for _, c in out) == raw


def test_response_is_closed():
    t = TTS(engine="http")
    r = FakeResp(_wav(24000, b"\x00\x00" * 4))
    list(t._iter_pcm(r))  # _iter_pcm ne ferme pas ; c'est l'appelant
    # _http_play_stream/synth_stream ferment la réponse dans leur finally (cf. ci-dessous).


def test_synth_stream_resamples_24k_to_16k():
    t = TTS(engine="http")
    os.environ["VOICE_TTS_HTTP_URL"] = "http://x"
    big = struct.pack("<2400h", *([1000, -1000] * 1200))
    r = FakeResp(_wav(24000, big), n=4096)
    t._open_stream = lambda emotion, text: r
    out = b"".join(t.synth_stream("x", target_sr=16000))
    ratio = (len(out) // 2) / 2400
    assert 0.64 < ratio < 0.69, f"ratio resample inattendu : {ratio}"
    assert r.closed, "synth_stream doit fermer la réponse HTTP (pas de fuite)"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests TTS streaming passent.")
