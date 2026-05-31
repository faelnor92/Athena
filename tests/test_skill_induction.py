"""Tests : sûreté du validateur de compétences auto-induites + flux d'induction.

Exécution : python3 tests/test_skill_induction.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.skills_manager import validate_pure_skill


def test_validateur_accepte_fonction_pure():
    ok, _ = validate_pure_skill(
        'import math\ndef calc_tva(montant, taux=20.0):\n    "TVA"\n    return round(montant * taux / 100, 2)',
        "calc_tva")
    assert ok, "une fonction pure légitime doit être acceptée"
    print("OK: fonction pure acceptée")


def test_validateur_rejette_dangers():
    dangers = [
        ('import os\ndef bad(x):\n    return os.system(x)', "bad", "import os"),
        ('def bad(p):\n    return open(p).read()', "bad", "open"),
        ('def bad(s):\n    return eval(s)', "bad", "eval"),
        ('def bad():\n    return ().__class__.__bases__', "bad", "dunder"),
        ('def f(x):\n    return x\nprint("boom")', "f", "code au niveau module"),
        ('import requests\ndef f():\n    return requests.get("http://x")', "f", "import requests"),
    ]
    for code, name, why in dangers:
        ok, reason = validate_pure_skill(code, name)
        assert not ok, f"DANGER non bloqué ({why}) : {code!r}"
    print("OK: tous les patterns dangereux sont rejetés")


def test_fonction_absente_rejetee():
    ok, _ = validate_pure_skill('import math\ndef autre(x):\n    return x', "calc_tva")
    assert not ok, "doit exiger la fonction du bon nom"
    print("OK: fonction manquante rejetée")


def test_induction_complete_et_refus():
    """Le flux _induce_skill enregistre une skill pure et refuse du code dangereux."""
    os.environ["SELF_IMPROVE"] = "true"
    os.environ["SELF_IMPROVE_SKILLS"] = "true"
    import core.swarm as cs
    from core.agent import Agent
    import tools.skills_manager as sm

    saved = {}
    sm.save_new_skill = lambda n, c, d: saved.update({"name": n}) or "Succès : ok"
    cs.load_dynamic_skills = lambda: {}

    s = cs.Swarm.__new__(cs.Swarm)
    agent = Agent(name="Codeur", system_prompt="x", model="gpt-4o")

    def _resp(content):
        class _M: pass
        m = _M(); m.content = content
        class _C: pass
        c = _C(); c.message = m
        class _R: pass
        r = _R(); r.choices = [c]
        return r

    # Skill pure valide -> enregistrée
    s._complete = lambda model, msgs, tools_schema=None: _resp(
        '{"skill": true, "name": "calc_remise", "description": "remise",'
        ' "code": "def calc_remise(prix, pct):\\n    \\"r\\"\\n    return round(prix*(1-pct/100), 2)"}')
    steps = [{"type": "tool_call"}]
    s._induce_skill(agent, [{"role": "user", "content": "remise 10% sur 50"}], steps)
    assert saved.get("name") == "calc_remise", "la skill pure aurait dû être enregistrée"
    assert any(st.get("type") == "skill_learned" for st in steps)

    # Code dangereux -> refusé
    saved.clear()
    s._complete = lambda model, msgs, tools_schema=None: _resp(
        '{"skill": true, "name": "pirate", "description": "x",'
        ' "code": "import os\\ndef pirate(c):\\n    return os.system(c)"}')
    s._induce_skill(agent, [{"role": "user", "content": "..."}], [{"type": "tool_call"}])
    assert not saved, "le code dangereux ne doit JAMAIS être enregistré"
    print("OK: induction enregistre le pur, refuse le dangereux")


if __name__ == "__main__":
    test_validateur_accepte_fonction_pure()
    test_validateur_rejette_dangers()
    test_fonction_absente_rejetee()
    test_induction_complete_et_refus()
