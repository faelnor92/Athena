import os
import json
import uuid
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import HTMLResponse
from core import athenadesign_runner as runner
from core import athenadesign_generator as generator

router = APIRouter(prefix="/api/athenadesign", tags=["AthenaDesign"])

# Save database in root directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_FILE = os.path.join(BASE_DIR, "athenadesign_projects.json")

# Ensure sandbox directory exists
SANDBOX_DIR = runner.SANDBOX_DIR
os.makedirs(SANDBOX_DIR, exist_ok=True)

def read_db() -> dict:
    if os.path.exists(PROJECTS_FILE):
        try:
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def write_db(data: dict):
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@router.get("/projects")
async def get_projects():
    db = read_db()
    return [
        {
            "id": pid,
            "name": pdata.get("name", "Sans titre"),
            "updated_at": pdata.get("updated_at", ""),
            "versions_count": len(pdata.get("versions", []))
        } for pid, pdata in db.items()
    ]

@router.post("/projects/new")
async def create_project(payload: dict = Body(...)):
    project_id = str(uuid.uuid4().hex[:12])
    name = payload.get("name", f"Projet {project_id[:4]}")
    
    db = read_db()
    db[project_id] = {
        "id": project_id,
        "name": name,
        "created_at": uuid.uuid4().hex,
        "updated_at": uuid.uuid4().hex,
        "history": [],
        "versions": []
    }
    write_db(db)
    return db[project_id]

@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    db = read_db()
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return db[project_id]

@router.post("/chat")
async def chat_endpoint(payload: dict = Body(...)):
    project_id = payload.get("project_id")
    prompt = payload.get("prompt")
    provider = payload.get("provider", "mock")
    api_key = payload.get("api_key", "")
    model_name = payload.get("model_name", "")
    
    db = read_db()
    if not project_id or project_id not in db:
        project_id = str(uuid.uuid4().hex[:12])
        db[project_id] = {
            "id": project_id,
            "name": f"Conversation {project_id[:4]}",
            "history": [],
            "versions": []
        }
        
    project = db[project_id]
    
    result = await generator.generate_design(
        prompt=prompt,
        history=project["history"],
        provider=provider,
        api_key=api_key,
        model_name=model_name
    )
    
    project["history"].append({"role": "user", "content": prompt})
    project["history"].append({"role": "assistant", "content": result["explanation"]})
    
    version_num = len(project["versions"]) + 1
    new_version = {
        "version": version_num,
        "type": result["type"],
        "explanation": result["explanation"],
        "code": result["code"],
        "prompt": prompt,
        "comments": []
    }
    project["versions"].append(new_version)
    
    write_db(db)
    
    return {
        "project_id": project_id,
        "version": new_version,
        "history": project["history"]
    }

@router.post("/projects/{project_id}/versions/{version_num}/comments")
async def save_comment(project_id: str, version_num: int, comment: dict = Body(...)):
    db = read_db()
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    project = db[project_id]
    
    idx = version_num - 1
    if idx < 0 or idx >= len(project["versions"]):
        raise HTTPException(status_code=404, detail="Version introuvable")
        
    version = project["versions"][idx]
    if "comments" not in version:
        version["comments"] = []
        
    comment_id = str(uuid.uuid4().hex[:8])
    comment_data = {
        "id": comment_id,
        "text": comment.get("text", ""),
        "x": comment.get("x", 0),
        "y": comment.get("y", 0),
        "width": comment.get("width", 0),
        "height": comment.get("height", 0),
        "tool": comment.get("tool", "point"),
        "color": comment.get("color", "#ef4444"),
        "drawing_data": comment.get("drawing_data", ""),
        "resolved": False
    }
    
    version["comments"].append(comment_data)
    write_db(db)
    return comment_data

@router.post("/execute")
async def execute_endpoint(payload: dict = Body(...)):
    project_id = payload.get("project_id")
    code = payload.get("code")
    
    if not project_id or not code:
        raise HTTPException(status_code=400, detail="Paramètres project_id et code requis")
        
    execution_result = runner.execute_code(code, project_id)
    return execution_result

@router.get("/projects/{project_id}/versions/{version_num}/raw", response_class=HTMLResponse)
async def get_raw_html(project_id: str, version_num: int):
    db = read_db()
    if project_id not in db:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    project = db[project_id]
    
    idx = version_num - 1
    if idx < 0 or idx >= len(project["versions"]):
        raise HTTPException(status_code=404, detail="Version introuvable")
        
    version = project["versions"][idx]
    if version.get("type") != "html":
        raise HTTPException(status_code=400, detail="Seuls les artefacts de type HTML peuvent être affichés de manière brute")
        
    return HTMLResponse(content=version["code"], status_code=200)
