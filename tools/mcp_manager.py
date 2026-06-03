"""Gestionnaire de serveurs MCP (Model Context Protocol).

Permet aux agents d'utiliser n'importe quel serveur MCP (filesystem, GitHub,
Postgres, ...) sans recoder d'outils.

Principe :
  - lit `mcp_servers.json` (format compatible Claude Desktop : command/args/env,
    ou url/transport pour HTTP & SSE) ;
  - ouvre une connexion persistante par serveur dans une boucle asyncio dédiée
    tournant sur un thread de fond ;
  - expose une méthode SYNCHRONE `call(tool, arguments)` utilisable depuis le
    swarm synchrone (via asyncio.run_coroutine_threadsafe) ;
  - tolère les pannes : un serveur qui échoue est journalisé et ignoré, sans
    faire planter l'agent.

Sécurité : si l'authentification est désactivée (ADMIN_PASSWORD vide), les
serveurs « sensibles » (filesystem / shell / exec) ne sont PAS démarrés.
"""
import asyncio
import json
import logging
import os
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("athena.mcp")

# Mots-clés identifiant un serveur à fort pouvoir (FS / shell) à ne pas activer
# quand l'auth est désactivée.
_SENSITIVE_KEYWORDS = ("filesystem", "shell", "exec", "bash", "subprocess")


def _auth_disabled() -> bool:
    return not os.getenv("ADMIN_PASSWORD", "").strip()


