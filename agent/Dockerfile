FROM python:3.13-slim

WORKDIR /app

# ── Dependencias del sistema ─────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencias Python ──────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Código del agente ────────────────────────────────────────────────────
COPY . agent/

# ── Configuración por defecto ────────────────────────────────────────────
# Montá tu config.toml en /etc/sentinelpy/config.toml o setea env vars
ENV CONFIG_PATH=/etc/sentinelpy/config.toml

# ── Healthcheck ────────────────────────────────────────────────────────────
# The agent runs a background loop; HEALTHCHECK ensures the container
# doesn't stay alive if the loop dies. We check via process presence.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD gosu python -c "import os; os.kill(1, 0)" || exit 1

CMD ["python", "-m", "agent", "/etc/sentinelpy/config.toml"]
