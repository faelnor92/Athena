import re

with open('server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

auth_lines = []
new_server_lines = []

in_auth_block = False

for i, line in enumerate(lines):
    line_num = i + 1
    
    if line_num == 60:
        in_auth_block = True
        
    if in_auth_block:
        modified_line = line.replace('@app.post', '@router.post').replace('@app.get', '@router.get').replace('@app.delete', '@router.delete')
        # auth_middleware cannot be on router, we will apply it manually in server.py
        modified_line = modified_line.replace('@app.middleware("http")', '')
        auth_lines.append(modified_line)
    else:
        new_server_lines.append(line)
        
    if line_num == 250:
        in_auth_block = False

    # Inject the inclusion at line 59
    if line_num == 59:
        new_server_lines.append('from routers import auth as _auth_router\n')
        new_server_lines.append('app.include_router(_auth_router.router)\n')
        new_server_lines.append('from routers.auth import auth_middleware, _enforce_network_security\n')
        new_server_lines.append('_enforce_network_security()\n')
        new_server_lines.append('app.middleware("http")(auth_middleware)\n')

header = """import os
import time
import secrets
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.users import user_store
from core.state import ACTIVE_SESSIONS, _current_username, _scope_cid

router = APIRouter(tags=["Auth"])

_SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", "168") or 168) * 3600

"""

with open('routers/auth.py', 'w', encoding='utf-8') as f:
    f.write(header)
    f.writelines(auth_lines)

with open('server.py', 'w', encoding='utf-8') as f:
    f.writelines(new_server_lines)

print("Extraction of auth done.")
