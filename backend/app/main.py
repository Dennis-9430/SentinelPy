"""SentinelPy FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from app.config import settings
from app.api import events, rules, alerts


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup / shutdown."""
    # TODO: initialize DB, collectors, engine
    yield
    # TODO: graceful shutdown


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# --- API routes ---
app.include_router(events.router)
app.include_router(rules.router)
app.include_router(alerts.router)


# --- Web UI (Jinja2 templates for N1) ---
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "app_name": settings.app_name},
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "app": settings.app_name, "version": settings.app_version}
