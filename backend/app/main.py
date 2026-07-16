"""Punto de entrada de la aplicación FastAPI.

Configura la aplicación, registra rutas, middlewares,
y maneja el ciclo de vida (inicio/cierre).
"""

import logging

from app.logging_config import setup_logging

setup_logging()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import admin as admin_router
from app.api import agents as agents_router
from app.api import alerts, analysis, events, rules, stats
from app.api import auth as auth_router
from app.api import threat_intel as ti_router
from app.api import users as users_router
from app.config import settings
from app.middleware import register_error_handlers
from app.schemas.common import HealthResponse
from app.services.analysis_service import AnalysisService
from app.services.auth_service import AuthService
from app.services.engine import CorrelationEngine
from app.services.notifier import ConsoleNotifier, MultiNotifier
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
                datos_alerta.get("source_ip") or datos_alerta.get("source") or "unknown"
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

                # ── Seed agente demo (para docker-compose) ────────────
                try:
                    import os as _os

                    from app.services.agent_service import AgentService

                    demo_key = _os.environ.get(
                        "AGENT_API_KEY", "spy_demo-key-change-me"
                    )
                    agent_svc = AgentService(seed_session)
                    existing = await agent_svc.obtener_por_api_key(demo_key)
                    if existing:
                        logger.info("Agente demo ya existe con key correcta")
                    else:
                        # Buscar por nombre — puede tener key vieja
                        from sqlalchemy import select as _sel

                        from app.models.agent import Agent

                        result = await seed_session.execute(
                            _sel(Agent).where(Agent.name == "demo-agent")
                        )
                        found = result.scalar_one_or_none()
                        demo_hash = AuthService.hash_password(demo_key)
                        if found:
                            found.api_key_hash = demo_hash
                            found.active = True
                            await seed_session.commit()
                            logger.info(
                                "Agente demo: key actualizada desde AGENT_API_KEY env"
                            )
                        else:
                            demo_agent = Agent(
                                name="demo-agent",
                                hostname="demo-agent",
                                api_key_hash=demo_hash,
                                active=True,
                            )
                            seed_session.add(demo_agent)
                            await seed_session.commit()
                            logger.info(
                                "Agente demo creado (key from AGENT_API_KEY env)"
                            )
                except Exception as e:
                    logger.warning("No se pudo seedear agente demo: %s", e)
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

    # ── Inicializar Threat Intelligence ──────────────────────────────────
    try:
        from app.services.threat_intel_service import ThreatIntelService
        from app.services.ti_providers.abuseipdb import AbuseIPDBProvider

        ti_service = ThreatIntelService()
        if settings.abuseipdb_api_key:
            ti_service.register_provider(AbuseIPDBProvider(settings.abuseipdb_api_key))
            logger.info("Provider AbuseIPDB registrado")
        if settings.otx_api_key:
            from app.services.ti_providers.otx import OTXProvider
            ti_service.register_provider(OTXProvider(settings.otx_api_key))
            logger.info("Provider OTX registrado")
        elif not settings.abuseipdb_api_key:
            # OTX works without API key for basic lookups
            from app.services.ti_providers.otx import OTXProvider
            ti_service.register_provider(OTXProvider())
            logger.info("Provider OTX registrado (sin API key)")
        if settings.virustotal_api_key:
            from app.services.ti_providers.virustotal import VirusTotalProvider
            ti_service.register_provider(VirusTotalProvider(settings.virustotal_api_key))
            logger.info("Provider VirusTotal registrado")
        app.state.ti_service = ti_service
        pipeline.ti_service = ti_service
        logger.info("Servicio de Threat Intelligence inicializado")
    except Exception as e:
        logger.warning("No se pudo inicializar Threat Intelligence: %s", e)
        app.state.ti_service = None

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

# ── Error handlers globales ─────────────────────────────────────────────
register_error_handlers(app)

# ── API v1: todos los endpoints REST bajo /api/v1 ──────────────────────
from fastapi import APIRouter

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(events.router)
v1_router.include_router(rules.router)
v1_router.include_router(alerts.router)
v1_router.include_router(auth_router.router)
v1_router.include_router(users_router.router)
v1_router.include_router(admin_router.router)
v1_router.include_router(analysis.router)
v1_router.include_router(stats.router)
v1_router.include_router(ti_router.router)
app.include_router(v1_router)

# ── Backward compat: /api/ sin versionado (deprecated, para tests) ─────
compat_router = APIRouter(prefix="/api")
compat_router.include_router(events.router)
compat_router.include_router(rules.router)
compat_router.include_router(alerts.router)
compat_router.include_router(auth_router.router)
compat_router.include_router(users_router.router)
compat_router.include_router(admin_router.router)
compat_router.include_router(analysis.router)
compat_router.include_router(stats.router)
compat_router.include_router(ti_router.router)
app.include_router(compat_router)

# ── Agent endpoints (v2 — ya versionados independientemente) ────────────
app.include_router(agents_router.router)


# ── Health check (sin auth, sin versionado — para orquestadores) ────────
@app.get("/health", response_model=HealthResponse)
async def health():
    """Endpoint de health check para Docker y orquestadores."""
    return HealthResponse(
        status="healthy",
        app=settings.app_name,
        version=settings.app_version,
        reglas_activas=engine.reglas_activas,
        ventanas_activas=engine.ventanas_activas,
    )


# ═════════════════════════════════════════════════════════════════════════
# PÁGINAS DEL DASHBOARD WEB (Server-Side Rendering)
# ═════════════════════════════════════════════════════════════════════════
# NOTA: Las rutas de templates fueron reemplazadas por la SPA.
# El catch-all al final del archivo sirve frontend/dist/index.html
# para todas las rutas que no coincidan con la API.


# ═════════════════════════════════════════════════════════════════════════
# SPA Catch-All — Sirve el frontend para cualquier ruta no-API
# ═════════════════════════════════════════════════════════════════════════
# IMPORTANTE: Esta sección debe estar al FINAL del archivo, después de
# TODAS las rutas de API.
#
# Approach: Route-based catch-all. FastAPI registra rutas en orden, así
# que los endpoints de API (`/api/*`, `/health`, etc.) matchean primero.
# El `/{full_path:path}` al final solo captura lo que ningún endpoint
# previo matcheó — archivos estáticos de Vite o rutas SPA.
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
    _spa_index = _os.path.join(_spa_dir, "index.html")

    # MIME types para assets de Vite
    _MIME_TYPES: dict[str, str] = {
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".eot": "application/vnd.ms-fontobject",
        ".webp": "image/webp",
        ".map": "application/json",
    }

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """Sirve archivos estáticos de dist/ o fallback a index.html.

        Las rutas de API (`/api/*`) y endpoints explícitos (`/health`,
        etc.) ya están registrados ANTES de este catch-all, así que
        FastAPI los matchea primero y nunca llegan acá.
        """
        # Servir archivo real desde dist/ si existe
        candidate = _os.path.normpath(_os.path.join(_spa_dir, full_path))
        if _os.path.isfile(candidate):
            ext = _os.path.splitext(candidate)[1].lower()
            mime = _MIME_TYPES.get(ext, "application/octet-stream")
            return FileResponse(candidate, media_type=mime)

        # Fallback: index.html para que React Router maneje la ruta
        return FileResponse(_spa_index, media_type="text/html")

    logger.info("SPA catch-all activo desde: %s", _spa_dir)
else:
    logger.warning(
        "Directorio SPA no encontrado. Buscado en: %s. "
        "Ejecutá 'pnpm build' en frontend/ para servir la SPA.",
        _spa_candidates,
    )
