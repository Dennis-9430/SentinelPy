"""Script para poblar la base de datos con datos de demostración.

Genera eventos de prueba con distintas severidades, fuentes, y tipos,
reglas de detección (activas y desactivadas), y alertas en varios estados.

Uso:
    python -m scripts.seed_demo_data        # desde backend/
    python scripts/seed_demo_data.py        # desde backend/

Requiere que la base de datos PostgreSQL esté accesible (local o Docker).
Usa la configuración de app.config (database_url).
"""

import asyncio
import logging
import sys
from pathlib import Path

# Agregar backend/ al path para que se pueda ejecutar como script directo
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from datetime import UTC, datetime, timedelta

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("seed")


# ── Datos de ejemplo ──────────────────────────────────────────────────────────

EVENT_TYPES = [
    ("auth_failure", "high", "Fallo de autenticación SSH desde {ip}"),
    ("auth_success", "info", "Inicio de sesión exitoso desde {ip}"),
    ("port_scan", "critical", "Escaneo de puertos detectado desde {ip}"),
    ("process_create", "medium", "Proceso sospechoso creado: {proc}"),
    ("dns_query", "low", "Consulta DNS a dominio desconocido: {dominio}"),
    ("firewall_block", "high", "Firewall bloqueó tráfico entrante desde {ip}"),
    ("malware_detected", "critical", "Archivo malicioso detectado: {file}"),
    ("vpn_connect", "info", "Conexión VPN establecida desde {ip}"),
    ("vpn_disconnect", "low", "Conexión VPN finalizada desde {ip}"),
    ("privilege_escalation", "critical", "Escalada de privilegios detectada en {proc}"),
]

SOURCES = [
    "servidor-web-01",
    "servidor-web-02",
    "firewall-panel",
    "servidor-correo-01",
    "dns-primario",
    "vpn-gateway",
    "base-datos-01",
    "balanceador-01",
    "waf-01",
]

PROCESSES = [
    "powershell.exe",
    "cmd.exe",
    "bash",
    "python3",
    "nginx",
    "sshd",
    "vsftpd",
    "docker",
]

DOMAINS = [
    "malware-evil.com",
    "phishing.xyz",
    "unknown-panel.net",
    "c2-server.io",
    "data-exfil.biz",
]

FILES = [
    "/tmp/ransomware.exe",
    "/var/www/html/shell.php",
    "/root/.ssh/authorized_keys",
    "C:\\Users\\Public\\malware.dll",
]

SEVERITIES = ["critical", "high", "medium", "low", "info"]

