"""Gestion de la VUE LLM du contexte (mixin) : compaction d'historique et éviction des
gros résultats d'outils déjà exploités. N'altère JAMAIS l'historique persistant — seulement
ce qui est ré-envoyé au modèle à chaque tour (économie de tokens / latence).

Méthodes de `Swarm` (s'appuient sur `self._complete` / `self._utility_model`).
"""
import json
import os


class _ContextMixin:
    """Compaction + éviction de la vue LLM, mélangées dans `Swarm`."""

    def _maybe_compact(self, model: str, history: list, steps: list) -> list:
        """Compacte un historique trop long : résume les anciens messages en un
        seul, garde les plus récents verbatim. N'agit que sur la vue LLM.
        Activé par MEMORY_MAX_MESSAGES (0 = désactivé). Résultats mis en cache
        pour ne pas re-résumer le même bloc à chaque tour."""
        max_msgs = int(os.getenv("MEMORY_MAX_MESSAGES", "15") or 0)
        if not max_msgs or len(history) <= max_msgs:
            return history
        keep = max(1, int(os.getenv("MEMORY_KEEP_RECENT", "5")))
        head, tail = history[:-keep], history[-keep:]
        if not head:
            return history

        cache = getattr(self, "_summary_cache", None)
        if cache is None:
            cache = self._summary_cache = {}

        try:
            key = json.dumps(head, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            key = str(len(head))

        summary = cache.get(key)
        if summary is None:
            transcript = "\n".join(
                f"{m.get('role')}: {m.get('content', '')}" for m in head if m.get("content")
            )[:8000]
            try:
                resp = self._complete(self._utility_model(model), [
                    {"role": "system", "content": (
                        "Résume la conversation suivante en 10 lignes maximum, en français, "
                        "en conservant les faits, décisions, préférences utilisateur et le "
                        "contexte utiles à la poursuite. Style condensé, pas de bavardage."
                    )},
                    {"role": "user", "content": transcript},
                ])
                summary = (resp.choices[0].message.content or "").strip()
            except Exception as e:
                print(f"[\033[91mCompaction mémoire erreur\033[0m] {e}")
                return history  # en cas d'échec, on garde l'historique complet
            cache[key] = summary
            if len(cache) > 64:
                cache.pop(next(iter(cache)))
            steps.append({"type": "memory_compaction", "summarized": len(head), "kept": len(tail)})
            print(f"[\033[96mMÉMOIRE\033[0m] Historique compacté : {len(head)} messages résumés, {len(tail)} conservés.")

        summary_msg = {
            "role": "user",
            "content": f"[RÉSUMÉ DE LA CONVERSATION PRÉCÉDENTE — {len(head)} messages condensés]\n{summary}",
        }
        return [summary_msg] + tail

    def _evict_large_results(self, history: list) -> list:
        """ÉVICTION des gros résultats d'outils DÉJÀ EXPLOITÉS : un résultat d'outil
        volumineux qui n'est plus dans les derniers échanges (donc déjà lu par le modèle)
        est remplacé par un EXTRAIT tête+queue + un pointeur, au lieu de trimballer tout le
        payload à chaque tour. N'agit que sur la vue LLM (jamais l'historique persistant).
        Les résultats RÉCENTS restent intacts. EVICT_TOOL_RESULT_MAX=0 désactive."""
        cap = int(os.getenv("EVICT_TOOL_RESULT_MAX", "2000") or 0)
        if not cap:
            return history
        keep_recent = max(1, int(os.getenv("EVICT_KEEP_RECENT", "4") or 4))
        n = len(history)
        out = []
        for i, m in enumerate(history):
            c = m.get("content")
            if (m.get("role") == "tool" and i < n - keep_recent
                    and isinstance(c, str) and len(c) > cap):
                name = m.get("name", "outil")
                evicted = (f"{c[:cap // 2]}\n"
                           f"…[résultat « {name} » tronqué : {len(c)} caractères, déjà exploité — "
                           f"extrait tête/queue ; redemande l'outil si tu as besoin du détail]…\n"
                           f"{c[-cap // 4:]}")
                out.append({**m, "content": evicted})
            else:
                out.append(m)
        return out
