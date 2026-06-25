# Fase 07: Notificaciones por Email y Webhook

## Objetivo

Agregar notificaciones automáticas cuando se generen alertas de severidad
crítica o alta. Un SIEM que no notifica no sirve para producción — nadie
va a estar mirando el dashboard 24/7. Con notificaciones por email y
webhook, los analistas reciben las alertas en su canal de comunicación
habitual (correo, Slack, Discord, etc.).

## Arquitectura Propuesta

```
                    ┌──────────────────────┐
                    │   CorrelationEngine  │
                    │   detecta alerta     │
                    └────────┬─────────────┘
                             │
                             ▼
                    ┌──────────────────────┐
                    │   AlertService       │
                    │   crea alerta en BD  │
                    └────────┬─────────────┘
                             │
                             ▼
                    ┌──────────────────────┐
                    │   Notifier System     │
                    │                      │
                    │  ┌──────────────┐    │
                    │  │ EmailNotifier│    │
                    │  │ → SMTP      │    │
                    │  └──────────────┘    │
                    │  ┌──────────────┐    │
                    │  │ SlackNotifier│    │
                    │  │ → Webhook   │    │
                    │  └──────────────┘    │
                    │  ┌──────────────┐    │
                    │  │ LogNotifier  │    │
                    │  │ → consola    │    │
                    │  └──────────────┘    │
                    └──────────────────────┘
```

## Componentes a Implementar

### 1. EmailNotifier

Envío de alertas por email usando SMTP asíncrono.

**Configuración (config.py):**

```python
# ── Notificaciones Email ──────────────────────────────────────
smtp_host: str = "smtp.gmail.com"
smtp_port: int = 587
smtp_user: str = ""       # Email remitente
smtp_password: str = ""    # Contraseña de aplicación
smtp_from: str = ""        # Dirección From
notify_to: list[str] = []  # Lista de destinatarios
notify_min_severity: str = "high"  # critical | high | medium
```

**Formato del email:**

```
Asunto: [CRITICAL] SentinelPy — Posible fuerza bruta SSH detectada

├── Regla:      Fuerza bruta SSH
├── Severidad:  critical
├── Eventos:    15 en 60 segundos
├── Creada:     2024-01-15 10:00:00 UTC
│
└── Descripción:
    Múltiples intentos de autenticación como root
    desde 10.0.0.1 en los últimos 60 segundos.
```

### 2. WebhookNotifier (Slack / Discord / Genérico)

Envío de alertas a webhooks HTTP (Slack, Discord, Teams, etc.).

**Payload Slack:**

```json
{
    "attachments": [{
        "color": "#dc2626",
        "title": "🚨 [CRITICAL] Posible fuerza bruta SSH",
        "fields": [
            {"title": "Regla", "value": "Fuerza bruta SSH", "short": true},
            {"title": "Severidad", "value": "critical", "short": true},
            {"title": "Eventos", "value": "15", "short": true},
            {"title": "Fuente", "value": "10.0.0.1", "short": true}
        ],
        "footer": "SentinelPy",
        "ts": 1705312800
    }]
}
```

**Configuración:**

```python
# ── Notificaciones Webhook ────────────────────────────────────
webhook_urls: list[str] = []    # URLs de webhook (Slack, Discord, etc.)
notify_on_severity: list[str] = ["critical", "high"]
```

### 3. LogNotifier (ya existe como ConsoleNotifier)

Registro de alertas en consola/logs. Ya implementado como `ConsoleNotifier`
dentro de `MultiNotifier`. Se mantiene para debug en desarrollo.

### 4. Sistema de Canales por Severidad

Cada canal (email, webhook, consola) debería poder configurarse
para qué severidades notifica:

| Canal | critical | high | medium | low | Por defecto |
|-------|----------|------|--------|-----|-------------|
| Email | ✅ | ✅ | ❌ | ❌ | critical+high |
| Slack | ✅ | ✅ | ❌ | ❌ | critical+high |
| Log | ✅ | ✅ | ✅ | ✅ | todas |

### 5. Notification History (opcional)

Tabla opcional para registrar qué notificaciones se enviaron:

```python
class NotificationLog(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "notification_log"

    alert_id:      UUID   # FK → alerts.id
    channel:       str    # "email" | "slack" | "console"
    severity:      str    # severidad de la alerta original
    status:        str    # "sent" | "failed"
    error:         str    # mensaje de error si falló
    delivered_at:  datetime
```

Útil para auditoría y debugging de notificaciones fallidas.

## Dependencias Nuevas

```txt
# Notificaciones
aiosmtplib>=3.0.0          # SMTP asíncrono
httpx>=0.28.0              # Webhooks HTTP (ya está)
```

`aiosmtplib` es clave: usa `asyncio` para no bloquear el event loop
mientras envía el email.

## Flujo de Notificación

```
1. CorrelationEngine detecta match
2. Callback → AlertService.crear_alerta()
3. MultiNotifier.send_all(alerta_dict)
4. Por cada notificador registrado:
   ── ¿severidad >= notify_min_severity?
   ├── Sí → enviar notificación
   │    ├── Éxito → log "notificación enviada"
   │    └── Error → log "fallo al enviar: {error}"
   └── No → skip
```