class MCPManager:
    def __init__(self, config_path: str = "mcp_servers.json"):
        self.config_path = config_path
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._sessions: Dict[str, Any] = {}            # server -> ClientSession
        self._stop_events: Dict[str, "asyncio.Event"] = {}
        self._tools: Dict[str, Dict[str, Any]] = {}    # tool_name -> {server, schema, description}
        self._tool_functions: Dict[str, Callable] = {}
        self._started = False

    # ------------------------------------------------------------------ config
    def _load_config(self) -> Dict[str, dict]:
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Lecture de %s impossible : %s", self.config_path, e)
            return {}
        # Format Claude Desktop : {"mcpServers": {...}} ou directement {...}
        servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
        return servers or {}

    @staticmethod
    def _is_sensitive(name: str, conf: dict) -> bool:
        blob = " ".join([
            name,
            str(conf.get("command", "")),
            " ".join(conf.get("args", []) or []),
        ]).lower()
        return any(k in blob for k in _SENSITIVE_KEYWORDS)

    # ------------------------------------------------------------------ démarrage
    def start(self):
        if self._started:
            return
        config = self._load_config()
        if not config:
            logger.info("Aucun serveur MCP configuré (%s absent ou vide).", self.config_path)
            self._started = True
            return

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, name="mcp-loop", daemon=True)
        self.thread.start()

        auth_off = _auth_disabled()
        for name, conf in config.items():
            if conf.get("disabled"):
                continue
            if auth_off and self._is_sensitive(name, conf):
                logger.warning(
                    "Serveur MCP '%s' ignoré : sensible (FS/shell) et authentification désactivée.",
                    name,
                )
                continue
            self._connect_blocking(name, conf)

        self._build_tool_functions()
        self._started = True
        logger.info("MCP prêt : %d serveur(s), %d outil(s).",
                    len(self._sessions), len(self._tools))

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _connect_blocking(self, name: str, conf: dict):
        ready = threading.Event()
        box: Dict[str, Any] = {}
        asyncio.run_coroutine_threadsafe(
            self._connect_server(name, conf, ready, box), self.loop
        )
        timeout = conf.get("timeout", 30)
        if not ready.wait(timeout=timeout):
            logger.error("Serveur MCP '%s' : délai de connexion dépassé (%ss).", name, timeout)
            return
        if box.get("error"):
            logger.error("Serveur MCP '%s' : échec — %s", name, box["error"])
        else:
            logger.info("Serveur MCP '%s' connecté (%d outils).", name, box.get("n_tools", 0))

    def _make_transport(self, conf: dict):
        """Retourne un context manager async pour le transport demandé."""
        if conf.get("command"):
            from mcp.client.stdio import stdio_client, StdioServerParameters
            env = {**os.environ, **(conf.get("env") or {})}
            params = StdioServerParameters(
                command=conf["command"],
                args=conf.get("args", []) or [],
                env=env,
            )
            return ("stdio", stdio_client(params))

        url = conf.get("url")
        if not url:
            raise ValueError("Config MCP invalide : ni 'command' ni 'url'.")
        transport = (conf.get("transport") or "").lower()
        if transport in ("sse",) or (not transport and url.rstrip("/").endswith("sse")):
            from mcp.client.sse import sse_client
            return ("sse", sse_client(url))
        # HTTP « streamable » par défaut pour une URL
        from mcp.client.streamable_http import streamablehttp_client
        return ("http", streamablehttp_client(url))

    async def _connect_server(self, name, conf, ready: threading.Event, box: dict):
        try:
            from mcp import ClientSession
            kind, transport_cm = self._make_transport(conf)
            async with transport_cm as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    resp = await session.list_tools()
                    self._sessions[name] = session
                    for tool in resp.tools:
                        schema = tool.inputSchema or {"type": "object", "properties": {}}
                        self._tools[tool.name] = {
                            "server": name,
                            "schema": schema,
                            "description": tool.description or f"Outil MCP {tool.name}",
                        }
                    box["n_tools"] = len(resp.tools)
                    stop = asyncio.Event()
                    self._stop_events[name] = stop
                    ready.set()
                    await stop.wait()  # garde la session ouverte jusqu'à l'arrêt
        except Exception as e:  # noqa: BLE001 — robustesse : on n'interrompt jamais l'agent
            box["error"] = repr(e)
            ready.set()

    # ------------------------------------------------------------------ outils
    @staticmethod
    def _stringify(result) -> str:
        parts = []
        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(f"[contenu {getattr(item, 'type', 'inconnu')}]")
        out = "\n".join(parts) if parts else "(aucun contenu retourné)"
        if getattr(result, "isError", False):
            return f"[Erreur outil MCP] {out}"
        return out

    def call(self, tool_name: str, arguments: Optional[dict] = None, timeout: int = 60) -> str:
        """Appel SYNCHRONE d'un outil MCP depuis le swarm."""
        info = self._tools.get(tool_name)
        if not info or self.loop is None:
            return f"Erreur : outil MCP '{tool_name}' indisponible."
        session = self._sessions.get(info["server"])
        if session is None:
            return f"Erreur : serveur MCP '{info['server']}' non connecté."

        async def _run():
            return await session.call_tool(tool_name, arguments or {})

        try:
            fut = asyncio.run_coroutine_threadsafe(_run(), self.loop)
            result = fut.result(timeout=timeout)
            return self._stringify(result)
        except Exception as e:  # noqa: BLE001
            logger.error("Appel MCP '%s' échoué : %s", tool_name, e)
            return f"Erreur lors de l'appel de l'outil MCP '{tool_name}' : {e}"

    def _build_tool_functions(self):
        self._tool_functions = {}
        for tool_name, info in self._tools.items():
            self._tool_functions[tool_name] = self._make_func(tool_name, info)

    def _make_func(self, tool_name: str, info: dict) -> Callable:
        manager = self

        def mcp_tool(**kwargs):
            return manager.call(tool_name, kwargs)

        mcp_tool.__name__ = tool_name
        mcp_tool.__doc__ = info["description"]
        # Schéma réel exposé à function_to_schema (cf. core.swarm).
        mcp_tool._mcp_schema = info["schema"]
        return mcp_tool

    def tool_functions(self) -> Dict[str, Callable]:
        return dict(self._tool_functions)

    def status(self) -> Dict[str, Any]:
        """État courant pour l'UI : serveurs connectés et outils par serveur."""
        tools_by_server: Dict[str, list] = {}
        for tool_name, info in self._tools.items():
            tools_by_server.setdefault(info["server"], []).append({
                "name": tool_name,
                "description": info.get("description", ""),
            })
        return {
            "started": self._started,
            "config_path": self.config_path,
            "connected_servers": list(self._sessions.keys()),
            "tools_by_server": tools_by_server,
            "tool_count": len(self._tools),
        }

    def stop(self):
        """Arrête proprement la boucle et les connexions MCP."""
        if self.loop is None:
            return
        for ev in list(self._stop_events.values()):
            try:
                self.loop.call_soon_threadsafe(ev.set)
            except Exception:
                pass
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            pass
        if self.thread:
            self.thread.join(timeout=5)

    def restart(self):
        """Recharge la config et reconnecte tous les serveurs MCP à chaud."""
        self.stop()
        self._sessions = {}
        self._stop_events = {}
        self._tools = {}
        self._tool_functions = {}
        self.loop = None
        self.thread = None
        self._started = False
        self.config_path = os.getenv("MCP_CONFIG_PATH", "mcp_servers.json")
        self.start()


# Singleton applicatif
mcp_manager = MCPManager(os.getenv("MCP_CONFIG_PATH", "mcp_servers.json"))
