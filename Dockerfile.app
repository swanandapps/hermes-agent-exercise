# The web tier: FastAPI relay + the built React UI.
# Knows nothing about agents — it forwards to the Hermes gateway and streams the reply back.

# FROM = the starting filesystem. "slim" is a stripped-down Debian with Python,
# ~10x smaller than the full image because we need no compilers here.
FROM python:3.11-slim

# WORKDIR = the directory every later command runs in. Created if absent.
WORKDIR /srv

# Dependencies are copied and installed BEFORE the source. Docker caches each step
# as a layer and reuses it while its inputs are unchanged — so editing app.py does
# not reinstall FastAPI. Copying source first would invalidate that cache on every edit.
COPY requirements.docker.app.txt ./
RUN pip install --no-cache-dir -r requirements.docker.app.txt

# Now the parts that change often.
COPY backend/ ./backend/
COPY config/ ./config/
COPY frontend/dist/ ./frontend/dist/

# Documents the port. Publishing it to the host happens in docker-compose.yml —
# EXPOSE alone opens nothing.
EXPOSE 8000

# CMD runs when the CONTAINER STARTS (RUN happens at build time — that distinction
# is most of Docker). 0.0.0.0 rather than 127.0.0.1: inside a container, localhost
# means the container itself, so binding there would make it unreachable from outside.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