## Archivos a Crear/Modificar

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `backend/app/services/email_notifier.py` | Crear | EmailNotifier con SMTP asíncrono |
| `backend/app/services/webhook_notifier.py` | Crear | WebhookNotifier para Slack/Discord |
| `backend/app/services/notifier.py` | Modificar | Refactor MultiNotifier con filtro por severidad |
| `backend/app/config.py` | Modificar | Config SMTP + webhooks |
| `backend/app/main.py` | Modificar | Registrar nuevos notificadores en lifespan |
| `backend/requirements.txt` | Modificar | Agregar aiosmtplib |
| `backend/tests/test_notifiers.py` | Crear | Tests para cada notificador |
| `docs/fase-07-notificaciones.md` | Crear | Este documento |

## Tests a Implementar

| Test | Qué verifica |
|------|-------------|
| `email_notifier_envia_alerta` | EmailNotifier envía correctamente |
| `email_notifier_filtra_severidad` | No envía si severidad es muy baja |
| `email_notifier_error_manejado` | Error SMTP no crashea la app |
| `webhook_notifier_envia_payload` | POST correcto al webhook |
| `webhook_notifier_formato_slack` | Payload Slack tiene estructura correcta |
| `multi_notifier_filtra_canales` | Cada canal recibe según su configuración |
| `multi_notifier_error_continua` | Un canal falla, los otros siguen |

## Lecciones Anticipadas

### 1. SMTP asíncrono con aiosmtplib

`aiosmtplib` es la versión asíncrona de `smtplib`. La diferencia principal
es que usa `asyncio` para no bloquear:

```python
import aiosmtplib

async def enviar(self, alerta: dict):
    message = EmailMessage()
    message["From"] = self.from_addr
    message["To"] = ", ".join(self.to_addrs)
    message["Subject"] = f"[{alerta['severity'].upper()}] {alerta['title']}"
    message.set_content(formatear_cuerpo(alerta))

    await aiosmtplib.send(
        message,
        hostname=self.smtp_host,
        port=self.smtp_port,
        username=self.smtp_user,
        password=self.smtp_password,
        start_tls=True,
    )
```

### 2. Timeout y retry en notificaciones

Las notificaciones no deben ralentizar el pipeline. Cada notificador
debería tener un timeout (5s por defecto) y manejar fallos sin excepciones:

```python
try:
    await asyncio.wait_for(self._enviar(alerta), timeout=5.0)
except asyncio.TimeoutError:
    logger.error("Timeout al enviar notificación: %s", alerta["id"])
except Exception as e:
    logger.error("Error al enviar notificación: %s", e)
```

### 3. Rate limiting para webhooks

Slack y Discord tienen rate limits (típicamente 1 mensaje por segundo).
Para alertas en ráfaga (ej: 100 eventos en 1 minuto con ventana temporal),
el CorrelationEngine ya agrupa en una sola alerta. Pero si hay múltiples
reglas disparándose, igual pueden llegar varias notificaciones seguidas.

Solución simple: cola asíncrona con mínimo 1 segundo entre mensajes.

### 4. Contraseñas de aplicación para Gmail

Gmail ya no permite contraseñas normales para SMTP. Hay que generar una
"contraseña de aplicación" desde:
`Cuenta de Google → Seguridad → Verificación en dos pasos → Contraseñas de aplicación`

Para otros proveedores:

| Proveedor | Host | Puerto | TLS |
|-----------|------|--------|-----|
| Gmail | smtp.gmail.com | 587 | ✅ |
| Outlook | smtp.office365.com | 587 | ✅ |
| SendGrid | smtp.sendgrid.net | 587 | ✅ |
| Mailtrap (dev) | sandbox.smtp.mailtrap.io | 2525 | ✅ |

### 5. El AsyncTry pattern para no bloquear

En lugar de esperar a que la notificación se envíe (bloqueando el callback
del engine), se puede lanzar una tarea asíncrona independiente:

```python
async def send_all(self, alerta: dict):
    for notificador in self._notificadores:
        asyncio.create_task(notificador.enviar_si_corresponde(alerta))
```

Esto hace que las notificaciones sean fire-and-forget: no ralentizan el
pipeline, y si fallan, solo se loguean.

## Configuración de Desarrollo (Mailtrap)

Para desarrollo sin un servidor SMTP real, [Mailtrap](https://mailtrap.io)
ofrece un sandbox SMTP gratuito:

```env
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=2525
SMTP_USER=tu_usuario_mailtrap
SMTP_PASSWORD=tu_password_mailtrap
NOTIFY_TO=analista@ejemplo.com
NOTIFY_MIN_SEVERITY=low
```

Los emails no se envían realmente — se pueden inspeccionar en el web
dashboard de Mailtrap.

## Próximos Pasos (Fase 08)

- **Configuración productiva** (variables de entorno, volúmenes Docker, healthchecks)
- **Documentación de instalación y configuración**
- **Docker compose con perfiles** (dev vs prod)
