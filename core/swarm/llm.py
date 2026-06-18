"""Couche COMPLÉTION LLM du Swarm (mixin) : appel litellm, streaming token-par-token,
auto-continuation des réponses tronquées, prompt caching, routage (spécialiste / modèle
rapide / modèle utilitaire).

Méthodes de `Swarm` (s'appuient sur `self.agents`, `self.orchestrator_name`). Le helper
`_completion` appelle `litellm.completion` via le namespace du PACKAGE (`core.swarm.completion`)
pour rester monkeypatchable par les tests après le découpage.
"""
import os
import time

from core.agent import Agent


def _completion(*args, **kwargs):
    """Appelle `litellm.completion` via le namespace du PACKAGE (`core.swarm.completion`).
    Indirection volontaire : après le découpage en package, les tests continuent de
    monkeypatcher `core.swarm.completion` — cette résolution à l'exécution garantit que
    le patch atteint bien la boucle du moteur (contrat historique préservé)."""
    import core.swarm as _pkg
    return _pkg.completion(*args, **kwargs)


class _CompletionMixin:
    """Appel/streaming LLM + routage, mélangés dans `Swarm`."""

    def _maybe_continue(self, model: str, base_messages: list, response):
        """Auto-continuation : si la réponse est tronquée (finish_reason='length',
        sans tool_calls), redemande la suite et recolle, jusqu'à
        LLM_MAX_CONTINUATIONS fois. Évite les réponses coupées."""
        max_cont = int(os.getenv("LLM_MAX_CONTINUATIONS", "3") or 0)
        if max_cont <= 0:
            return response
        try:
            choice = response.choices[0]
            msg = choice.message
        except Exception:
            return response
        full = getattr(msg, "content", "") or ""
        cont = 0
        while (cont < max_cont and getattr(choice, "finish_reason", None) == "length"
               and not getattr(msg, "tool_calls", None) and full):
            cont += 1
            follow = list(base_messages) + [
                {"role": "assistant", "content": full},
                {"role": "user", "content": "Continue ta réponse EXACTEMENT là où elle s'est arrêtée (elle a été tronquée). Ne répète rien, n'ajoute aucune introduction."},
            ]
            try:
                nxt = self._complete(model, follow, tools_schema=None, allow_continuation=False)
                nchoice = nxt.choices[0]
                nmsg = nchoice.message
            except Exception:
                break
            piece = getattr(nmsg, "content", "") or ""
            if not piece:
                break
            full += piece
            choice, msg = nchoice, nmsg
            print(f"[\033[96mCONTINUATION\033[0m] réponse tronquée prolongée ({cont}/{max_cont}).")
        try:
            response.choices[0].message.content = full
            response.choices[0].finish_reason = "stop"
        except Exception:
            pass
        return response

    def _complete_streaming(self, completion_kwargs, on_delta):
        """Appel LLM en streaming : diffuse les tokens via on_delta et reconstruit
        un objet réponse compatible avec la boucle (content + tool_calls)."""
        completion_kwargs["stream"] = True
        content_parts = []
        tool_acc = {}   # index -> {id, name, arguments}
        finish_reason = None

        stream_obj = _completion(**completion_kwargs)
        # Compat : si l'objet renvoyé est déjà une réponse complète (provider sans
        # streaming, ou tests), on émet le contenu d'un bloc et on le renvoie tel quel.
        _choices = getattr(stream_obj, "choices", None)
        if _choices and getattr(_choices[0], "message", None) is not None:
            msg = _choices[0].message
            if getattr(msg, "content", None):
                try:
                    on_delta(msg.content)
                except Exception:
                    pass
            return stream_obj

        for chunk in stream_obj:
            try:
                choice = chunk.choices[0]
            except (AttributeError, IndexError):
                continue
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            piece = getattr(delta, "content", None)
            if piece:
                content_parts.append(piece)
                try:
                    on_delta(piece)
                except Exception:
                    pass
            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = getattr(tc, "index", 0) or 0
                acc = tool_acc.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    acc["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        acc["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        acc["arguments"] += fn.arguments

        full = "".join(content_parts)

        class _F:
            def __init__(self, name, args):
                self.name = name
                self.arguments = args

        class _TC:
            def __init__(self, tid, name, args):
                self.id = tid or f"call_{__import__('uuid').uuid4().hex[:8]}"
                self.type = "function"
                self.function = _F(name, args)

        tool_calls = [_TC(a["id"], a["name"], a["arguments"]) for _i, a in sorted(tool_acc.items()) if a["name"]] or None

        class _Msg:
            def __init__(self):
                self.content = full
                self.tool_calls = tool_calls
            def model_dump(self, exclude_none=True):
                d = {"role": "assistant"}
                if full:
                    d["content"] = full
                if tool_calls:
                    d["tool_calls"] = [{"id": t.id, "type": "function",
                                        "function": {"name": t.function.name, "arguments": t.function.arguments}}
                                       for t in tool_calls]
                return d

        class _Usage:
            prompt_tokens = 0
            completion_tokens = 0

        class _Choice:
            def __init__(self):
                self.message = _Msg()
                self.finish_reason = finish_reason or "stop"

        class _Resp:
            def __init__(self):
                self.choices = [_Choice()]
                self.usage = _Usage()

        return _Resp()

    def _apply_prompt_cache(self, messages: list, model: str) -> list:
        """Prompt caching : marque le gros message système comme point de cache pour
        les modèles Anthropic (préfixe stable réutilisé → latence et coût réduits).
        PROMPT_CACHE = auto (défaut, Anthropic seulement) | on (forcé) | off.
        N'est JAMAIS appliqué sur l'endpoint custom (qwen3 = prefix caching serveur)."""
        mode = os.getenv("PROMPT_CACHE", "auto").lower()
        if mode == "off":
            return messages
        is_anthropic = "claude" in (model or "").lower() or "anthropic" in (model or "").lower()
        if mode != "on" and not is_anthropic:
            return messages
        out, cached = [], False
        for m in messages:
            if (not cached and m.get("role") == "system"
                    and isinstance(m.get("content"), str) and len(m["content"]) > 1000):
                out.append({"role": "system", "content": [
                    {"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}
                ]})
                cached = True
            else:
                out.append(m)
        return out

    def _route_target(self, agent: Agent, messages: list):
        """À QUEL spécialiste confier la demande ? Routage SÉMANTIQUE par embeddings
        (core.agent_router) — ZÉRO appel LLM (avant : un juge LLM par run, lent/facturé/biaisé
        « aucun »/limité au dernier message). Multilingue, prend les 3 derniers messages user.
        Renvoie : NOM d'agent (déléguer) ; "" (aucun → l'orchestrateur répond) ; None (routeur
        indisponible → ne rien restreindre)."""
        try:
            from core import agent_router
            return agent_router.route(self.agents, getattr(self, "orchestrator_name", "Athena"), messages)
        except Exception as e:
            print(f"[Routeur délégation] indisponible ({e}) — délégation laissée au modèle.")
            return None

    def _route_model(self, default_model: str, messages: list) -> str:
        """Routage par difficulté : pour une requête manifestement triviale, utilise
        un modèle rapide (FAST_MODEL) ; sinon garde le modèle fort. Désactivé tant que
        FAST_MODEL n'est pas défini. Heuristique CONSERVATRICE (en cas de doute → fort)."""
        fast = os.getenv("FAST_MODEL", "").strip()
        if not fast:
            return default_model
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if not user_msgs:
            return default_model
        text = str(user_msgs[-1].get("content", "") or "").lower()
        hard_kw = ("```", "code", "python", "script", "debug", "débug", "erreur",
                   "analyse", "compare", "explique", "traduis", "rédige", "écris",
                   "calcule", "pourquoi", "démontre", "résous", "résume", "corrige")
        is_hard = len(text) > 280 or any(k in text for k in hard_kw)
        return default_model if is_hard else fast

    def _utility_model(self, default_model: str) -> str:
        """Modèle pour les appels LLM UTILITAIRES (jugement, extraction, classification :
        induction de compétence, relecture critique…). Un PETIT modèle suffit et coûte
        bien moins. Priorité : UTILITY_MODEL > FAST_MODEL > modèle de l'agent (repli sûr)."""
        return (os.getenv("UTILITY_MODEL", "").strip()
                or os.getenv("FAST_MODEL", "").strip()
                or default_model)

    def _complete(self, model: str, messages: list, tools_schema=None, allow_continuation: bool = True, on_delta=None, allow_fallback: bool = True):
        """Appel LLM via litellm avec routage clé officielle / endpoint custom.
        Si on_delta est fourni et STREAM_TOKENS actif, diffuse les tokens au fil
        de l'eau (latence minimale) et reconstruit une réponse compatible.
        En cas d'échec du modèle (après retries), bascule sur FALLBACK_MODELS."""
        # Config LLM PAR UTILISATEUR : clés/modèle propres au compte courant si définis
        # dans user_config (mêmes noms que les variables d'env), sinon repli sur le global.
        _ucfg = {}
        try:
            from core import user_config
            _ucfg = user_config.get_all()
        except Exception:
            _ucfg = {}

        def _u(name):
            v = _ucfg.get(name)
            return (str(v).strip() if v else os.environ.get(name, "").strip())

        # Modèle préféré de l'utilisateur (optionnel) : remplace le modèle par défaut.
        if _ucfg.get("LLM_MODEL"):
            model = str(_ucfg["LLM_MODEL"]).strip()

        # Plafond de tokens pour forcer des réponses concises (optimisation des coûts)
        max_t = int(os.getenv("LLM_MAX_TOKENS", "4000"))
        # `_internal` est un marqueur INTERNE (échafaudage auto-continuation/relais) : utile
        # pour la persistance/affichage, mais non-standard côté API → on l'enlève de la copie
        # envoyée au LLM (sans muter la liste d'origine qui sert encore au scope visible).
        _api_messages = [
            {k: v for k, v in m.items() if k != "_internal"} if isinstance(m, dict) and "_internal" in m else m
            for m in messages]
        completion_kwargs = {"model": model, "messages": _api_messages, "tools": tools_schema, "max_tokens": max_t}
        custom_base = _u("CUSTOM_LLM_API_BASE")
        custom_key = _u("CUSTOM_LLM_API_KEY")
        m = (model or "").strip()
        model_l = m.lower()

        # --- Routage par PRÉFIXE explicite (déterministe, pas d'ambiguïté).
        # 1) "custom/" / "custom_openai/" = convention UI de NOTRE liste → endpoint custom.
        is_custom_prefixed = model_l.startswith("custom/") or model_l.startswith("custom_openai/")
        # 2) Préfixe provider NATIF litellm → routé en direct, JAMAIS vers l'endpoint custom
        #    (sinon un "gemini/…" partirait sur le serveur local qui ne le connaît pas → échec).
        _NATIVE_PREFIXES = ("gemini/", "mistral/", "groq/", "openrouter/",
                            "anthropic/", "ollama/", "vertex_ai/", "cohere/", "together_ai/")
        is_native_prefixed = any(model_l.startswith(p) for p in _NATIVE_PREFIXES)

        # Clé officielle éventuelle (passée explicitement à litellm si on a la nôtre).
        official_key = ""
        if model_l.startswith("gemini/") or "gemini-" in model_l:
            official_key = _u("GEMINI_API_KEY")
        elif model_l.startswith("mistral/"):
            official_key = _u("MISTRAL_API_KEY")
        elif model_l.startswith("groq/"):
            official_key = _u("GROQ_API_KEY")
        elif model_l.startswith("openrouter/"):
            official_key = _u("OPENROUTER_API_KEY")
        elif model_l.startswith("anthropic/") or "claude-" in model_l:
            official_key = _u("ANTHROPIC_API_KEY")
        elif "gpt-" in model_l or model_l.startswith("openai/"):
            official_key = _u("OPENAI_API_KEY")
        has_official_key = bool(official_key)

        # Décision : endpoint custom si préfixe custom, OU si "openai/" (= endpoint
        # OpenAI-compatible local), OU si on n'a NI préfixe provider natif NI clé officielle
        # → repli sur le serveur custom configuré. JAMAIS pour un préfixe provider natif,
        # ni pour un modèle cloud dont on possède la clé (gpt-4o, claude-…, gemini-… même
        # écrits SANS préfixe — corrige « gemini-2.5-pro nu » envoyé par erreur au custom).
        use_custom = bool(custom_base) and (
            is_custom_prefixed
            or model_l.startswith("openai/")
            or (not is_native_prefixed and not has_official_key)
        )
        if use_custom:
            # Auto-correction pour Open WebUI (/v1 -> /api/v1)
            if "/v1" in custom_base and "/api" not in custom_base:
                custom_base = custom_base.replace("/v1", "/api/v1")
            completion_kwargs["api_base"] = custom_base
            completion_kwargs["api_key"] = custom_key or "placeholder-key"
            # Retirer le préfixe UI "custom/" : litellm ne connaît pas de provider "custom"
            # (c'était LA cause du « il faut enlever custom/ à la main »).
            local_model = m or "qwen3"
            for pfx in ("custom/", "custom_openai/"):
                if local_model.lower().startswith(pfx):
                    local_model = local_model[len(pfx):]
                    break
            # litellm exige un préfixe de provider OpenAI-compatible pour un endpoint custom.
            completion_kwargs["model"] = local_model if "/" in local_model else f"openai/{local_model}"
        else:
            # Appel direct au provider via litellm (préfixe natif conservé : gemini/…, etc.).
            completion_kwargs["model"] = m
            # Clé officielle résolue (par-utilisateur ou globale) passée explicitement à litellm.
            if official_key:
                completion_kwargs["api_key"] = official_key
            # Prompt caching (Anthropic) hors endpoint custom uniquement — sûr pour qwen3.
            completion_kwargs["messages"] = self._apply_prompt_cache(messages, model)

        stream = on_delta is not None and os.getenv("STREAM_TOKENS", "true").lower() in ("true", "1", "yes")

        # Garde-fou : retries avec backoff exponentiel sur erreur LLM transitoire.
        retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        last_err = None
        for attempt in range(retries + 1):
            try:
                if stream:
                    return self._complete_streaming(dict(completion_kwargs), on_delta)
                response = _completion(**completion_kwargs)
                # Recolle automatiquement les réponses tronquées (finish_reason=length).
                if allow_continuation:
                    response = self._maybe_continue(model, messages, response)
                return response
            except Exception as e:
                last_err = e
                if attempt < retries:
                    wait = min(2 ** attempt, 8)
                    print(f"[\033[93mLLM retry\033[0m] tentative {attempt + 1}/{retries} échouée ({e}); nouvelle tentative dans {wait}s")
                    time.sleep(wait)

        # Failover : le modèle principal a échoué → on tente les modèles de secours.
        if allow_fallback:
            fallbacks = [m.strip() for m in os.getenv("FALLBACK_MODELS", "").split(",")
                         if m.strip() and m.strip() != model]
            for fb in fallbacks:
                try:
                    print(f"[\033[96mLLM failover\033[0m] '{model}' indisponible → bascule sur '{fb}'.")
                    return self._complete(fb, messages, tools_schema, allow_continuation,
                                          on_delta, allow_fallback=False)
                except Exception as e:
                    last_err = e
        raise last_err
