"""Robustesse : les blocs de réflexion sont masqués quel que soit le délimiteur émis par le
modèle — <thought>…</thought> (consigne) ET [thought]…[/thought] (qwen & co.)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from core.swarm.engine import strip_thoughts  # noqa: E402


@pytest.mark.parametrize("inp,exp", [
    ("[emotion: enjoué] Bonjour", "Bonjour"),
    ("(ton: calme) Salut", "Salut"),
    ("[emotion:excité]Ça marche", "Ça marche"),
    ("Aucun tag d'émotion", "Aucun tag d'émotion"),
])
def test_strip_emotion_tags(inp, exp):
    from core.swarm.engine import strip_emotion_tags
    assert strip_emotion_tags(inp) == exp


@pytest.mark.parametrize("inp,exp", [
    ("<thought>x</thought>Réponse", "Réponse"),
    ("<thinking>x</thinking>Réponse", "Réponse"),
    ("[thought]x[/thought]Réponse", "Réponse"),          # crochets (cas observé en prod)
    ("[THINKING]x[/THINKING]  Salut", "Salut"),          # casse insensible
    ("[thought]tronqué sans balise de fin", ""),         # ouverture non fermée
    ("<thought>incomplet", ""),
    ("Aucun bloc ici", "Aucun bloc ici"),
])
def test_strip_thoughts(inp, exp):
    assert strip_thoughts(inp) == exp
