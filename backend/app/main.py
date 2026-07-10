"""Punto de entrada de la aplicación FastAPI.

Configura la aplicación, registra rutas, middlewares,
y maneja el ciclo de vida (inicio/cierre).
"""

import csv
import io
import logging

from app.logging_config import setup_logging

setup_logging()

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.api import admin as admin_router
from app.api import agents as agents_router
from app.api import alerts, analysis, events, rules
from app.api import auth as auth_router
from app.api import users as users_router
from app.config import settings
from app.models.user import User  # noqa: F401 — usado por seed en lifespan
from app.services.auth_service import AuthService
from app.services.engine import CorrelationEngine
from app.services.notifier import ConsoleNotifier, MultiNotifier
from app.services.analysis_service import AnalysisService
from app.services.pipeline import Pipeline

logger = logging.getLogger(__name__)

# ── Instancias globales ──────────────────────────────────────────────────
engine = CorrelationEngine()
multi_notifier = MultiNotifier()
pipeline = Pipeline(engine=engine)


async def crear_alerta_desde_engine(datos_alerta: dict) -> dict | None:
    """Callback que persiste alertas generadas por el motor de correlación."""
    try:
        from app.database import async_session as db_session
        from app.models.alert import Alert

        async with db_session() as session:
            alerta = Alert(**datos_alerta)

            # Derive group_key from alert data
            source_ip = (
                datos_alerta.get("source_ip")
                or datos_alerta.get("source")
                or "unknown"
            )
            rule_id = str(alerta.rule_id)
            alerta.group_key = f"{rule_id}:{source_ip}"

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
            await multi_notifier.send_all(alerta_dict)
            logger.info(
                "Alerta creada por engine: %s | %s",
                alerta.title,
                alerta.severity,
            )
            return alerta_dict
    except Exception as e:
        logger.error("Error en callback de alerta: %s", e, exc_info=True)
        return None


async def actualizar_alerta_desde_engine(datos: dict):
    """Callback para actualizar contadores dentro de ventana temporal.

    Cuando el motor de correlación detecta un evento dentro de la
    ventana temporal de una regla, llama a este callback para
    incrementar event_count y actualizar last_event_at en la alerta existente.
    """
    try:
        from app.database import async_session as db_session
        from app.services.alert_service import AlertService

        async with db_session() as session:
            service = AlertService(session)
            await service.actualizar_contadores(
                rule_id=datos["rule_id"],
                event_count=datos["event_count"],
                last_event_at=datos["last_event_at"],
            )
    except Exception as e:
        logger.error("Error en callback de actualización: %s", e, exc_info=True)


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

        # ── Seed usuario admin ──────────────────────────────────────────
        try:
            from app.database import async_session as db_session

            async with db_session() as seed_session:
                auth_svc = AuthService(seed_session)
                try:
                    admin_user = await auth_svc.crear_usuario(
                        username=settings.admin_username,
                        password=settings.admin_password,
                        role="admin",
                    )
                    logger.info("Admin creado: %s", admin_user.username)
                except ValueError:
                    logger.info("Admin ya existe, omitiendo seed")
        except Exception as e:
            logger.warning("No se pudo seedear admin: %s", e)
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
        engine.registrar_callback_actualizar(actualizar_alerta_desde_engine)
        app.state.engine = engine
        logger.info("Motor de correlación: %d reglas activas", engine.reglas_activas)
    except Exception as e:
        logger.warning("No se pudo inicializar motor de correlación: %s", e)
        app.state.engine = None

    # ── Configurar notificadores ─────────────────────────────────────────
    multi_notifier.agregar(ConsoleNotifier())

    # EmailNotifier (solo si hay configuración SMTP)
    if settings.smtp_user:
        from app.services.email_notifier import EmailNotifier

        multi_notifier.agregar(
            EmailNotifier(), min_severity=settings.notify_min_severity
        )
        logger.info(
            "EmailNotifier configurado para severidad >= %s",
            settings.notify_min_severity,
        )

    # WebhookNotifier (solo si hay URL configurada)
    if settings.webhook_url:
        from app.services.webhook_notifier import WebhookNotifier

        multi_notifier.agregar(
            WebhookNotifier(), min_severity=settings.notify_min_severity
        )
        logger.info(
            "WebhookNotifier configurado para severidad >= %s",
            settings.notify_min_severity,
        )

    app.state.notifier = multi_notifier
    logger.info("Notificadores configurados")

    # ── Inicializar servicio de análisis ─────────────────────────────────
    try:
        from app.database import async_session as db_session

        analysis_service = AnalysisService(db_session)
        await analysis_service.init_async()
        app.state.analysis_service = analysis_service
        pipeline.analysis_service = analysis_service
        logger.info("Servicio de análisis inicializado")
    except Exception as e:
        logger.warning("No se pudo inicializar análisis: %s", e)
        app.state.analysis_service = None

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

    if hasattr(app.state, "analysis_service") and app.state.analysis_service:
        await app.state.analysis_service.shutdown()

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
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(admin_router.router)
app.include_router(agents_router.router)
app.include_router(analysis.router)

# ═════════════════════════════════════════════════════════════════════════
# PÁGINAS DEL DASHBOARD WEB (Server-Side Rendering)
# ═════════════════════════════════════════════════════════════════════════
# NOTA: Las rutas de templates fueron reemplazadas por el SPA.
# El catch-all al final del archivo sirve frontend/dist/index.html
# para todas las rutas que no coincidan con la API.


