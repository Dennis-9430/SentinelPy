# =============================================================================
# Dockerfile Multi-Stage para SentinelPy
# =============================================================================
# Stage 1: builder — instala dependencias
# Stage 2: runtime — solo lo necesario para correr
#
# Uso en desarrollo:
#   docker compose up -d --build
#
# Uso en producción:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Cache de pip: solo reinstala si cambia requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Crear usuario no-root para seguridad
RUN addgroup --system --gid 1001 sentinel && \
    adduser --system --uid 1001 sentinel

# Copiar dependencias desde builder
COPY --from=builder /root/.local /root/.local

# Copiar código de la aplicación
COPY . .

# Dar permisos al entrypoint
RUN chmod +x scripts/docker-entrypoint.sh

# PATH para encontrar paquetes instalados con --user
ENV PATH=/root/.local/bin:$PATH

# Cambiar a usuario no-root
USER sentinel

EXPOSE 8000

ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
