# Fase 02: Colectores y Parsing de Logs

## Objetivo

Implementar la ingesta de logs: recibir mensajes syslog por UDP, parsearlos
a un formato normalizado, y almacenarlos en PostgreSQL.

## Arquitectura del Pipeline

```
Syslog UDP :5140
      │
      ▼
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  Colector   │────▶│   Parser     │────▶│  Base de Datos │
│ (UDP Server)│     │ RFC 3164/JSON│     │   PostgreSQL   │
└─────────────┘     └──────────────┘     └────────────────┘
```

## Componentes Nuevos

### 1. SyslogCollector

Usa `asyncio.DatagramProtocol` para crear un servidor UDP asíncrono.
Escucha en `0.0.0.0:5140` y cada datagrama recibido se envía al pipeline
como una tarea asíncrona para no bloquear el event loop.

```python
class SyslogUDPHandler(asyncio.DatagramProtocol):
    def datagram_received(self, data, addr):
        asyncio.create_task(self.pipeline.process(raw, addr))
```

### 2. SyslogParser (RFC 3164)

Parsea el formato BSD syslog tradicional:

```
<PRI>Timestamp Hostname App[PID]: Mensaje
```

**Ejemplo real:**
```
<30>Oct  9 22:33:20 myhost sshd[12345]: Failed password for root from 192.168.1.100
```

**Campos extraídos:**
- **Priority** (30): se divide en facility(3) y severity(6)
- **Facility**: auth(4), daemon(3), kern(0), etc.
- **Severity**: mapeada a nuestro modelo (0→critical, 6→info, 7→info)
- **Hostname**: myhost
- **App**: sshd
- **PID**: 12345
- **Mensaje**: "Failed password for root from 192.168.1.100"

### 3. JSONParser

Para logs modernos que ya vienen estructurados (Docker, apps, cloud).
Detecta automáticamente campos por nombre y soporta múltiples variantes:

| Campo Normalizado | Nombres que acepta |
|------------------|-------------------|
| source | source, host, hostname, origin |
| event_type | event_type, type, event, log_type |
| severity | severity, level, log_level, priority |
| description | description, message, msg, log, text |
| source_ip | source_ip, src_ip, source, src |
| destination_ip | destination_ip, dest_ip, dest, dst |

### 4. Pipeline

Orquesta el flujo: recibe logs crudos, detecta el formato (JSON vs syslog),
parsea, y guarda en la base de datos.

### 5. EventService

Capa de servicio para operaciones CRUD sobre eventos:
- `crear_evento()` — persiste un evento normalizado
- `listar_eventos()` — consulta con paginación y filtros
- `obtener_estadisticas()` — métricas para el dashboard

## Endpoints Nuevos

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/events` | Lista eventos con paginación y filtros |
| `POST` | `/api/events` | Ingesta un evento vía API REST |
| `GET` | `/api/events/estadisticas` | Estadísticas de eventos |

## Lo que Aprendí

### asyncio.DatagramProtocol
- asyncio tiene soporte nativo para UDP con `create_datagram_endpoint()`
- El protocolo recibe datagramas en `datagram_received()` que se llama por cada paquete
- Es importante crear una tarea asíncrona (`asyncio.create_task`) para no bloquear el event loop durante el procesamiento

### Expresiones Regulares para Syslog
- RFC 3164 tiene un formato fijo pero con variaciones (PID opcional, mensaje variable)
- Se puede expresar completo en una sola regex con grupos nombrados
- La fecha no tiene año (se asume el actual) — una limitación conocida del formato

### Mapeo de Severidad
- Los niveles de syslog (0-7) no mapean 1:1 a severidades modernas
- Emergency/Alert/Critical → critical, Error → high, Warning → medium, etc.

### Pipeline Pattern
- Separar detección de formato del parsing mantiene el código limpio
- El pipeline actúa como "middleware" que puede crecer (agregar logging, métricas, etc.)

## Próximos Pasos (Fase 03)

- Implementar el motor de correlación (evaluar eventos contra reglas)
- CRUD completo de reglas de detección
- Generación de alertas automáticas
- Notificaciones en consola
