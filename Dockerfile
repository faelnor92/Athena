# Image de l'application Athena v2
FROM python:3.11-slim

# Client Docker (pour piloter la sandbox via le socket hôte) + libs utiles.
RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Écoute réseau dans le conteneur (ADMIN_PASSWORD devient obligatoire — cf. garde-fou).
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000

CMD ["python3", "server.py"]
