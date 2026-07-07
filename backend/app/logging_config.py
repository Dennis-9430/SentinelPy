"""Configure structured JSON logging for the application.

Replaces plain-text ``logging.basicConfig`` with JSON-formatted
log lines written to stdout, suitable for ingestion by Datadog,
Grafana Loki, ELK, or any JSON-aware log collector.
"""

import logging
import sys

from pythonjsonlogger import jsonlogger

from app.config import settings


def setup_logging() -> None:
    """Configure the root logger to emit structured JSON lines to stdout.

    Reads ``LOG_LEVEL`` from :attr:`app.config.Settings.log_level` (default:
    ``INFO``).  Applies the same level to an ``app.logging`` named logger
    so that application code can import and use a dedicated logger if desired.

    Any pre-existing handlers on the root logger are removed first to
    guarantee a clean configuration.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s %(module)s %(funcName)s %(lineno)d",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    # Named logger — useful for filtering in log aggregators
    app_logger = logging.getLogger("app.logging")
    app_logger.setLevel(level)
    app_logger.propagate = True
