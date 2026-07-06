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
COPY . .

# ── Configuración por defecto ────────────────────────────────────────────
# Montá tu config.toml en /etc/sentinelpy/config.toml o setea env vars
ENV CONFIG_PATH=/etc/sentinelpy/config.toml

CMD ["python", "-m", "agent", "/etc/sentinelpy/config.toml"]
