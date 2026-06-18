"""Chargement de l'essaim et fabriques de transfert/délégation (mixin).

Extraits de l'ancien `core/swarm.py` :
- `load_agents`              : lit agents.yaml, instancie les agents, câble handoffs/délégations ;
- `create_handoff_function` : fonction dynamique de transfert DÉFINITIF vers un agent ;
- `create_delegate_function`: fonction de SOUS-TRAITANCE (sous-agent isolé, le parent garde la main).

Méthodes de `Swarm` (utilisent `self.agents`, `self.run`, …). `AVAILABLE_TOOLS`,
`_delegate_depth` et `DELEGATE_BLOCKED_TOOLS` vivent dans le moteur : importés en
PARESSEUX (au moment de l'appel) pour éviter un import circulaire engine↔agents.
"""
import os
import time
from typing import Callable

import yaml

from core.agent import Agent, Result

# Racine du projet : ce fichier est core/swarm/agents.py → remonter de 3 dossiers.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _AgentsMixin:
    """Chargement de l'essaim + fabriques handoff/délégation, mélangés dans `Swarm`."""

    def load_agents(self, path: str):
        from core.swarm.engine import AVAILABLE_TOOLS   # paresseux : anti-cycle engine↔agents
        # Bootstrap : à la première installation, agents.yaml n'existe pas encore.
        # On démarre alors avec le SEUL orchestrateur (agents.default.yaml) ; l'utilisateur
        # ajoute ses propres agents ensuite (UI ou outil create_agent). agents.example.yaml
        # contient une équipe complète d'exemple à charger si on veut.
        if not os.path.exists(path):
            import shutil
            default = os.path.join(_PROJECT_ROOT, "agents.default.yaml")
            if os.path.exists(default):
                shutil.copy(default, path)
                print(f"[Essaim] Première exécution : {path} initialisé avec l'orchestrateur seul (agents.default.yaml).")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Reset : repartir d'une table vierge pour que les agents SUPPRIMÉS de
        # agents.yaml disparaissent réellement lors d'un hot-reload (sinon ils
        # survivaient en mémoire jusqu'au redémarrage du serveur).
        self.agents = {}

        # Première passe : créer les agents sans les fonctions de transfert (handoffs)
        for agent_data in data.get("agents", []):
            agent = Agent(
                name=agent_data["name"],
                system_prompt=agent_data["system_prompt"],
                model=agent_data.get("model", "gpt-4o"),
                supports_tools=agent_data.get("supports_tools", True),
                display_name=agent_data.get("display_name"),
                welcome_message=agent_data.get("welcome_message"),
                description=agent_data.get("description", "")
            )
            # Ajouter les outils standards
            for tool_name in agent_data.get("tools", []):
                if tool_name in AVAILABLE_TOOLS:
                    agent.tools.append(AVAILABLE_TOOLS[tool_name])

            self.agents[agent.name] = agent

        # Détermination de l'ORCHESTRATEUR (renommable) : agent marqué
        # `orchestrator: true`, sinon "Athena" s'il existe (compat.), sinon le 1er agent.
        self.orchestrator_name = None
        for agent_data in data.get("agents", []):
            if agent_data.get("orchestrator") is True:
                self.orchestrator_name = agent_data["name"]
                break
        if not self.orchestrator_name:
            if "Athena" in self.agents:
                self.orchestrator_name = "Athena"
            elif self.agents:
                self.orchestrator_name = next(iter(self.agents))
        orch = self.orchestrator_name

        # Seconde passe : injecter les fonctions de transfert dynamiquement
        for agent_data in data.get("agents", []):
            agent = self.agents[agent_data["name"]]

            # L'orchestrateur a automatiquement des transferts vers TOUS les autres agents !
            targets = list(agent_data.get("handoffs", []))
            if agent.name == orch:
                targets = [name for name in self.agents.keys() if name != orch]
            else:
                if orch and orch not in targets and orch in self.agents:
                    targets.append(orch)

            for target_name in targets:
                if target_name in self.agents:
                    target_agent = self.agents[target_name]
                    # Handoffs
                    if not any(f.__name__ == f"transfer_to_{target_agent.name}" for f in agent.tools):
                        handoff_func = self.create_handoff_function(target_agent)
                        agent.tools.append(handoff_func)
                    # Delegates
                    if not any(f.__name__ == f"delegate_to_{target_agent.name}" for f in agent.tools):
                        delegate_func = self.create_delegate_function(target_agent)
                        agent.tools.append(delegate_func)

    def create_handoff_function(self, target_agent: Agent) -> Callable:
        """Génère une fonction Python dynamiquement pour transférer la conversation."""
        def handoff() -> Result:
            return Result(value=f"Transféré avec succès à {target_agent.name}", agent=target_agent)

        handoff.__name__ = f"transfer_to_{target_agent.name}"
        _spec = (getattr(target_agent, "description", "") or "").strip()
        _spec_txt = f" Spécialité : {_spec}" if _spec else ""
        handoff.__doc__ = (f"Transfère la conversation DÉFINITIVEMENT à {target_agent.name}.{_spec_txt} "
                           "Utilise ceci si la demande globale de l'utilisateur relève de ses compétences.")
        return handoff

    def create_delegate_function(self, target_agent: Agent) -> Callable:
        """Génère une fonction pour déléguer une sous-tâche à un spécialiste et attendre son
        résultat (sous-agent en contexte ISOLÉ). Le parent garde la main et synthétise."""
        def delegate(task_description: str, context: str = "") -> str:
            from core.swarm.engine import _delegate_depth, DELEGATE_BLOCKED_TOOLS  # paresseux : anti-cycle
            # 1) Garde de PROFONDEUR : empêche la récursion infinie de sous-agents.
            depth = _delegate_depth.get()
            try:
                max_depth = int(os.getenv("DELEGATE_MAX_DEPTH", "1") or 1)
            except ValueError:
                max_depth = 1
            if depth >= max_depth:
                return (f"Délégation refusée : profondeur maximale atteinte (max={max_depth}). "
                        f"Traite la tâche toi-même ou rends ton résumé au parent.")

            # 2) Prompt ENFANT discipliné (Hermes-like) : il ne connaît RIEN de la
            #    conversation du parent → tout doit passer par tâche + contexte.
            parts = []
            if (context or "").strip():
                parts.append(f"CONTEXTE (fourni par le parent) :\n{context.strip()}")
            parts.append(f"TÂCHE :\n{task_description.strip()}")
            parts.append("Tu es un SOUS-AGENT focalisé : tu ne connais rien de la conversation "
                         "du parent, base-toi uniquement sur la tâche et le contexte ci-dessus. "
                         "Termine par un RÉSUMÉ bref : ce que tu as fait, le résultat, les fichiers "
                         "créés/modifiés, les éventuels problèmes.")
            sub_messages = [{"role": "user", "content": "\n\n".join(parts)}]

            # 3) Budget de tours dédié à l'enfant.
            try:
                child_turns = int(os.getenv("DELEGATE_MAX_TURNS", "12") or 12)
            except ValueError:
                child_turns = 12
            try:
                child_secs = float(os.getenv("DELEGATE_TIMEOUT", "0") or 0)  # 0 = illimité
            except ValueError:
                child_secs = 0.0

            # 4) Sécurité ENFANT : on clampe ses outils (pas de re-délégation/transfert ni
            #    d'effets de bord globaux) via la politique d'outils par session.
            from core import tool_policy as _tp
            d_tok = _delegate_depth.set(depth + 1)
            p_tok = _tp.set_policy(deny=DELEGATE_BLOCKED_TOOLS)
            t0 = time.time()
            try:
                # locked + lock_delegation → l'enfant est une FEUILLE (ni transfert ni délégation).
                _agent, _msgs, _steps = self.run(
                    target_agent, sub_messages, max_turns=child_turns,
                    max_seconds=(child_secs or None), locked=True, lock_delegation=True)
            except Exception as e:
                return f"Erreur lors de la délégation à {target_agent.name} : {e}"
            finally:
                _tp.reset_policy(p_tok)
                _delegate_depth.reset(d_tok)

            # 5) Résultat STRUCTURÉ (résumé + métriques) pour le parent.
            final = next((m.get("content") for m in reversed(_msgs)
                          if m.get("role") == "assistant" and (m.get("content") or "").strip()), None)
            n_tools = sum(1 for s in _steps if s.get("type") == "tool_call")
            dur = int(time.time() - t0)
            header = f"[Sous-agent {target_agent.name} — {n_tools} outil(s), {dur}s]"
            return f"{header}\n{final or '(aucune réponse produite)'}"

        delegate.__name__ = f"delegate_to_{target_agent.name}"
        _spec = (getattr(target_agent, "description", "") or "").strip()
        _spec_txt = f" Spécialité : {_spec}." if _spec else ""
        delegate.__doc__ = (
            f"SOUS-TRAITANCE : confie une sous-tâche à {target_agent.name} et attends son résumé. "
            f"Tu restes le maître et tu synthétises.{_spec_txt} Le sous-agent ne voit PAS la "
            "conversation : passe-lui TOUT le nécessaire. "
            "task_description = ce qu'il doit faire ; context = infos utiles (chemins, contraintes, données).")
        return delegate
