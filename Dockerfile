# Image de l'application Athena v2
FROM python:3.13-slim

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

# Sécurité : exécution en utilisateur NON-root. Pour piloter la sandbox Docker via le
# socket de l'hôte, lancez avec le bon groupe, ex. :
#   docker run --group-add "$(stat -c %g /var/run/docker.sock)" -v /var/run/docker.sock:/var/run/docker.sock ...
# (sinon utilisez SANDBOX=local). Montez un volume pour /app afin de persister l'état
# (athena_state.sqlite3, conversations.sqlite3, .chroma_db, .env) — il doit être accessible en écriture à cet utilisateur.
RUN useradd --create-home --uid 10001 athena && chown -R athena:athena /app
USER athena

# Sonde de santé : la racine sert l'UI (200, hors /api donc sans auth).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/',timeout=4).status==200 else 1)"

CMD ["python3", "server.py"]
