import os
import sys
import json
from dotenv import load_dotenv

# Charger les variables d'environnement correctement
load_dotenv()

sys.path.append(os.getcwd())

from core.swarm import Swarm

print("🚀 Initialisation du Swarm...")
swarm = Swarm()

print("🔍 Agents chargés :", list(swarm.agents.keys()))
athena = swarm.agents["Athena"]
print("🔍 Outils de Athena :", [f.__name__ for f in athena.tools])

# Reconstruire le scénario
prompt = "j'aimerais que tu me critique ce bout de roman, que tu me fasse un code python pour verifier les fautes d'orthographe et que tu me le traduise en allemand. ensuite fait moi un post facebook dans 3 langues"
messages = [
    {"role": "assistant", "content": "Bonjour, je suis Athena. Comment puis-je vous aider aujourd'hui ?", "name": "Athena"},
    {"role": "user", "content": prompt}
]

print("💬 Envoi du prompt au Swarm...")
final_agent, new_messages, steps = swarm.run(athena, messages)

print("\n--- RÉSULTATS DU RUN ---")
print(f"Agent final actif : {final_agent.name}")
print("\nÉtapes d'exécution :")
print(json.dumps(steps, indent=2, ensure_ascii=False))

print("\nNouveaux messages ajoutés :")
for m in new_messages[len(messages):]:
    print(f"[{m.get('role')} - {m.get('name') or 'NoName'}]: {m.get('content')}")
    if m.get("tool_calls"):
        print("  Tool Calls:", json.dumps(m["tool_calls"], indent=2))
