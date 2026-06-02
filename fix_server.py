with open('server.py', 'r') as f:
    content = f.read()
    
content = content.replace("app.include_router(_chat_router.router)\n", 
"""app.include_router(_chat_router.router)
from routers import memory as _memory_router
app.include_router(_memory_router.router)
from routers import agenda as _agenda_router
app.include_router(_agenda_router.router)
from routers import lists as _lists_router
app.include_router(_lists_router.router)
from routers import plan as _plan_router
app.include_router(_plan_router.router)
""")

with open('server.py', 'w') as f:
    f.write(content)
