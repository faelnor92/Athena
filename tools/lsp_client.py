"""Diagnostics de code UNIFIÉS (boucle de feedback façon opencode / Claude Code).

Un SEUL moteur de diagnostics, partagé par :
  - les outils d'édition (edit_file/write_file/apply_patch) → la sortie renvoyée à l'agent
    inclut les erreurs introduites, qu'il corrige immédiatement (athena_cli, swarm, UI chat) ;
  - l'onglet Code de l'UI via /api/workspace/lint.

Stratégie :
  1. basedpyright (`basedpyright-langserver --stdio`) pour Python : types, imports, variables
     non définies, etc. Un serveur LSP par racine de projet, gardé chaud (handshake une fois).
     Embarque son propre Node (nodejs-wheel) → aucune dépendance système.
  2. Repli ROBUSTE sans serveur (toujours dispo) : `compile()` pour les erreurs de syntaxe
     Python, `ruff` si présent pour le style, `json.loads` pour le JSON.

Tout est NON bloquant et dégradé en silence : si rien n'est disponible, on renvoie [].
Sévérités normalisées : "error" | "warning" | "information" | "hint".
Positions 1-indexées (ligne ET colonne) pour coller à read_file et aux éditeurs.
"""
import atexit
import json
import os
import shutil
import subprocess
import threading
import time
from urllib.request import pathname2url

# Sévérités LSP (textDocument/publishDiagnostics) → libellés normalisés.
_SEVERITY = {1: "error", 2: "warning", 3: "information", 4: "hint"}

# Extensions prises en charge par le serveur LSP Python.
_PY_EXT = (".py", ".pyi")

# Marqueurs de racine de projet Python (sinon → dossier du fichier).
_ROOT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
                 "Pipfile", "pyrightconfig.json", ".git")


def _enabled() -> bool:
    return os.getenv("CODE_LSP_ENABLED", "true").lower() in ("true", "1", "yes")


def _langserver_cmd():
    """Commande du serveur LSP Python, ou None si introuvable. basedpyright d'abord
    (embarque Node), puis pyright si installé séparément."""
    for exe in ("basedpyright-langserver", "pyright-langserver"):
        path = shutil.which(exe)
        if path:
            return [path, "--stdio"]
    return None


def _find_root(abs_path: str) -> str:
    d = os.path.dirname(os.path.abspath(abs_path))
    cur = d
    while True:
        for marker in _ROOT_MARKERS:
            if os.path.exists(os.path.join(cur, marker)):
                return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return d  # aucun marqueur → dossier du fichier
        cur = parent


def _uri(abs_path: str) -> str:
    return "file://" + pathname2url(os.path.abspath(abs_path))