RULES = [
    {
        "title": "Detección de escaneo de puertos",
        "description": "Genera alerta cuando se detecta un escaneo de puertos desde una IP externa. "
        "Indica reconocimiento activo por parte de un atacante.",
        "severity": "critical",
        "status": "active",
        "conditions": {"field": "event_type", "operator": "eq", "value": "port_scan"},
        "alert_title": "Escaneo de Puertos Detectado",
        "alert_severity": "critical",
        "author": "Equipo SOC",
        "correlation_window": 300,
        "tags": ["attack.t1046", "mitre.reconnaissance"],
        "references": ["https://attack.mitre.org/techniques/T1046/"],
        "false_positives": "Herramientas de monitoreo interno como Nmap o Zmap.",
    },
    {
        "title": "Fuerza bruta SSH",
        "description": "Múltiples fallos de autenticación SSH en ventana de 5 minutos. "
        "Indica intento de acceso no autorizado.",
        "severity": "high",
        "status": "active",
        "conditions": {
            "field": "event_type",
            "operator": "eq",
            "value": "auth_failure",
        },
        "alert_title": "Posible Fuerza Bruta SSH",
        "alert_severity": "high",
        "author": "Equipo SOC",
        "correlation_window": 300,
        "tags": ["attack.t1110", "mitre.credential-access"],
        "references": ["https://attack.mitre.org/techniques/T1110/"],
        "false_positives": None,
    },
    {
        "title": "Malware detectado en endpoints",
        "description": "Alerta cuando se detecta un archivo malicioso en algún endpoint. "
        "Requiere investigación inmediata.",
        "severity": "critical",
        "status": "active",
        "conditions": {
            "field": "event_type",
            "operator": "eq",
            "value": "malware_detected",
        },
        "alert_title": "Malware Detectado",
        "alert_severity": "critical",
        "author": "Equipo SOC",
        "tags": ["attack.t1204", "mitre.execution"],
        "references": [],
        "false_positives": "Firmas de AV desactualizadas o falsos positivos conocidos.",
    },
    {
        "title": "Escalada de privilegios",
        "description": "Detección de escalada de privilegios en procesos del sistema. "
        "Indica posible compromiso de cuenta.",
        "severity": "critical",
        "status": "active",
        "conditions": {
            "field": "event_type",
            "operator": "eq",
            "value": "privilege_escalation",
        },
        "alert_title": "Escalada de Privilegios",
        "alert_severity": "critical",
        "author": "Equipo SOC",
        "correlation_window": 60,
        "tags": ["attack.t1068", "mitre.privilege-escalation"],
        "references": ["https://attack.mitre.org/techniques/T1068/"],
        "false_positives": None,
    },
    {
        "title": "Conexiones a dominios maliciosos",
        "description": "Detección de consultas DNS a dominios identificados como maliciosos. "
        "Indica posible comunicación C2.",
        "severity": "high",
        "status": "active",
        "conditions": {"field": "event_type", "operator": "eq", "value": "dns_query"},
        "alert_title": "Dominio Malicioso Detectado",
        "alert_severity": "high",
        "author": "Equipo SOC",
        "tags": ["attack.t1071", "mitre.command-and-control"],
        "references": [],
        "false_positives": "Dominios legítimos no categorizados correctamente.",
    },
    {
        "title": "Firewall: tráfico bloqueado",
        "description": "Tráfico entrante bloqueado por el firewall perimetral. "
        "Monitoreo de intentos de conexión externa.",
        "severity": "medium",
        "status": "active",
        "conditions": {
            "field": "event_type",
            "operator": "eq",
            "value": "firewall_block",
        },
        "alert_title": "Tráfico Bloqueado por Firewall",
        "alert_severity": "medium",
        "author": "Equipo SOC",
        "tags": ["network"],
        "references": [],
        "false_positives": "Escaneos automáticos de internet (Shodan, Censys).",
    },
    {
        "title": "Regla legacy: procesos anticuados",
        "description": "Regla desactivada por migración a nueva plataforma. "
        "Se mantiene por compatibilidad con informes históricos.",
        "severity": "low",
        "status": "disabled",
        "conditions": {
            "field": "event_type",
            "operator": "eq",
            "value": "process_create",
        },
        "alert_title": "[LEGACY] Proceso Detectado",
        "alert_severity": "low",
        "author": "Admin",
        "tags": ["legacy", "deprecated"],
        "references": [],
        "false_positives": None,
    },
]

ALERT_STATES = [
    {"status": "open", "prob": 0.30},
    {"status": "acknowledged", "prob": 0.15},
    {"status": "investigating", "prob": 0.15},
    {"status": "resolved", "prob": 0.30},
    {"status": "false_positive", "prob": 0.10},
]

RESOLUTION_NOTES = [
    "Se investigó y se confirmó como falso positivo.",
    "Se contuvo el incidente y se parcheó la vulnerabilidad.",
    "Se bloqueó la IP origen y se notificó al equipo de red.",
    "El antivirus eliminó el archivo malicioso automáticamente.",
    "Se revisaron los logs y no se encontró actividad maliciosa real.",
    None,
]


# ── Lógica de seed ───────────────────────────────────────────────────────────


def _random_ip(seed: int) -> str:
    """Genera una IP pseudo-aleatoria determinista."""
    return f"10.0.{seed % 255}.{(seed * 7) % 255}"


def _random_choice(seed: int, items: list) -> str:
    """Selecciona un elemento pseudo-aleatorio determinista."""
    return items[seed % len(items)]


