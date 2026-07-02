"""Gestion de la VUE LLM du contexte (mixin) : compaction d'historique et éviction des
gros résultats d'outils déjà exploités. N'altère JAMAIS l'historique persistant — seulement
ce qui est ré-envoyé au modèle à chaque tour (économie de tokens / latence).

Méthodes de `Swarm` (s'appuient sur `self._complete` / `self._utility_model`).
"""
import hashlib
import json
import os
from collections import OrderedDict


class _ContextMixin:
    """Compaction + éviction de la vue LLM, mélangées dans `Swarm`."""

    # ------------------------------------------------------------------ #
    # Compaction : RÉSUMÉ ROULANT INCRÉMENTAL À CHECKPOINTS
    # ------------------------------------------------------------------ #
    # Au lieu de re-résumer tout l'historique à chaque tour (coûteux + perte du
    # milieu quand on tronque), on maintient un résumé ÉVOLUTIF et un curseur `M`
    # (nombre de messages déjà pliés dedans). Vue LLM = [résumé(0..M)] + [messages(M..N)].
    #
    # Bornes tokens PAR CONSTRUCTION :
    #  • on ne plie (1 appel LLM) que quand `cutoff - M ≥ batch` → sinon 0 appel,
    #    on rallonge juste la queue verbatim de l'écart (< batch messages) ;
    #  • chaque pli réécrit TOUT le résumé sous un plafond de caractères → il n'enfle pas ;
    #  • chaque message du bloc plié est clippé → un bloc de pli reste borné ;
    #  • `max_folds`/tour amortit la reconstruction à froid (après redémarrage) sur
    #    plusieurs tours au lieu d'un pic d'appels.
    #
    # État en RAM sur l'instance Swarm (perdu au redémarrage = reconstruit paresseusement,
    # comme l'ancien cache). Checkpoints indexés par SIGNATURE du préfixe `hash(history[:M])` :
    # stable car l'historique est append-only le long d'une branche ; on vérifie la signature
    # avant réutilisation → une branche divergente recalcule proprement (pas de contamination).

    @staticmethod
    def _hist_sig(history: list, n: int) -> str:
        """Signature stable des `n` premiers messages (rôle + contenu)."""
        try:
            payload = json.dumps(
                [{"r": m.get("role"), "c": m.get("content"), "n": m.get("name")}
                 for m in history[:n]],
                ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            payload = repr(history[:n])
        return hashlib.sha1(payload.encode("utf-8", "replace")).hexdigest()  # nosec B324 — clé de cache, pas de la crypto

    def _find_checkpoint(self, history: list, cutoff: int):
        """Meilleur checkpoint réutilisable : le plus AVANCÉ (len max) dont la signature
        de préfixe correspond encore à l'historique courant et dont len ≤ cutoff."""
        store = getattr(self, "_roll_checkpoints", None)
        if not store:
            return None
        best = None
        for entry in store.values():
            L = entry["len"]
            if L > cutoff or (best and L <= best["len"]):
                continue
            if self._hist_sig(history, L) == entry["sig"]:
                best = entry
        return best

    def _store_checkpoint(self, history: list, m: int, summary: str) -> None:
        store = getattr(self, "_roll_checkpoints", None)
        if store is None:
            store = self._roll_checkpoints = OrderedDict()
        sig = self._hist_sig(history, m)
        store[sig] = {"len": m, "sig": sig, "summary": summary}
        store.move_to_end(sig)
        cap = max(8, int(os.getenv("MEMORY_CHECKPOINTS_MAX", "64") or 64))
        while len(store) > cap:
            store.popitem(last=False)

    def _fold(self, model: str, prev_summary, block: list, steps: list):
        """Plie un bloc de messages bruts dans le résumé roulant (UN appel LLM).
        Renvoie le nouveau résumé, ou `prev_summary` en cas d'échec (jamais None si
        `prev_summary` ne l'était pas)."""
        clip = max(200, int(os.getenv("MEMORY_MSG_CLIP_CHARS", "2000") or 2000))
        lines = []
        for m in block:
            c = m.get("content")
            if not c:
                continue
            if not isinstance(c, str):
                c = json.dumps(c, ensure_ascii=False, default=str)
            if len(c) > clip:
                c = c[:clip] + " …[tronqué]"
            who = m.get("name") or m.get("role") or "?"
            lines.append(f"{who}: {c}")
        transcript = "\n".join(lines)
        if not transcript.strip():
            return prev_summary
        max_chars = max(400, int(os.getenv("MEMORY_SUMMARY_MAX_CHARS", "2000") or 2000))
        try:
            resp = self._complete(self._utility_model(model), [
                {"role": "system", "content": (
                    "Tu maintiens un RÉSUMÉ ÉVOLUTIF d'une conversation. On te donne le résumé "
                    "ACTUEL (peut être vide) puis de NOUVEAUX messages. Produis le résumé MIS À JOUR, "
                    "en français, style condensé, sans bavardage. CONSERVE tous les faits, décisions, "
                    "préférences de l'utilisateur, identités, chiffres, engagements et contexte durables "
                    "— ANCIENS (déjà dans le résumé) COMME nouveaux. N'invente jamais rien. "
                    f"Reste sous {max_chars} caractères."
                )},
                {"role": "user", "content": (
                    f"RÉSUMÉ ACTUEL :\n{prev_summary or '(vide)'}\n\nNOUVEAUX MESSAGES :\n{transcript}"
                )},
            ])
            new = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[\033[91mCompaction mémoire erreur\033[0m] {e}")
            return prev_summary
        if not new:
            return prev_summary
        if len(new) > max_chars:
            new = new[:max_chars].rstrip() + " …"
        steps.append({"type": "memory_compaction", "folded": len(block)})
        return new

    def _maybe_compact(self, model: str, history: list, steps: list) -> list:
        """Compacte un historique trop long via un RÉSUMÉ ROULANT INCRÉMENTAL.
        N'agit que sur la vue LLM (jamais l'historique persistant).
        Activé par MEMORY_MAX_MESSAGES (0 = désactivé)."""
        max_msgs = int(os.getenv("MEMORY_MAX_MESSAGES", "15") or 0)
        if not max_msgs or len(history) <= max_msgs:
            return history
        keep = max(1, int(os.getenv("MEMORY_KEEP_RECENT", "5")))
        n = len(history)
        cutoff = n - keep
        if cutoff <= 0:
            return history
        batch = max(1, int(os.getenv("MEMORY_FOLD_BATCH", str(keep)) or keep))
        max_folds = max(1, int(os.getenv("MEMORY_MAX_FOLDS_PER_TURN", "6") or 6))

        ck = self._find_checkpoint(history, cutoff)
        m = ck["len"] if ck else 0
        summary = ck["summary"] if ck else None

        # Replie par blocs bornés jusqu'à rattraper `cutoff` (à < batch près), sans dépasser
        # `max_folds` appels ce tour-ci (le reste sera plié aux tours suivants).
        folds = 0
        while cutoff - m >= batch and folds < max_folds:
            end = m + batch
            new_summary = self._fold(model, summary, history[m:end], steps)
            if new_summary is summary or new_summary is None:
                # Échec du pli : on ne fait pas avancer le curseur (l'écart partira verbatim).
                break
            summary = new_summary
            m = end
            self._store_checkpoint(history, m, summary)
            folds += 1

        if summary is None:
            # Rien n'a pu être résumé (écart < batch et pas de checkpoint, ou 1er pli en échec).
            return history

        summary_msg = {
            "role": "user",
            "content": f"[RÉSUMÉ DE LA CONVERSATION — {m} messages condensés]\n{summary}",
        }
        view = [summary_msg] + history[m:n]
        if folds:
            print(f"[\033[96mMÉMOIRE\033[0m] Résumé roulant : {m} messages condensés, "
                  f"{n - m} conservés verbatim ({folds} pli(s) ce tour).")
        return view

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
