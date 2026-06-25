# Fase 07: Notificaciones por Email y Webhook

## Objetivo

Agregar notificaciones automáticas multicanal cuando se generen alertas
de seguridad. Un SIEM que no notifica no sirve para producción — nadie
va a estar mirando el dashboard 24/7. Con notificaciones por email y
webhook, los analistas reciben las alertas en su canal de comunicación
habitual (correo, Slack, Discord, etc.).

## Arquitectura

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
                    │   MultiNotifier       │
                    │   (filtro severidad)  │
                    │                      │
                    │  ┌──────────────┐    │
                    │  │ ConsoleNotif │    │
                    │  │ → logging    │    │
                    │  └──────────────┘    │
                    │  ┌──────────────┐    │
                    │  │ EmailNotifier│    │
                    │  │ → aiosmtplib │    │
                    │  └──────────────┘    │
                    │  ┌──────────────┐    │
                    │  │WebhookNotif  │    │
                    │  │ → httpx POST │    │
                    │  └──────────────┘    │
                    └──────────────────────┘
```

## Componentes

### 1. MultiNotifier — Refactor a Async + Filtro por Severidad

El `MultiNotifier` existente se refactorizó para soportar:

- **Async**: `send_all()` ahora es `async def` y `await` cada notificador
- **Filtro por severidad**: cada notificador registrado tiene su propio
  `min_severity`. Antes de enviar, se compara la severidad de la alerta
  contra el umbral usando un orden numérico.

**Orden de severidad:**

```python
_SEVERITY_ORDER = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}
```

**Registro con severidad:**

```python
multi_notifier.agregar(ConsoleNotifier())
multi_notifier.agregar(EmailNotifier(), min_severity="high")
multi_notifier.agregar(WebhookNotifier(), min_severity="high")
```

**SendAll con tolerancia a fallos:**

```python
async def send_all(self, alerta: dict):
    for notificador, min_severidad in self._notificadores:
        if _SEVERITY_ORDER.get(alerta.get("severity", "info"), 0) < _SEVERITY_ORDER.get(min_severidad, 0):
            continue
        try:
            await notificador.send(alerta)
        except Exception as e:
            logger.error("Error en notificador %s: %s", type(notificador).__name__, e)
```

Un notificador que falla nunca detiene a los demás.

### 2. ConsoleNotifier — Adaptado a Async

El `ConsoleNotifier` existente solo cambió `def send()` → `async def send()`.
La lógica interna sigue igual: loguea la alerta con diferentes niveles
(warning para critical/high, info para el resto).

### 3. EmailNotifier

Envío de alertas por email usando `aiosmtplib` (SMTP asíncrono).

**Inicialización:**

```python
class EmailNotifier:
    def __init__(self):
        self.host = settings.smtp_host          # smtp.gmail.com
        self.port = settings.smtp_port           # 587
        self.user = settings.smtp_user           # correo@gmail.com
        self.password = settings.smtp_password    # contraseña de aplicación
        self.from_addr = settings.smtp_from
        self.to_addrs = settings.notify_to        # ["analista@ejemplo.com"]
```

**Método send() con skip silencioso:**

```python
async def send(self, alerta: dict):
    if not self.user or not self.to_addrs:
        return  # SMTP no configurado — skip silencioso

    msg = EmailMessage()
    msg["From"] = self.from_addr or self.user
    msg["To"] = ", ".join(self.to_addrs)
    msg["Subject"] = f"[{severity}] SentinelPy — {title}"
    msg.set_content(self._formatear_cuerpo(alerta))

    await aiosmtplib.send(
        msg,
        hostname=self.host,
        port=self.port,
        username=self.user,
        password=self.password,
        start_tls=True,
        timeout=10.0,
    )
```

**Formato del email (texto plano):**

```
[CRITICAL] Posible fuerza bruta SSH detectada
============================================================

  Regla:      550e8400-e29b-41d4-a716-446655440000
  Severidad:  critical
  Eventos:    15
  ID Alerta:  660e8400-e29b-41d4-a716-446655440000

  Descripción:
    Múltiples intentos de autenticación como root
    desde 10.0.0.1 en los últimos 60 segundos.

  — SentinelPy
```

### 4. WebhookNotifier

Envío de alertas a webhooks HTTP via `httpx.AsyncClient`. Detecta
automáticamente el formato según la URL:

| URL contiene | Formato |
|-------------|---------|
| `discord` | Discord Embeds |
| cualquier otra | Slack Attachments |

**Inicialización:**

```python
class WebhookNotifier:
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or settings.webhook_url
        self._client = httpx.AsyncClient(timeout=5.0)
```

**Payload Slack:**

```json
{
    "attachments": [{
        "color": "#dc2626",
        "title": "🚨 [CRITICAL] Posible fuerza bruta SSH",
        "text": "Múltiples intentos de autenticación...",
        "fields": [
            {"title": "ID", "value": "550e8400", "short": true},
            {"title": "Eventos", "value": "15", "short": true}
        ],
        "footer": "SentinelPy"
    }]
}
```

**Payload Discord:**

```json
{
    "embeds": [{
        "color": 14431526,
        "title": "[CRITICAL] Posible fuerza bruta SSH",
        "description": "Múltiples intentos de autenticación...",
        "fields": [
            {"name": "ID", "value": "550e8400", "inline": true},
            {"name": "Eventos", "value": "15", "inline": true}
        ],
        "footer": {"text": "SentinelPy"}
    }]
}
```

**Mapa de colores por severidad:**

| Severidad | Slack (hex) | Discord (int) |
|-----------|-------------|---------------|
| critical | `#dc2626` | `0xdc2626` |
| high | `#ea580c` | `0xea580c` |
| medium | `#ca8a04` | `0xca8a04` |
| low | `#2563eb` | `0x2563eb` |
| info | `#6b7280` | `0x6b7280` |

