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
cm = swarm.agents["CommunityManager"]
print("🔍 Outils de CommunityManager :", [f.__name__ for f in cm.tools])
print("🔍 Modèle de CommunityManager :", cm.model)

# Reconstruire le scénario
prompt = "peux-tu me faire un post facebook de présentation d'auteur"
messages = [
    {"role": "assistant", "content": "Bonjour, je suis Athena. Comment puis-je vous aider aujourd'hui ?", "name": "Athena"},
    {"role": "user", "content": prompt}
]

print("💬 Envoi du prompt au Swarm ( starting with Athena ) ...")
athena = swarm.agents["Athena"]
final_agent, new_messages, steps = swarm.run(athena, messages)

print("\n--- RÉSULTATS DU RUN ---")
print(f"Agent final actif : {final_agent.name}")
print("\nÉtapes d'exécution :")
print(json.dumps(steps, indent=2, ensure_ascii=False))

print("\nNouveaux messages ajoutés :")
for m in new_messages[len(messages):]:
    print(f"\n[{m.get('role')} - {m.get('name') or 'NoName'}]:")
    print(m.get('content'))
