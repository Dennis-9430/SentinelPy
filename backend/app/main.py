"""Punto de entrada de la aplicación FastAPI.

Configura la aplicación, registra rutas, middlewares,
y maneja el ciclo de vida (inicio/cierre).
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from app.config import settings
from app.api import events, rules, alerts
from app.services.pipeline import Pipeline
from app.services.engine import CorrelationEngine
from app.services.notifier import ConsoleNotifier, MultiNotifier
from app.database import get_session

logger = logging.getLogger(__name__)

# ── Instancias globales ──────────────────────────────────────────────────
engine = CorrelationEngine()
multi_notifier = MultiNotifier()
pipeline = Pipeline(engine=engine)


# ── Async generator para sesiones desde templates (sin Depends) ─────────
async def obtener_session():
    """Versión directa de get_session para usar en rutas de templates."""
    from app.database import async_session
    async with async_session() as session:
        yield session


async def crear_alerta_desde_engine(datos_alerta: dict) -> dict | None:
    """Callback que persiste alertas generadas por el motor de correlación."""
    try:
        from app.models.alert import Alert
        from app.database import async_session as db_session

        async with db_session() as session:
            alerta = Alert(**datos_alerta)
            session.add(alerta)
            await session.commit()
            await session.refresh(alerta)

            alerta_dict = {
                "id": str(alerta.id),
                "rule_id": str(alerta.rule_id),
                "title": alerta.title,
                "severity": alerta.severity,
                "description": alerta.description,
                "status": alerta.status,
            }
            multi_notifier.send_all(alerta_dict)
            logger.info(
                "Alerta creada por engine: %s | %s",
                alerta.title, alerta.severity,
            )
            return alerta_dict
    except Exception as e:
        logger.error("Error en callback de alerta: %s", e, exc_info=True)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicación.

    Inicializa BD, motor de correlación, notificadores y colectores.
    """
    logger.info("Iniciando SentinelPy...")

    # ── Inicializar base de datos ────────────────────────────────────────
    try:
        from app.database import engine as db_engine
        from app.models.base import Base

        async with db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tablas de base de datos verificadas/creadas")
    except Exception as e:
        logger.warning("No se pudo conectar a la base de datos: %s", e)

    # ── Cargar reglas en el motor de correlación ─────────────────────────
    try:
        from app.database import async_session as db_session
        from app.services.rule_service import RuleService

        async with db_session() as session:
            rule_service = RuleService(session)
            reglas = await rule_service.cargar_reglas_activas()
            engine.cargar_reglas(reglas)

        engine.registrar_callback(crear_alerta_desde_engine)
        app.state.engine = engine
        logger.info(
            "Motor de correlación: %d reglas activas", engine.reglas_activas
        )
    except Exception as e:
        logger.warning("No se pudo inicializar motor de correlación: %s", e)
        app.state.engine = None

    # ── Configurar notificadores ─────────────────────────────────────────
    multi_notifier.agregar(ConsoleNotifier())
    app.state.notifier = multi_notifier
    logger.info("Notificadores configurados")

    # ── Iniciar colector syslog ──────────────────────────────────────────
    try:
        from app.services.collector import SyslogCollector

        colector = SyslogCollector(pipeline)
        await colector.start()
        app.state.colector = colector
        logger.info("Sistema de recolección iniciado")
    except Exception as e:
        logger.warning("No se pudo iniciar el colector syslog: %s", e)
        app.state.colector = None

    app.state.pipeline = pipeline
    logger.info("SentinelPy iniciado correctamente")

    yield  # La app corre

    # ── Shutdown graceful ────────────────────────────────────────────────
    logger.info("Deteniendo SentinelPy...")

    if hasattr(app.state, "colector") and app.state.colector:
        await app.state.colector.stop()
        logger.info("Colectores detenidos")

    logger.info("SentinelPy detenido")


# ── Creación de la app FastAPI ──────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# ── Archivos estáticos (CSS, JS, imágenes) ──────────────────────────────
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ── Rutas de la API REST ────────────────────────────────────────────────
app.include_router(events.router)
app.include_router(rules.router)
app.include_router(alerts.router)

# ── Templates ───────────────────────────────────────────────────────────
# Usamos Jinja2 directamente (no Starlette Jinja2Templates) para evitar
# TypeError: unhashable type: 'dict' en Jinja2 3.1.x con Python 3.13
from jinja2 import Environment, FileSystemLoader, select_autoescape

jinja_env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0,
)


def render_template(name: str, context: dict) -> HTMLResponse:
    """Renderiza una plantilla Jinja2 y devuelve una respuesta HTML."""
    template = jinja_env.get_template(name)
    content = template.render(context)
    return HTMLResponse(content)