# --------------------------------------------------------------------------- #
# Serveur LSP (un par racine, gardé chaud).
# --------------------------------------------------------------------------- #
class _LspServer:
    def __init__(self, root: str, cmd: list):
        self.root = root
        self.proc = subprocess.Popen(
            cmd, cwd=root,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._wlock = threading.Lock()
        self._mid = 0
        self._open = {}                       # uri -> version
        self._diags = {}                      # uri -> list[diagnostic LSP brut]
        self._events = {}                     # uri -> threading.Event (set au prochain publish)
        self._state_lock = threading.Lock()
        self._ready = threading.Event()
        self._alive = True
        threading.Thread(target=self._reader, name="lsp-reader", daemon=True).start()
        self._initialize()

    # --- bas niveau JSON-RPC sur stdio (cadrage Content-Length) --------------
    def _send(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        with self._wlock:
            self.proc.stdin.write(header + data)
            self.proc.stdin.flush()

    def _notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict) -> int:
        with self._state_lock:
            self._mid += 1
            mid = self._mid
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        return mid

    def _reader(self):
        out = self.proc.stdout
        try:
            while self._alive:
                # En-têtes jusqu'à la ligne vide.
                length = 0
                while True:
                    line = out.readline()
                    if not line:
                        return  # processus terminé
                    line = line.decode("ascii", "replace").strip()
                    if not line:
                        break
                    if line.lower().startswith("content-length:"):
                        length = int(line.split(":", 1)[1].strip())
                if length <= 0:
                    continue
                body = out.read(length)
                if not body:
                    return
                try:
                    msg = json.loads(body.decode("utf-8", "replace"))
                except Exception:
                    continue
                self._handle(msg)
        except Exception:
            return
        finally:
            self._alive = False

    def _handle(self, msg: dict):
        method = msg.get("method")
        if method == "textDocument/publishDiagnostics":
            params = msg.get("params") or {}
            uri = params.get("uri")
            if uri:
                with self._state_lock:
                    self._diags[uri] = params.get("diagnostics") or []
                    ev = self._events.get(uri)
                if ev:
                    ev.set()
        elif "id" in msg and "result" in msg and not self._ready.is_set():
            # Réponse à `initialize`.
            self._ready.set()
        elif method == "workspace/configuration":
            # pyright/basedpyright demandent la config par section. On force le mode "standard"
            # (défaut pyright/Claude Code) — sinon basedpyright est en "recommended", très
            # bruyant (reportUnknown* en avertissements sur tout code non typé).
            items = (msg.get("params") or {}).get("items") or [{}]
            result = [self._config_for(it.get("section", "")) for it in items]
            if "id" in msg:
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        elif method in ("client/registerCapability", "window/workDoneProgress/create"):
            if "id" in msg:
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})

    @staticmethod
    def _config_for(section: str):
        mode = os.getenv("CODE_LSP_MODE", "standard")  # off|basic|standard|strict|recommended|all
        analysis = {"typeCheckingMode": mode, "diagnosticMode": "openFilesOnly",
                    "useLibraryCodeForTypes": True}
        if section.endswith("analysis"):       # "python.analysis" / "basedpyright.analysis"
            return analysis
        return {"analysis": analysis}          # "python" / "basedpyright" / ""

    def _initialize(self):
        self._request("initialize", {
            "processId": os.getpid(),
            "rootUri": _uri(self.root),
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {"relatedInformation": True},
                    "synchronization": {"didSave": True, "dynamicRegistration": False},
                },
                "workspace": {"configuration": True, "workspaceFolders": True},
            },
            "initializationOptions": {},
            "workspaceFolders": [{"uri": _uri(self.root), "name": os.path.basename(self.root) or "root"}],
        })
        self._ready.wait(timeout=float(os.getenv("CODE_LSP_INIT_TIMEOUT", "15") or 15))
        self._notify("initialized", {})

    # --- API ----------------------------------------------------------------
    def diagnostics(self, abs_path: str, content: str, timeout: float):
        if not self._alive:
            raise RuntimeError("serveur LSP arrêté")
        uri = _uri(abs_path)
        ev = threading.Event()
        with self._state_lock:
            self._events[uri] = ev
            version = self._open.get(uri, 0) + 1
            self._open[uri] = version
        if version == 1:
            self._notify("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": "python", "version": version, "text": content}})
        else:
            self._notify("textDocument/didChange", {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": content}]})
        got = ev.wait(timeout=timeout)
        # Petit délai de stabilisation : pyright peut publier un 1er lot puis l'affiner.
        time.sleep(float(os.getenv("CODE_LSP_SETTLE", "0.15") or 0.15))
        if not got:
            # Aucun publishDiagnostics dans le délai → serveur lent/bloqué : signal de panne
            # (pour le disjoncteur côté module). pyright publie TOUJOURS, même sans erreur.
            raise TimeoutError("diagnostics LSP non reçus dans le délai")
        with self._state_lock:
            return list(self._diags.get(uri, []))

    def shutdown(self):
        self._alive = False
        try:
            self.proc.terminate()
        except Exception:
            pass


_SERVERS = {}            # root -> _LspServer
_SERVERS_LOCK = threading.Lock()

# DISJONCTEUR : si le LSP enchaîne les échecs (lent/cassé), on l'éteint temporairement et on
# bascule sur le repli compile/ast → l'édition ne reste JAMAIS bloquée plusieurs secondes.
_lsp_fails = 0
_lsp_disabled_until = 0.0
_LSP_FAIL_THRESHOLD = int(os.getenv("CODE_LSP_FAIL_THRESHOLD", "3") or 3)
_LSP_COOLDOWN = float(os.getenv("CODE_LSP_COOLDOWN", "120") or 120)


def _breaker_open() -> bool:
    return time.time() < _lsp_disabled_until


def _record_ok():
    global _lsp_fails
    _lsp_fails = 0


def _record_fail():
    global _lsp_fails, _lsp_disabled_until
    _lsp_fails += 1
    if _lsp_fails >= _LSP_FAIL_THRESHOLD:
        _lsp_disabled_until = time.time() + _LSP_COOLDOWN
        _lsp_fails = 0


def _server_for(abs_path: str):
    cmd = _langserver_cmd()
    if not cmd:
        return None
    root = _find_root(abs_path)
    with _SERVERS_LOCK:
        srv = _SERVERS.get(root)
        # Serveur vivant ET processus encore en vie (sinon on le remplace).
        if srv is not None and srv._alive and srv.proc.poll() is None:
            return srv
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
        try:
            srv = _LspServer(root, cmd)
        except Exception:
            return None
        _SERVERS[root] = srv
        return srv


@atexit.register
def _shutdown_all():
    with _SERVERS_LOCK:
        for srv in _SERVERS.values():
            srv.shutdown()
        _SERVERS.clear()


# --------------------------------------------------------------------------- #
# Repli sans serveur LSP (toujours disponible).
# --------------------------------------------------------------------------- #
def _fallback(abs_path: str, content: str):
    ext = os.path.splitext(abs_path)[1].lower()
    out = []
    if ext in _PY_EXT:
        try:
            compile(content, abs_path, "exec")
        except SyntaxError as e:
            out.append({"line": e.lineno or 1, "column": e.offset or 1,
                        "severity": "error", "message": f"SyntaxError: {e.msg}",
                        "code": "syntax", "source": "compile"})
            return out  # syntaxe cassée → ruff n'apportera rien d'utile
        except Exception as e:
            out.append({"line": 1, "column": 1, "severity": "error",
                        "message": str(e), "code": "", "source": "compile"})
            return out
        # Style/lint via ruff si présent (non bloquant).
        if shutil.which("ruff"):
            try:
                res = subprocess.run(
                    ["ruff", "check", "--output-format", "json", "--quiet", abs_path],
                    capture_output=True, text=True, timeout=10)
                if res.stdout.strip():
                    for r in json.loads(res.stdout):
                        loc = r.get("location") or {}
                        out.append({
                            "line": loc.get("row", 1), "column": loc.get("column", 1),
                            "severity": "warning",
                            "message": f"{r.get('code', '')}: {r.get('message', '')}".strip(": "),
                            "code": r.get("code", ""), "source": "ruff"})
            except Exception:
                pass
    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            out.append({"line": e.lineno, "column": e.colno, "severity": "error",
                        "message": f"JSONDecodeError: {e.msg}", "code": "", "source": "json"})
    return out


def _normalize_lsp(diags: list):
    """Diagnostics LSP bruts → format unifié 1-indexé."""
    out = []
    for d in diags:
        rng = (d.get("range") or {}).get("start") or {}
        end = (d.get("range") or {}).get("end") or {}
        code = d.get("code")
        out.append({
            "line": int(rng.get("line", 0)) + 1,
            "column": int(rng.get("character", 0)) + 1,
            "end_line": int(end.get("line", 0)) + 1,
            "end_column": int(end.get("character", 0)) + 1,
            "severity": _SEVERITY.get(d.get("severity", 1), "error"),
            "message": d.get("message", ""),
            "code": str(code) if code is not None else "",
            "source": d.get("source", "lsp"),
        })
    return out


# --------------------------------------------------------------------------- #
# API publique.
# --------------------------------------------------------------------------- #
def diagnostics(abs_path: str, content: str = None, timeout: float = None):
    """Diagnostics du fichier (liste de dicts unifiés). `content` = contenu courant (sinon lu
    sur disque). Ne lève jamais : renvoie [] si rien n'est analysable/disponible."""
    if not _enabled():
        return []
    abs_path = os.path.abspath(abs_path)
    if content is None:
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return []
    ext = os.path.splitext(abs_path)[1].lower()
    # Serveur LSP pour Python — sauf si le DISJONCTEUR est ouvert (échecs répétés → on évite
    # de bloquer l'édition et on passe direct au repli). Sinon repli (couvre aussi Python).
    if ext in _PY_EXT and not _breaker_open():
        srv = _server_for(abs_path)
        if srv is not None:
            try:
                to = timeout if timeout is not None else float(os.getenv("CODE_LSP_TIMEOUT", "2.5") or 2.5)
                raw = srv.diagnostics(abs_path, content, to)
                _record_ok()
                return _normalize_lsp(raw)
            except Exception:
                _record_fail()  # timeout/erreur → compte pour le disjoncteur, puis repli
    try:
        return _fallback(abs_path, content)
    except Exception:
        return []


def has_lsp() -> bool:
    """True si un vrai serveur LSP est disponible (sinon on est en mode repli)."""
    return _enabled() and _langserver_cmd() is not None


def format_for_agent(rel_path: str, diags: list, max_items: int = 12) -> str:
    """Bloc texte compact à AJOUTER à la sortie d'un outil d'édition. Vide si aucune ERREUR
    ni AVERTISSEMENT (on n'ajoute pas de bruit pour des hints/infos)."""
    notable = [d for d in diags if d.get("severity") in ("error", "warning")]
    if not notable:
        return ""
    errors = [d for d in notable if d["severity"] == "error"]
    head = "❌ Erreurs détectées (corrige-les)" if errors else "⚠️ Avertissements"
    lines = []
    for d in notable[:max_items]:
        mark = "error" if d["severity"] == "error" else "warn "
        code = f" [{d['code']}]" if d.get("code") else ""
        lines.append(f"  {mark} {rel_path}:{d['line']}:{d['column']} {d['message']}{code}")
    extra = len(notable) - max_items
    if extra > 0:
        lines.append(f"  … et {extra} de plus.")
    return f"\n{head} :\n" + "\n".join(lines)
