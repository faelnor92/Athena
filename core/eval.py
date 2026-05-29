"""Évaluation et rejeu de runs.

- replay_run : ré-exécute le message utilisateur d'un run persisté et renvoie une
  comparaison ancien/nouveau (utile pour inspecter/diagnostiquer un run raté).
- run_eval : harnais d'éval minimal — exécute une liste de cas et vérifie des
  assertions simples (la réponse contient X / l'agent final est Y / l'outil Z a
  été utilisé).

Indépendant du serveur : utilisable en CLI (voir eval_runner.py) avec un objet
Swarm fourni.
"""
import time
from typing import Any, Dict, List

from core.tracing import run_store
from core.run_context import registry, current_run_id


def _sum_tokens(steps: List[dict]) -> int:
    return sum(
        (s.get("prompt_tokens", 0) + s.get("completion_tokens", 0))
        for s in steps if s.get("type") == "usage"
    )


def _final_response(steps: List[dict]) -> str:
    for s in reversed(steps):
        if s.get("type") == "message":
            return s.get("content", "")
    return ""


def _run_once(swarm, message: str, start_agent: str = "Jarvis"):
    """Exécute un message dans un run isolé et renvoie (agent, steps, response)."""
    starting = swarm.agents.get(start_agent) or swarm.agents.get("Jarvis") \
        or next(iter(swarm.agents.values()))
    rid = run_store.new_run_id()
    started = time.time()
    token = current_run_id.set(rid)
    registry.start(rid)
    try:
        agent, _messages, steps = swarm.run(starting, [{"role": "user", "content": message}])
        steps_list = list(steps)
        resp = _final_response(steps_list)
        return rid, started, agent, steps_list, resp
    finally:
        registry.finish(rid)
        current_run_id.reset(token)


def replay_run(swarm, run_id: str, persist: bool = True) -> Dict[str, Any]:
    original = run_store.get(run_id)
    if not original:
        return {"error": f"Run '{run_id}' introuvable."}
    user_message = original.get("user_message", "") or ""

    rid, started, agent, steps, resp = _run_once(swarm, user_message)
    if persist:
        run_store.save(
            run_id=rid, agent=agent.name, status="replay",
            user_message=user_message, final_response=resp,
            duration_ms=int((time.time() - started) * 1000),
            total_tokens=_sum_tokens(steps), steps=steps, created_at=started,
        )
    return {
        "replay_of": run_id,
        "new_run_id": rid,
        "agent": agent.name,
        "original_response": original.get("final_response", ""),
        "new_response": resp,
    }


def _evaluate_case(case: dict, agent_name: str, resp: str, tools_used: set) -> Dict[str, Any]:
    checks = []
    ok = True
    if "expect_contains" in case:
        c = case["expect_contains"].lower() in (resp or "").lower()
        checks.append({"type": "contains", "expected": case["expect_contains"], "ok": c})
        ok = ok and c
    if "expect_agent" in case:
        c = agent_name == case["expect_agent"]
        checks.append({"type": "agent", "expected": case["expect_agent"], "got": agent_name, "ok": c})
        ok = ok and c
    if "expect_tool" in case:
        c = case["expect_tool"] in tools_used
        checks.append({"type": "tool", "expected": case["expect_tool"], "ok": c})
        ok = ok and c
    return {"passed": ok, "checks": checks}


def run_eval(swarm, cases: List[dict]) -> Dict[str, Any]:
    results = []
    for case in cases:
        message = case.get("message", "")
        start_agent = case.get("start_agent", "Jarvis")
        try:
            _rid, _started, agent, steps, resp = _run_once(swarm, message, start_agent)
            tools_used = {s.get("tool") for s in steps if s.get("type") == "tool_call"}
            verdict = _evaluate_case(case, agent.name, resp, tools_used)
            results.append({
                "name": case.get("name", message[:40]),
                "message": message,
                "passed": verdict["passed"],
                "checks": verdict["checks"],
                "response": (resp or "")[:300],
            })
        except Exception as e:
            results.append({"name": case.get("name", message[:40]), "message": message,
                            "passed": False, "error": str(e)})
    passed = sum(1 for r in results if r.get("passed"))
    return {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}