@app.get("/health")
async def health():
    """Endpoint de health check para Docker y orquestadores."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "reglas_activas": engine.reglas_activas,
        "ventanas_activas": engine.ventanas_activas,
    }


# ═════════════════════════════════════════════════════════════════════════
# GRÁFICAS (Chart.js) — Datos para el dashboard
# ═════════════════════════════════════════════════════════════════════════


@app.get("/api/events/stats")
async def stats_eventos(horas: int = 24):
    """Estadísticas de eventos para gráficas del dashboard.

    Retorna:
        timeline: Eventos por hora en las últimas N horas.
        por_severidad: Conteo de eventos agrupado por severidad.
    """
    from app.database import async_session as _db_session

    async with _db_session() as session:
        from app.models.event import NormalizedEvent

        ahora = datetime.now(UTC)
        desde = ahora - timedelta(hours=horas)

        # ── Timeline: eventos por hora ──────────────────────────────────
        timeline_raw = await session.execute(
            select(
                func.date_trunc("hour", NormalizedEvent.event_timestamp).label("hora"),
                func.count(NormalizedEvent.id).label("total"),
            )
            .where(NormalizedEvent.event_timestamp >= desde)
            .group_by("hora")
            .order_by("hora")
        )
        timeline = [
            {"hora": row.hora.isoformat(), "total": row.total} for row in timeline_raw
        ]

        # ── Por severidad ────────────────────────────────────────────────
        sev_raw = await session.execute(
            select(
                NormalizedEvent.severity,
                func.count(NormalizedEvent.id).label("total"),
            ).group_by(NormalizedEvent.severity)
        )
        por_severidad = {row.severity or "unknown": row.total for row in sev_raw}

        return {"timeline": timeline, "por_severidad": por_severidad}


@app.get("/api/alerts/stats")
async def stats_alertas():
    """Estadísticas de alertas para gráficas del dashboard.

    Retorna:
        por_severidad: Conteo de alertas agrupado por severidad.
        por_estado: Conteo de alertas agrupado por estado.
    """
    from app.database import async_session as _db_session

    async with _db_session() as session:
        from app.models.alert import Alert

        # ── Por severidad ────────────────────────────────────────────────
        sev_raw = await session.execute(
            select(
                Alert.severity,
                func.count(Alert.id).label("total"),
            ).group_by(Alert.severity)
        )
        por_severidad = {row.severity or "unknown": row.total for row in sev_raw}

        # ── Por estado ───────────────────────────────────────────────────
        est_raw = await session.execute(
            select(
                Alert.status,
                func.count(Alert.id).label("total"),
            ).group_by(Alert.status)
        )
        por_estado = {row.status or "unknown": row.total for row in est_raw}

        return {"por_severidad": por_severidad, "por_estado": por_estado}


# ═════════════════════════════════════════════════════════════════════════
# EXPORTACIÓN CSV
# ═════════════════════════════════════════════════════════════════════════


@app.get("/api/alerts/exportar")
async def exportar_alertas_csv(
    estado: str | None = None,
    severidad: str | None = None,
):
    """Exporta alertas a CSV con los filtros actuales.

    Descarga un archivo CSV con columnas: id, título, severidad,
    estado, event_count, created_at, resolved_at, descripción.

    Los filtros (estado, severidad) se aplican igual que en la
    interfaz web para exportar exactamente lo que se está viendo.
    """
    from app.database import async_session as _db_session

    async with _db_session() as session:
        from app.services.alert_service import AlertService

        service = AlertService(session)
        alertas, _ = await service.listar_alertas(
            limite=10000, estado=estado, severidad=severidad
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "titulo",
                "severidad",
                "estado",
                "eventos",
                "creada",
                "resuelta",
                "descripcion",
            ]
        )

        for a in alertas:
            writer.writerow(
                [
                    str(a.id),
                    a.title,
                    a.severity,
                    a.status,
                    a.event_count,
                    a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
                    a.resolved_at.strftime("%Y-%m-%d %H:%M:%S")
                    if a.resolved_at
                    else "",
                    a.description or "",
                ]
            )

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=alertas.csv",
            },
        )


# ═════════════════════════════════════════════════════════════════════════
# SPA Catch-All — Sirve el frontend para cualquier ruta no-API
# ═════════════════════════════════════════════════════════════════════════
# IMPORTANTE: Esta sección debe estar al FINAL del archivo, después de
# TODAS las rutas de API. Usa un middleware 404 fallback + StaticFiles
# para assets de Vite.
import os as _os

from fastapi.responses import FileResponse

_base = _os.path.dirname(__file__)
_spa_candidates = [
    _os.path.normpath(
        _os.path.join(_base, "..", "..", "frontend", "dist")
    ),  # local dev
    _os.path.normpath(_os.path.join(_base, "..", "frontend", "dist")),  # docker
]
_spa_dir = next((d for d in _spa_candidates if _os.path.isdir(d)), None)

if _spa_dir:
    # Montar los assets compilados por Vite (JS, CSS, imágenes, etc.)
    # Se sirven primero para que archivos reales tengan prioridad.
    app.mount(
        "/",
        StaticFiles(directory=_spa_dir, html=False),
        name="spa_assets",
    )

    # Middleware fallback: si StaticFiles devuelve 404 y no es ruta API,
    # servir index.html para que React Router maneje la ruta.
    @app.middleware("http")
    async def _spa_fallback(request: Request, call_next):
        response = await call_next(request)
        if (
            response.status_code == 404
            and not request.url.path.startswith("/api/")
            and not request.url.path.startswith("/static/")
        ):
            index_path = _os.path.join(_spa_dir, "index.html")
            if _os.path.isfile(index_path):
                return FileResponse(index_path, media_type="text/html")
        return response

    logger.info("SPA catch-all activo desde: %s", _spa_dir)
else:
    logger.warning(
        "Directorio SPA no encontrado. Buscado en: %s. "
        "Ejecutá 'pnpm build' en frontend/ para servir la SPA.",
        _spa_candidates,
    )
