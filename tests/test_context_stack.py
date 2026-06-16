"""Tests : pile de contextes (« fil d'Ariane ») PUSH/POP sur l'arbre de session.

Exécution : python3 tests/test_context_stack.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_push_pop_cycle():
    from core import channels
    from core.state import sessions
    import core.context_stack as cs
    import tools.context_tools as ct

    cid = "test-ctx"
    channels.current_channel.set(cid)
    sess = sessions.get(cid)
    sess.reset()
    sess.messages = [{"id": "v1", "parent_id": None, "role": "user", "content": "VLAN"}]
    sess.active_node_id = "v1"

    assert cs.depth(sess.client_id) == 0
    ct.open_context("debug DB")
    assert sess.active_node_id is None, "PUSH doit repartir sur une branche neuve"
    assert cs.depth(sess.client_id) == 1
    assert cs.topics(sess.client_id) == ["debug DB"]

    out = ct.close_context()
    assert sess.active_node_id == "v1", "POP doit restaurer le nœud parqué"
    assert cs.depth(sess.client_id) == 0
    assert "principale" in out
    print("OK: cycle PUSH/POP restaure le fil parqué")


def test_nested_lifo():
    from core import channels
    from core.state import sessions
    import core.context_stack as cs
    import tools.context_tools as ct

    cid = "test-ctx2"
    channels.current_channel.set(cid)
    sess = sessions.get(cid)
    sess.reset()
    sess.messages = [{"id": "a", "parent_id": None, "role": "user", "content": "A"}]
    sess.active_node_id = "a"

    ct.open_context("B")
    sess.messages = sess.messages + [{"id": "b", "parent_id": None, "role": "user", "content": "B"}]
    sess.active_node_id = "b"
    ct.open_context("C")
    assert cs.depth(sess.client_id) == 2

    ct.close_context()                 # ferme C -> retour B
    assert sess.active_node_id == "b"
    ct.close_context()                 # ferme B -> retour A
    assert sess.active_node_id == "a"
    assert cs.depth(sess.client_id) == 0
    assert "vide" in ct.close_context()  # plus rien à dépiler
    print("OK: imbrication LIFO correcte")


if __name__ == "__main__":
    test_push_pop_cycle()
    test_nested_lifo()
    print("\n✅ test_context_stack OK")
