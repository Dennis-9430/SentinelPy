# =============================================================================
# Dockerfile Multi-Stage para SentinelPy (SPA mode)
# =============================================================================
# Stage 1: frontend-builder — compila Vite+React SPA
# Stage 2: builder — instala dependencias Python
# Stage 3: runtime — solo lo necesario para correr
#
# Build context: repo root (.)
# docker build -f backend/Dockerfile .
# =============================================================================

# ── Stage 1: Frontend Builder ──────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build

# Copiar solo los archivos de dependencias para cachear
COPY frontend/package.json frontend/pnpm-lock.yaml ./

# Instalar pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Instalar dependencias
RUN pnpm install --frozen-lockfile

# Copiar el resto del frontend
COPY frontend/ .

# Compilar SPA
RUN CI=true pnpm build

# ── Stage 2: Builder (Python) ──────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Cache de pip: solo reinstala si cambia requirements.txt
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: Runtime ───────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Crear usuario no-root para seguridad
RUN addgroup --system --gid 1001 sentinel && \
    adduser --system --uid 1001 sentinel

# Copiar dependencias Python desde builder
COPY --from=builder /usr/local /usr/local

# Copiar frontend compilado desde frontend-builder
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Copiar código de la aplicación backend
COPY backend/ .

# Dar permisos al entrypoint
RUN chmod +x scripts/docker-entrypoint.sh

# Reconstruir caché de paquetes y enlaces simbólicos de Python
RUN ldconfig 2>/dev/null || true

# curl para healthcheck de Docker
USER root
RUN apt-get update -qq && apt-get install -y -qq curl >/dev/null 2>&1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Cambiar a usuario no-root
USER sentinel

EXPOSE 8000

ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