# ═════════════════════════════════════════════════════════════════════════
# PÁGINAS DEL DASHBOARD WEB (Server-Side Rendering)
# ═════════════════════════════════════════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal del dashboard con métricas en vivo.

    Muestra:
        - Cards con eventos hoy, alertas activas, reglas activas
        - Tabla con los últimos 10 eventos
    """
    async for session in obtener_session():
        from app.models.event import NormalizedEvent
        from app.models.alert import Alert
        from app.services.event_service import EventService
        from app.services.alert_service import AlertService
        from app.services.rule_service import RuleService

        # ── Eventos de hoy ──────────────────────────────────────────────
        inicio_hoy = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        eventos_hoy = await session.execute(
            select(func.count(NormalizedEvent.id)).where(
                NormalizedEvent.event_timestamp >= inicio_hoy
            )
        )
        eventos_hoy_total = eventos_hoy.scalar() or 0

        # ── Últimos 10 eventos ──────────────────────────────────────────
        ev_service = EventService(session)
        ultimos_eventos, _ = await ev_service.listar_eventos(limite=10)

        # ── Alertas activas (no resueltas) ──────────────────────────────
        alertas_activas = await session.execute(
            select(func.count(Alert.id)).where(
                Alert.status.in_(["open", "acknowledged", "investigating"])
            )
        )
        alertas_activas_total = alertas_activas.scalar() or 0

        # ── Reglas activas ──────────────────────────────────────────────
        rule_service = RuleService(session)
        reglas, _ = await rule_service.listar_reglas(estado="active")
        reglas_activas_total = len(reglas)

        return render_template(
            "index.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "eventos_hoy": eventos_hoy_total,
                "alertas_activas": alertas_activas_total,
                "reglas_activas": reglas_activas_total,
                "ultimos_eventos": ultimos_eventos,
            },
        )


@app.get("/events", response_class=HTMLResponse)
async def pagina_eventos(
    request: Request,
    pagina: int = 1,
    severidad: str | None = None,
):
    """Página de eventos con paginación y filtros.

    Argumentos:
        pagina: Número de página (empieza en 1).
        severidad: Filtrar por severidad (opcional).
    """
    async for session in obtener_session():
        from app.services.event_service import EventService

        service = EventService(session)
        limite = 20
        desde = (pagina - 1) * limite

        eventos, total = await service.listar_eventos(
            limite=limite, desde=desde, severidad=severidad
        )
        total_paginas = max(1, (total + limite - 1) // limite)

        return render_template(
            "events.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "eventos": eventos,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
                "total_eventos": total,
                "severidad_seleccionada": severidad,
            },
        )


@app.get("/alerts", response_class=HTMLResponse)
async def pagina_alertas(
    request: Request,
    pagina: int = 1,
    estado: str | None = None,
    severidad: str | None = None,
):
    """Página de alertas con paginación, filtros y formularios de estado."""
    async for session in obtener_session():
        from app.services.alert_service import AlertService

        service = AlertService(session)
        limite = 20
        desde = (pagina - 1) * limite

        alertas, total = await service.listar_alertas(
            limite=limite, desde=desde, estado=estado, severidad=severidad
        )
        total_paginas = max(1, (total + limite - 1) // limite)

        return render_template(
            "alerts.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "alertas": alertas,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
                "total_alertas": total,
                "estado_seleccionado": estado,
                "severidad_seleccionada": severidad,
            },
        )


@app.post("/alerts/{alerta_id}/estado")
async def cambiar_estado_alerta(
    alerta_id: str,
    estado: str = Form(...),
):
    """Actualiza el estado de una alerta desde el dashboard y redirige.

    Recibe el POST del formulario HTML, actualiza el estado,
    y redirige de vuelta a /alerts.
    """
    async for session in obtener_session():
        from app.services.alert_service import AlertService

        estados_validos = {"open", "acknowledged", "investigating", "resolved", "false_positive"}
        if estado not in estados_validos:
            return RedirectResponse(url="/alerts", status_code=303)

        service = AlertService(session)
        await service.actualizar_estado(alerta_id, estado)

        return RedirectResponse(url="/alerts", status_code=303)


@app.get("/rules", response_class=HTMLResponse)
async def pagina_reglas(
    request: Request,
    pagina: int = 1,
    estado: str | None = None,
):
    """Página de reglas de detección con paginación."""
    async for session in obtener_session():
        from app.services.rule_service import RuleService

        service = RuleService(session)
        limite = 20
        desde = (pagina - 1) * limite

        reglas, total = await service.listar_reglas(
            limite=limite, desde=desde, estado=estado
        )
        total_paginas = max(1, (total + limite - 1) // limite)

        return render_template(
            "rules.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "reglas": reglas,
                "pagina_actual": pagina,
                "total_paginas": total_paginas,
                "total_reglas": total,
                "estado_seleccionado": estado,
            },
        )


@app.post("/rules/{regla_id}/toggle")
async def toggle_regla(regla_id: str):
    """Activa/desactiva una regla desde el dashboard."""
    async for session in obtener_session():
        from app.services.rule_service import RuleService

        service = RuleService(session)
        regla = await service.obtener_regla(regla_id)
        if not regla:
            return RedirectResponse(url="/rules", status_code=303)

        nuevo_estado = "disabled" if regla.status == "active" else "active"
        await service.actualizar_regla(regla_id, {"status": nuevo_estado})

        # Recargar engine
        try:
            from app.api.rules import _recargar_engine
            await _recargar_engine(session)
        except Exception:
            pass

        return RedirectResponse(url="/rules", status_code=303)


@app.get("/health")
async def health():
    """Endpoint de health check para Docker y orquestadores."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "reglas_activas": engine.reglas_activas,
    }
