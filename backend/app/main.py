"""Punto de entrada de la aplicación FastAPI.

Configura la aplicación, registra rutas, middlewares,
y maneja el ciclo de vida (inicio/cierre).
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from app.config import settings
from app.api import events, rules, alerts


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicación.

    Al iniciar:
        - Conecta la base de datos
        - Inicia los colectores (syslog, file watchers)
        - Carga las reglas activas en el motor de correlación

    Al cerrar:
        - Detiene colectores gracefulmente
        - Cierra conexiones de base de datos
    """
    # TODO: inicializar DB, colectores y motor
    yield
    # TODO: shutdown graceful


# ── Creación de la app FastAPI ──────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# ── Rutas de la API REST ────────────────────────────────────────────────
# Cada router se importa de app/api/ y se incluye con su prefijo
app.include_router(events.router)
app.include_router(rules.router)
app.include_router(alerts.router)

# ── Templates para la interfaz web (Jinja2) ─────────────────────────────
# En Nivel 1 usamos server-side rendering con Jinja2 + Tailwind
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal del dashboard.

    Muestra cards con métricas (eventos hoy, alertas activas, reglas)
    y la tabla de eventos recientes.
    """
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "app_name": settings.app_name},
    )


@app.get("/health")
async def health():
    """Endpoint de health check.

    Usado por Docker Compose y orquestadores para verificar
    que la aplicación responde correctamente.
    """
    return {"status": "healthy", "app": settings.app_name, "version": settings.app_version}
