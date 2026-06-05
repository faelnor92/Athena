"""Endpoints ADMIN du registre multi-hôtes SSH (brancher plusieurs serveurs).

Réservé à l'administrateur (`_require_admin`) — SSH = surface sensible. Les secrets ne
sont jamais renvoyés en clair (mot de passe masqué par `ssh_hosts.list_hosts`)."""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from routers.auth import _require_admin
from tools import ssh_hosts

router = APIRouter(tags=["SSH Hosts"])


@router.get("/api/ssh/hosts")
async def list_ssh_hosts(request: Request):
    _require_admin(request)
    return ssh_hosts.list_hosts(mask=True)


class SSHHostRequest(BaseModel):
    host: str
    label: str = ""
    username: str = ""
    port: int = 22
    password: str = ""
    key_path: str = ""
    remote_cwd: str = ""
    known_hosts: str = ""
    auto_add: bool = False


@router.post("/api/ssh/hosts")
async def add_ssh_host(request: Request, req: SSHHostRequest):
    _require_admin(request)
    try:
        return ssh_hosts.add_host(
            req.label, req.host, req.username, req.port, req.password,
            req.key_path, req.remote_cwd, req.known_hosts, req.auto_add)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/ssh/hosts/{host_id}")
async def del_ssh_host(request: Request, host_id: str):
    _require_admin(request)
    if host_id == "env":
        raise HTTPException(status_code=400, detail="L'hôte du .env n'est pas supprimable ici.")
    if not ssh_hosts.remove_host(host_id):
        raise HTTPException(status_code=404, detail="Hôte introuvable.")
    return {"status": "success"}