## Flujo Completo

```
1. CorrelationEngine detecta match → llama a callback
2. CrearAlertaDesdeEngine():
   a. Persiste alerta en BD
   b. MultiNotifier.send_all(alerta_dict)  ← AHORA ASYNC
3. Por cada notificador registrado:
   ── ¿severidad de alerta >= min_severity del notificador?
   ├── No → skip (log debug)
   └── Sí → await notificador.send(alerta)
        ├── Éxito → log "Notificación enviada: {title} → {canal}"
        └── Error → log "Error en {notificador}: {error}"
                     (los demás notificadores siguen)
```

## Configuración

### Config (config.py)

```python
# ── Notificaciones Email ────────────────────────────────────────────
smtp_host: str = ""
smtp_port: int = 587
smtp_user: str = ""
smtp_password: str = ""
smtp_from: str = ""
notify_to: list[str] = []

# ── Notificaciones Webhook ──────────────────────────────────────────
webhook_url: str = ""
notify_min_severity: str = "high"  # critical | high | medium | low
```

### .env

```env
# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alertas@tuempresa.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
NOTIFY_TO=analista@ejemplo.com

# Webhook
WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/xxxxx
NOTIFY_MIN_SEVERITY=high
```

## Archivos Creados/Modificados

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `app/services/email_notifier.py` | Creado | EmailNotifier con aiosmtplib (SMTP asíncrono) |
| `app/services/webhook_notifier.py` | Creado | WebhookNotifier con httpx (Slack/Discord) |
| `app/services/notifier.py` | Modificado | ConsoleNotifier → async. MultiNotifier con filtro severidad |
| `app/config.py` | Modificado | 7 campos nuevos: smtp_*, notify_to, webhook_url, notify_min_severity |
| `app/main.py` | Modificado | callback ahora await send_all(), lifespan registra notifiers condicionales |
| `requirements.txt` | Modificado | aiosmtplib>=3.0.0 |
| `tests/test_notifiers.py` | Creado | 7 tests con mocks |
| `.env.example` | Modificado | Variables SMTP y webhook comentadas |

## Tests (7 tests)

| Test | Tipo | Qué verifica |
|------|------|-------------|
| `test_console_notifier_logs_alerta` | Unitario | ConsoleNotifier loguea sin errores |
| `test_multi_notifier_ejecuta_todos` | Unitario | MultiNotifier ejecuta todos los registrados |
| `test_multi_notifier_filtra_severidad` | Unitario | No envía si severidad < min_severity |
| `test_multi_notifier_error_no_detiene` | Unitario | Un fallo no detiene a los otros |
| `test_email_notifier_skips_sin_config` | Unitario | Skip silencioso si SMTP no configurado |
| `test_webhook_notifier_skips_sin_url` | Unitario | Skip silencioso si URL vacía |
| `test_console_severity_filtering` | Unitario | Todas las severidades se manejan sin error |

## Lecciones Aprendidas

### 1. Hacer todo async fue el cambio más simple

El `ConsoleNotifier` original era sincrónico. Para que `MultiNotifier`
pudiera `await` notificadores async (email, webhook), había dos opciones:

- **Mantener sync + run_in_executor**: más complejo, introducía threads
- **Convertir todo a async**: solo cambiar `def` → `async def` en ConsoleNotifier

La segunda opción fue trivial. Como el engine ya `await`ea los callbacks,
el cambio fue natural y no rompió nada.

### 2. Filtro por severidad con orden numérico

```python
_SEVERITY_ORDER = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
```

Cada notificador registra su `min_severity`. En `send_all`, se compara
el orden de la severidad de la alerta contra el umbral. Esto permitió
que cada canal tenga su propia configuración: consola recibe todo,
email solo critical+high.

### 3. Detección Slack vs Discord por URL

En lugar de requerir una configuración explícita del tipo de webhook,
el `WebhookNotifier` detecta automáticamente el formato buscando
`"discord"` en la URL. Esto hace la configuración más simple: el usuario
solo pega la URL y el sistema elige el formato correcto.

### 4. Skip silencioso sin configuración

Si `smtp_user` está vacío, `EmailNotifier.send()` hace `return`
inmediatamente sin loguear error. Esto es intencional: el usuario
recién instaló SentinelPy y todavía no configuró SMTP. No debería ver
warnings por algo que no configuró. Los logs solo aparecen cuando hay
configuración pero falla el envío.

### 5. aiosmtplib vs smtplib

`aiosmtplib` tiene exactamente la misma API que `smtplib` pero async.
El cambio es mínimo:

```python
# Sync
smtplib.send(msg, hostname=..., port=...)

# Async
await aiosmtplib.send(msg, hostname=..., port=...)
```

Incluye soporte nativo para STARTTLS, autenticación, y timeout, lo que
evita tener que manejar conexiones manualmente.

## Configuración de Desarrollo

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

## Próximos Pasos

- **Sistema de permisos por rol** (admin puede todo, analyst solo lectura)
- **API Key** para integraciones externas sin cookie
- **NotificationLog** en BD para auditoría de notificaciones enviadas
- **Cola asíncrona** para rate limiting en webhooks