async def seed_demo_data():
    """Genera datos demo conectándose directo a la base de datos."""
    from app.database import async_session
    from app.services.alert_service import AlertService
    from app.services.event_service import EventService
    from app.services.rule_service import RuleService

    now = datetime.now(UTC)

    async with async_session() as session:
        # ── 1. Reglas ─────────────────────────────────────────────────────
        logger.info("Creando reglas de detección...")
        rule_service = RuleService(session)
        created_rules = []
        for rule_data in RULES:
            existing = await rule_service.listar_reglas(estado=rule_data["status"])
            exists = any(r.title == rule_data["title"] for r in existing[0])
            if exists:
                logger.info("  Regla ya existe: %s", rule_data["title"])
                # Buscarla para referenciarla
                all_rules, _ = await rule_service.listar_reglas(limite=100)
                for r in all_rules:
                    if r.title == rule_data["title"]:
                        created_rules.append(r)
                        break
                continue
            regla = await rule_service.crear_regla(rule_data)
            created_rules.append(regla)
            logger.info("  Regla creada: %s (%s)", regla.title, regla.status)

        active_rules = [r for r in created_rules if r.status == "active"]

        # ── 2. Eventos ────────────────────────────────────────────────────
        logger.info("Generando eventos de prueba...")
        event_service = EventService(session)
        total_events = 150
        created_events = 0

        for i in range(total_events):
            event_type, severity, desc_template = _random_choice(i, EVENT_TYPES)
            source = _random_choice(i * 3, SOURCES)
            source_ip = _random_ip(i + 100)

            # Timestamp distribuido en las últimas 24 horas
            hours_ago = (total_events - i) * 24 / total_events
            event_ts = now - timedelta(hours=hours_ago)

            # Variar la severidad con el tipo (algunos tipos tienen severidad fija)
            if severity != _random_choice(i, SEVERITIES):
                # Mezclar un poco
                severity = _random_choice(i * 7, SEVERITIES)

            desc = desc_template.format(
                ip=source_ip,
                proc=_random_choice(i * 11, PROCESSES),
                dominio=_random_choice(i * 13, DOMAINS),
                file=_random_choice(i * 17, FILES),
            )

            evento_data = {
                "source": source,
                "collector_type": "syslog",
                "event_timestamp": event_ts,
                "event_type": event_type,
                "severity": severity,
                "description": desc,
                "source_ip": source_ip,
                "destination_ip": _random_ip(i + 200),
                "source_port": 1024 + (i % 32768),
                "destination_port": [22, 80, 443, 3306, 8080][i % 5],
                "protocol": _random_choice(i * 19, ["TCP", "UDP", "ICMP"]),
                "user_name": _random_choice(
                    i * 23, ["admin", "dperez", "jramirez", None, None]
                ),
                "process_name": _random_choice(i * 29, PROCESSES)
                if event_type == "process_create"
                else None,
            }

            await event_service.crear_evento(evento_data)
            created_events += 1

        logger.info("  %d eventos creados en las últimas 24h", created_events)

        # ── 3. Alertas ────────────────────────────────────────────────────
        logger.info("Generando alertas de demostración...")
        alert_service = AlertService(session)
        created_alerts = 0

        for i, rule in enumerate(active_rules):
            # Cada regla activa genera de 2 a 5 alertas
            num_alerts = 2 + (i % 4)

            for j in range(num_alerts):
                # Determinar estado según distribución
                r = (i * 100 + j * 7) % 100
                cumulative = 0
                chosen_status = "open"
                for state in ALERT_STATES:
                    cumulative += int(state["prob"] * 100)
                    if r < cumulative:
                        chosen_status = state["status"]
                        break

                hours_ago = (j + 1) * 4 + (i * 2)
                alert_ts = now - timedelta(hours=hours_ago)

                alert_data = {
                    "rule_id": rule.id,
                    "title": rule.alert_title,
                    "severity": rule.alert_severity,
                    "description": f"Alerta generada por regla '{rule.title}'. "
                    f"Evento relacionado: {_random_choice(j * 37, EVENT_TYPES)[2].format(ip=_random_ip(j + 300), proc='explorer.exe', dominio='example.com', file='malware.exe')}",
                    "status": chosen_status,
                    "event_count": 1 + (j * 3),
                    "first_event_at": alert_ts - timedelta(minutes=5),
                    "last_event_at": alert_ts,
                }

                if chosen_status in ("resolved", "false_positive"):
                    alert_data["resolved_at"] = now - timedelta(hours=1)
                    note = _random_choice(j * 41, RESOLUTION_NOTES)
                    if note:
                        alert_data["resolution_notes"] = note

                await alert_service.crear_alerta(alert_data)
                created_alerts += 1

        logger.info("  %d alertas creadas con estados variados", created_alerts)

        await session.commit()

    logger.info("=" * 50)
    logger.info("Seed completado exitosamente")
    logger.info("  Reglas: %d (%d activas)", len(created_rules), len(active_rules))
    logger.info("  Eventos: %d", created_events)
    logger.info("  Alertas: %d", created_alerts)
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(seed_demo_data())
