import os
import re
import json
import time
import uuid
import shlex
import tempfile
import secrets
import asyncio
import threading
import contextvars
from fastapi import FastAPI, HTTPException, File, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from dotenv import load_dotenv

# Chargement du .env
load_dotenv()

# Confiner par défaut l'espace de travail des agents (explorateur de fichiers,
# sandbox, outils shell/code) au sous-dossier workspace/ — évite d'exposer le
# code source et le .env de l'installation. Surchargeable via ACTIVE_WORKSPACE_DIR.
if not os.environ.get("ACTIVE_WORKSPACE_DIR", "").strip():
    _default_ws = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
    os.makedirs(_default_ws, exist_ok=True)
    os.environ["ACTIVE_WORKSPACE_DIR"] = _default_ws

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger("athena.server")

from core.swarm import Swarm
from core.tracing import run_store
from core.run_context import registry as run_registry, current_run_id
from core import channels, approvals
from core.routines import routine_store, start_scheduler as start_routine_scheduler
from core.users import user_store
from tools.memory_tools import core_mem

app = FastAPI(title="Athena Multi-Agent Dashboard")

# Restriction stricte du CORS (sécurité VPS / CSRF)
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from core.state import ACTIVE_SESSIONS, _current_username, _scope_cid
_SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", "168") or 168) * 3600  # défaut 7 jours

from routers import auth as _auth_router
app.include_router(_auth_router.router)
from routers.auth import auth_middleware, _enforce_network_security
_enforce_network_security()
app.middleware("http")(auth_middleware)

# --- En-têtes HTTP de sécurité (anti-clickjacking / sniffing / XSS) -----------
_SECURITY_HEADERS = os.getenv("SECURITY_HEADERS", "true").lower() not in ("false", "0", "no")
_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
    "img-src 'self' data: blob:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'"
)
_CSP = os.getenv("CONTENT_SECURITY_POLICY", _DEFAULT_CSP)


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    if _SECURITY_HEADERS:
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if _CSP:
            resp.headers.setdefault("Content-Security-Policy", _CSP)
        # HSTS seulement derrière HTTPS (sinon casserait l'accès HTTP local).
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "https":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp
from core.state import swarm, _orch_name, _app_name, _orch_agent, ConversationManager, _session_file, ChatSession, SessionManager, sessions, session, TELEMETRY, CODER_CWD, get_coder_cwd, set_coder_cwd, get_model_cost

from routers import config_agents as _config_agents_router
app.include_router(_config_agents_router.router)
from routers import config_skills as _config_skills_router
app.include_router(_config_skills_router.router)
from routers import config_voice as _config_voice_router
app.include_router(_config_voice_router.router)
from routers import config_system as _config_system_router
app.include_router(_config_system_router.router)
from routers import config_metrics as _config_metrics_router
app.include_router(_config_metrics_router.router)
from routers import config_agenda as _config_agenda_router
app.include_router(_config_agenda_router.router)
from routers import config_routines as _config_routines_router
app.include_router(_config_routines_router.router)
from routers import system as _system_router
app.include_router(_system_router.router)
from routers import workspace as _workspace_router
app.include_router(_workspace_router.router)
from routers import chat as _chat_router
app.include_router(_chat_router.router)
from routers import memory as _memory_router
app.include_router(_memory_router.router)
from routers import agenda as _agenda_router
app.include_router(_agenda_router.router)
from routers import lists as _lists_router
app.include_router(_lists_router.router)
from routers import plan as _plan_router
app.include_router(_plan_router.router)
from routers import logs as _logs_router
app.include_router(_logs_router.router)
from routers import user_settings as _user_settings_router
app.include_router(_user_settings_router.router)
from routers import projects as _projects_router
app.include_router(_projects_router.router)
from routers import pipelines as _pipelines_router
app.include_router(_pipelines_router.router)


# Sert index.html avec le NOM D'APP injecté côté serveur (évite le flash « Athena →
# Athena » au rafraîchissement : le HTML statique contenait le nom en dur).
def _render_index():
    from fastapi.responses import HTMLResponse
    name = (os.getenv("APP_NAME", "").strip() or "Athena")
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html = f.read()
    except Exception:
        return HTMLResponse("<h1>Interface introuvable</h1>", status_code=500)
    html = html.replace("__APP_NAME_UPPER__", name.upper()).replace("__APP_NAME__", name)
    return HTMLResponse(html)


@app.get("/", include_in_schema=False)
async def _index():
    return _render_index()


@app.get("/index.html", include_in_schema=False)
async def _index_html():
    return _render_index()


# Sert les fichiers statiques de l'interface Web (le reste : assets, app.js, /index.html…)
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import sys
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0").strip()
    port = int(os.getenv("PORT", "8000"))
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()

    # Note : le garde-fou réseau (_enforce_network_security) s'exécute déjà au
    # CHARGEMENT du module — il couvre aussi `uvicorn server:app`. Ici on ne fait
    # qu'un message d'avertissement convivial en mode local sans mot de passe.
    if not admin_password:
        print("\033[93m[AVERTISSEMENT] ADMIN_PASSWORD vide : authentification désactivée "
              "(autorisé uniquement car bind local).\033[0m")

    from core.platform_info import get_version
    version = get_version()
    print(f"\n🚀 Lancement du serveur {_app_name()} Dashboard (v{version})...")
    print(f"👉 Accède à l'application ici : http://{'localhost' if host == '0.0.0.0' else host}:{port}\n")
    uvicorn.run("server:app", host=host, port=port, reload=True)
