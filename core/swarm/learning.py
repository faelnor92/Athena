"""Hooks d'APPRENTISSAGE post-tâche du Swarm (mixin).

Extraits de l'ancien `core/swarm.py`, ces méthodes tournent en fin de run pour faire
progresser l'assistant sans intervention :
- `_write_experience_report` : retour d'expérience archivé en mémoire sémantique ;
- `_extract_graph_facts`      : Chronos — faits durables → mémoire-graphe ;
- `_update_user_profile`      : profil utilisateur évolutif ;
- `_improve_skills`           : réparation auto des compétences pures qui ont échoué ;
- `_auto_critic`              : passe critique avant livraison ;
- `_induce_skill`             : acquisition d'une nouvelle compétence pure (façon Voyager).

Ce sont des méthodes de `Swarm` : elles s'appuient sur `self._complete` /
`self._utility_model` (définis dans le moteur). Mélangées à `Swarm` via héritage.
"""
import os

from core.agent import Agent
from core.swarm.text_tools import load_dynamic_skills


class _LearningMixin:
    """Méthodes d'auto-amélioration mélangées dans `Swarm` (cf. engine.py)."""

    def _write_experience_report(self, agent: Agent, messages: list, steps: list):
        """Hook post-tâche (auto-amélioration) : génère un court compte-rendu
        structuré (ce qui a marché / échoué / à retenir) et l'archive en mémoire
        sémantique, où il resurgira via le RAG lors d'une tâche similaire."""
        if os.getenv("SELF_IMPROVE", "true").lower() not in ("true", "1", "yes"):
            return
        # On ne produit un retour que pour les tâches non triviales (avec outils/handoffs).
        if not any(s.get("type") in ("tool_call", "handoff") for s in steps):
            return
        try:
            # Reconstruit un transcript compact du dernier échange.
            lines = []
            for m in messages[-12:]:
                role = m.get("role")
                if role == "user":
                    lines.append(f"UTILISATEUR: {m.get('content','')}")
                elif role == "assistant" and m.get("content"):
                    lines.append(f"{m.get('name','assistant')}: {m.get('content','')}")
                elif role == "tool":
                    lines.append(f"OUTIL[{m.get('name','?')}]: {str(m.get('content',''))[:400]}")
            transcript = "\n".join(lines)[:6000]

            report_messages = [
                {"role": "system", "content": (
                    "Tu es un module d'auto-amélioration. À partir de l'échange ci-dessous, rédige un "
                    "COMPTE-RENDU TRÈS COURT (5 lignes max) et factuel, en français, au format :\n"
                    "- Tâche: <résumé en une ligne>\n- A marché: <...>\n- A échoué/limites: <...>\n"
                    "- À retenir pour la prochaine fois: <conseil actionnable>\n"
                    "Si rien d'utile n'est à retenir, réponds exactement: RAS."
                )},
                {"role": "user", "content": transcript},
            ]
            resp = self._complete(agent.model, report_messages, tools_schema=None)
            report = (resp.choices[0].message.content or "").strip()
            if not report or report.upper().startswith("RAS"):
                return
            import tools.memory_tools
            tools.memory_tools.store_document(report, source="retour_experience")
            # Consolidation : borne le nombre de retours d'expérience (anti-bloat RAG).
            try:
                keep = int(os.getenv("EXPERIENCE_MAX", "50") or 50)
                pruned = tools.memory_tools.semantic_mem.prune_source("retour_experience", keep)
                if pruned:
                    print(f"[AUTO-AMÉLIORATION] {pruned} ancien(s) retour(s) élagué(s) (cap {keep}).")
            except Exception:
                pass
            steps.append({"type": "self_improve", "agent": agent.name, "content": report})
            print(f"[\033[96mAUTO-AMÉLIORATION\033[0m] Retour d'expérience archivé.")
        except Exception as e:
            print(f"[\033[91mAuto-amélioration erreur\033[0m] {e}")

    def _extract_graph_facts(self, agent: Agent, messages: list, steps: list):
        """CHRONOS — mémoire relationnelle à long terme. Extrait de l'échange les FAITS
        DURABLES (sujet, relation, objet) sur l'utilisateur, ses proches, lieux, machines
        et préférences, puis les range dans la mémoire-graphe (par-utilisateur). Ignore
        l'éphémère. Gate GRAPH_AUTO_EXTRACT (défaut: activé)."""
        if os.getenv("GRAPH_AUTO_EXTRACT", "true").lower() not in ("true", "1", "yes"):
            return
        try:
            # Assez de matière utilisateur pour qu'il y ait quelque chose à apprendre.
            user_txt = " ".join(str(m.get("content", "") or "") for m in messages if m.get("role") == "user")
            if len(user_txt.strip()) < 15:
                return
            lines = []
            for m in messages[-12:]:
                role = m.get("role")
                if role == "user":
                    lines.append(f"UTILISATEUR: {m.get('content','')}")
                elif role == "assistant" and m.get("content"):
                    lines.append(f"{m.get('name','assistant')}: {m.get('content','')}")
            transcript = "\n".join(lines)[:6000]
            if not transcript.strip():
                return
            prompt = [
                {"role": "system", "content": (
                    "Tu es Chronos, la mémoire à long terme de l'assistant. À partir de l'échange, "
                    "EXTRAIS uniquement les FAITS DURABLES et réutilisables : identité et préférences "
                    "de l'utilisateur, personnes/lieux/appareils/serveurs et leurs RELATIONS. "
                    "IGNORE tout ce qui est éphémère (météo, heure, contenu d'une tâche ponctuelle, "
                    "politesses). Réponds en JSON STRICT, rien d'autre :\n"
                    '{"facts":[{"s":"sujet","r":"relation","o":"objet"}]}\n'
                    "Chaque fait court et atomique (ex. {\"s\":\"serveur de dev\",\"r\":\"est hébergé sur\","
                    "\"o\":\"Dell R430\"}). Si rien de durable : {\"facts\":[]}."
                )},
                {"role": "user", "content": transcript},
            ]
            resp = self._complete(agent.model, prompt, tools_schema=None)
            raw = (resp.choices[0].message.content or "").strip()
            import json as _json, re as _re
            m = _re.search(r"\{.*\}", raw, _re.S)
            if not m:
                return
            data = _json.loads(m.group(0))
            facts = data.get("facts") or []
            triples = [(f.get("s"), f.get("r"), f.get("o")) for f in facts
                       if isinstance(f, dict) and f.get("s") and f.get("o") and f.get("r")]
            if not triples:
                return
            import core.graph_memory as _gm
            n = _gm.add_triples(triples)
            if n:
                steps.append({"type": "graph_learned", "agent": agent.name, "count": n})
                print(f"[\033[96mCHRONOS\033[0m] {n} fait(s) durable(s) ajouté(s) au graphe.")
        except Exception as e:
            print(f"[\033[91mChronos erreur\033[0m] {e}")

    def _update_user_profile(self, agent: Agent, messages: list, steps: list):
        """Met à jour le profil utilisateur évolutif à partir du dernier échange
        (personnalisation durable, façon Hermes/Honcho). Gate USER_MODELING."""
        if os.getenv("USER_MODELING", "true").lower() not in ("true", "1", "yes"):
            return
        try:
            from core.user_profile import user_profile
            lines = []
            for m in messages[-10:]:
                role = m.get("role")
                if role == "user":
                    lines.append(f"UTILISATEUR: {m.get('content','')}")
                elif role == "assistant" and m.get("content"):
                    lines.append(f"ASSISTANT: {m.get('content','')}")
            transcript = "\n".join(lines)[:5000]
            # On ne profile pas les échanges triviaux (évite un appel LLM inutile).
            last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
            if not transcript.strip() or len(str(last_user)) < 60:
                return
            if user_profile.update_from_exchange(transcript, self._complete, agent.model):
                steps.append({"type": "profile_updated", "agent": agent.name})
                print(f"[\033[96mPROFIL\033[0m] Profil utilisateur mis à jour.")
        except Exception as e:
            print(f"[\033[91mProfil utilisateur erreur\033[0m] {e}")

    def _improve_skills(self, agent: Agent, failures: list, steps: list):
        """Amélioration des compétences PENDANT l'usage : si une compétence dynamique a
        échoué, on tente de la RÉPARER automatiquement (LLM) puis on revalide la sûreté.
        N'agit que sur les compétences PURES (les skills complexes de l'utilisateur ne
        sont jamais réécrites automatiquement). Gate SELF_IMPROVE_SKILLS."""
        if os.getenv("SELF_IMPROVE_SKILLS", "true").lower() not in ("true", "1", "yes"):
            return
        if not failures:
            return
        import tools.skills_manager as sm
        seen = set()
        for f in failures:
            name = f.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            path = os.path.join("skills", f"{name}.py")
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    current = fh.read()
                # On ne répare automatiquement que les compétences pures (sûres).
                ok, _ = sm.validate_pure_skill(current, name)
                if not ok:
                    continue
                fixed = (self._complete(agent.model, [
                    {"role": "system", "content": (
                        "Tu es un module de RÉPARATION DE COMPÉTENCE. Corrige la fonction Python "
                        "ci-dessous qui a levé une erreur. Garde EXACTEMENT le même nom et la même "
                        "vocation, reste une fonction PURE (aucune I/O, imports sûrs uniquement). "
                        "Réponds STRICTEMENT par le code Python complet de la fonction corrigée, sans "
                        "texte ni balises markdown.")},
                    {"role": "user", "content": (
                        f"FONCTION ({name}) :\n{current}\n\nERREUR : {f.get('error')}\n"
                        f"ARGS AYANT ÉCHOUÉ : {f.get('args')}")},
                ], tools_schema=None).choices[0].message.content or "").strip()
                # Nettoyage d'éventuelles balises ```python.
                if fixed.startswith("```"):
                    fixed = fixed.strip("`")
                    fixed = fixed[len("python"):].strip() if fixed.lower().startswith("python") else fixed.strip()
                if not fixed or fixed.strip() == current.strip():
                    continue
                ok2, reason = sm.validate_pure_skill(fixed, name)
                if not ok2:
                    print(f"[\033[93mRÉPARATION refusée\033[0m] '{name}' : {reason}")
                    continue
                sm.save_new_skill(name, fixed, f"(réparée auto) {name}")
                steps.append({"type": "skill_improved", "agent": agent.name, "name": name})
                print(f"[\033[96mAUTO-COMPÉTENCE\033[0m] Compétence '{name}' réparée automatiquement.")
            except Exception as e:
                print(f"[\033[91mRéparation skill erreur\033[0m] {e}")

    def _auto_critic(self, agent: Agent, messages: list, steps: list):
        """Passe critique avant livraison (qualité) : un relecteur vérifie la réponse
        finale ; si un problème concret est trouvé, l'agent en produit UNE version
        corrigée. Désactivé par défaut (AUTO_CRITIC=true pour activer ; coût = 1-2
        appels LLM supplémentaires en fin de tâche)."""
        if os.getenv("AUTO_CRITIC", "false").lower() not in ("true", "1", "yes"):
            return
        final = next((m for m in reversed(messages)
                      if m.get("role") == "assistant" and m.get("content")), None)
        if not final or len(str(final.get("content", ""))) < 40:
            return
        user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        if not user:
            return
        try:
            verdict = (self._complete(self._utility_model(agent.model), [
                {"role": "system", "content": (
                    "Tu es un relecteur critique. Vérifie si la RÉPONSE traite correctement et "
                    "complètement la DEMANDE, sans erreur factuelle, incohérence ni partie manquante. "
                    "Réponds STRICTEMENT 'OK' si elle est correcte et complète. Sinon, liste en 1 à 3 "
                    "puces les problèmes concrets.")},
                {"role": "user", "content": f"DEMANDE:\n{user}\n\nRÉPONSE:\n{final.get('content','')}"},
            ], tools_schema=None).choices[0].message.content or "").strip()
            if not verdict or verdict.upper().startswith("OK"):
                return
            revised = (self._complete(agent.model, [
                {"role": "system", "content": (
                    "Corrige et complète ta réponse précédente en tenant compte des remarques du "
                    "relecteur. Renvoie UNIQUEMENT la réponse corrigée, complète et autoportante.")},
                {"role": "user", "content": f"DEMANDE:\n{user}\n\nTA RÉPONSE:\n{final.get('content','')}\n\nREMARQUES:\n{verdict}"},
            ], tools_schema=None).choices[0].message.content or "").strip()
            if not revised or revised.strip() == str(final.get("content", "")).strip():
                return
            messages.append({"role": "assistant", "name": agent.name, "content": revised})
            steps.append({"type": "critic", "agent": agent.name, "issues": verdict})
            steps.append({"type": "message", "agent": agent.name, "content": revised})
            print(f"[\033[96mAUTO-CRITIQUE\033[0m] Réponse révisée après vérification.")
        except Exception as e:
            print(f"[\033[91mAuto-critique erreur\033[0m] {e}")

    def _induce_skill(self, agent: Agent, messages: list, steps: list):
        """Acquisition de compétences (façon Voyager) : si une FONCTION PYTHON PURE et
        réutilisable aurait aidé sur cette tâche, on la fait générer puis on l'enregistre
        comme skill permanente (après validation de sûreté). Désactivable via
        SELF_IMPROVE_SKILLS=false."""
        if os.getenv("SELF_IMPROVE", "true").lower() not in ("true", "1", "yes"):
            return
        if os.getenv("SELF_IMPROVE_SKILLS", "true").lower() not in ("true", "1", "yes"):
            return
        # Création « PROPRE », sans bruit : on ne déclenche l'induction que pour des tâches
        # SUBSTANTIELLES — jamais pour le trivial à une étape (sinon la bibliothèque de
        # compétences se remplit de bruit). Critères (l'un suffit) :
        #   - ≥ SKILL_MIN_TOOL_CALLS appels d'outils (défaut 5),
        #   - une RÉCUPÉRATION D'ERREUR (un outil/skill a échoué puis le run a continué),
        #   - une CORRECTION (auto-critique déclenchée, ou l'utilisateur corrige explicitement).
        _n_tool_calls = sum(1 for s in steps if s.get("type") == "tool_call")
        _errm = ("erreur", "error", "traceback", "exception", "échec", "echec", "failed")
        _had_error_recovery = (
            any(s.get("type") == "skill_improved" for s in steps)
            or any(m.get("role") == "tool" and isinstance(m.get("content"), str)
                   and any(w in m["content"][:160].lower() for w in _errm)
                   for m in messages)
        )
        _last_user = next((str(m.get("content", "")) for m in reversed(messages)
                           if m.get("role") == "user"), "").lower()
        _corr = ("plutôt", "plutot", "corrige", "c'est faux", "ce n'est pas", "refais",
                 "pas ça", "pas ca", "non,", "non ")
        _had_correction = any(s.get("type") == "critic" for s in steps) or any(w in _last_user for w in _corr)
        _min_calls = int(os.getenv("SKILL_MIN_TOOL_CALLS", "5") or 5)
        if not (_n_tool_calls >= _min_calls or _had_error_recovery or _had_correction):
            return
        try:
            import json as _json
            import re as _re
            import tools.skills_manager as sm
            from core.swarm.engine import AVAILABLE_TOOLS   # paresseux : évite l'import circulaire
            existing = set(load_dynamic_skills().keys()) | set(AVAILABLE_TOOLS.keys())
            try:
                from core import skill_quarantine as _sq0
                existing |= set(_sq0.status().keys())  # déjà en canary → pas de doublon
            except Exception:
                pass

            lines = []
            for m in messages[-12:]:
                role = m.get("role")
                if role == "user":
                    lines.append(f"UTILISATEUR: {m.get('content','')}")
                elif role == "assistant" and m.get("content"):
                    lines.append(f"{m.get('name','assistant')}: {m.get('content','')}")
                elif role == "tool":
                    lines.append(f"OUTIL[{m.get('name','?')}]: {str(m.get('content',''))[:300]}")
            transcript = "\n".join(lines)[:6000]

            sys_prompt = (
                "Tu es un module d'ACQUISITION DE COMPÉTENCES. À partir de l'échange, juge si une "
                "FONCTION PYTHON PURE, générique et RÉUTILISABLE aurait évité du travail manuel et "
                "servirait à de futures tâches similaires (ex: calcul, formatage, conversion, parsing).\n"
                "CONTRAINTES STRICTES : fonction pure (déterministe), AUCUNE entrée/sortie, AUCUN accès "
                "réseau/fichier/système ; imports autorisés uniquement parmi math, datetime, json, re, "
                "statistics, itertools, collections, functools, typing, decimal, random, string, "
                "fractions, calendar. Le code doit définir 'def <nom>(...)' avec une docstring.\n"
                "Fournis AUSSI 2-3 CAS DE TEST (la fonction sera EXÉCUTÉE dessus ; un échec = "
                "compétence refusée) : entrées simples, résultat attendu EXACT.\n"
                "Réponds STRICTEMENT en JSON : "
                '{"skill": true, "name": "<snake_case>", "description": "<courte>", "code": "<python>", '
                '"tests": [{"args": [...], "kwargs": {}, "expected": <valeur>}, ...]} '
                'OU {"skill": false} si aucune compétence générique pertinente. '
                "Ne crée PAS de compétence trop spécifique ou triviale."
            )
            resp = self._complete(self._utility_model(agent.model), [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": transcript},
            ], tools_schema=None)
            content = (resp.choices[0].message.content or "").strip()
            # Extraction robuste du JSON.
            start, end = content.find("{"), content.rfind("}")
            if start < 0 or end <= start:
                return
            data = _json.loads(content[start:end + 1])
            if not data.get("skill"):
                return
            name = (data.get("name") or "").strip()
            code = data.get("code") or ""
            desc = (data.get("description") or "").strip() or name
            if not _re.match(r"^[a-z0-9_]+$", name):
                return
            if name in existing:
                print(f"[AUTO-COMPÉTENCE] '{name}' existe déjà — ignorée.")
                return
            ok, reason = sm.validate_pure_skill(code, name)
            if not ok:
                print(f"[\033[93mAUTO-COMPÉTENCE refusée\033[0m] '{name}' : {reason}")
                return
            # SELF-TESTS : la fonction est exécutée sur les cas fournis AVANT toute
            # adoption (validate_pure_skill garantit imports sûrs + fonction pure →
            # l'exec de vérification est équivalent à l'import qui suivrait de toute façon).
            from core import skill_quarantine as sq
            tests = data.get("tests") or []
            ns = {}
            exec(compile(code, f"<skill:{name}>", "exec"), ns)  # nosec B102 — code validé par AST (validate_pure_skill)
            func = ns.get(name)
            if not callable(func):
                print(f"[\033[93mAUTO-COMPÉTENCE refusée\033[0m] '{name}' : fonction introuvable après exec.")
                return
            ok, reason = sq.run_self_tests(func, tests)
            if not ok:
                print(f"[\033[93mAUTO-COMPÉTENCE refusée\033[0m] '{name}' : self-tests — {reason}")
                return
            # QUARANTAINE (canary) : exposée aux agents mais comptée ; promue dans
            # skills/ après N usages réussis, évincée si elle échoue en réel.
            result = sq.save_quarantined(name, code, desc, tests)
            if result.startswith("Succès"):
                steps.append({"type": "skill_learned", "agent": agent.name,
                              "name": name, "description": desc, "quarantined": True})
                print(f"[\033[96mAUTO-COMPÉTENCE\033[0m] '{name}' acquise (en quarantaine canary).")
        except Exception as e:
            print(f"[\033[91mAuto-compétence erreur\033[0m] {e}")
