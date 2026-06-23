# SentinelPy — Visión General del Sistema

> **¿Qué es SentinelPy?**
>
> Una plataforma SIEM (Security Information and Event Management) liviana
> diseñada para PyMEs. Recibe logs de seguridad, los normaliza, los evalúa
> contra reglas de detección estilo Sigma, genera alertas, y las muestra
> en un dashboard web — **código abierto, stack moderno Python**.

---

## Tabla de Contenidos

1. [¿Para qué sirve?](#para-qué-sirve)
2. [Arquitectura general](#arquitectura-general)
3. [Recorrido completo: del syslog al dashboard](#recorrido-completo)
4. [Dashboard página por página](#dashboard)
5. [API REST](#api-rest)
6. [Tecnologías](#tecnologías)
7. [Comandos rápidos](#comandos-rápidos)

---

## ¿Para qué sirve?

SentinelPy te permite:

| Problema | Solución SentinelPy |
|----------|---------------------|
| Tenés servidores Linux generando logs de autenticación, firewalls, aplicaciones | Enviá los logs por syslog UDP al puerto 5140 |
| Necesitás detectar ataques (SSH brute force, escaneos de puertos, accesos no autorizados) | Creá reglas de detección con condiciones lógicas |
| Querés centralizar los eventos de seguridad en un solo lugar | Se guardan automáticamente en PostgreSQL |
| Te llegan 10.000 logs por día y no podés revisarlos todos | El motor de correlación solo te muestra lo que importa: las alertas |
| Un analista necesita investigar y resolver alertas | Dashboard web con ciclo de vida: open → investigating → resolved |

**No reemplaza** a Splunk o Sentinel — es para aprendizaje, entornos chicos,
o como base para proyectos más grandes.

---

## Arquitectura general

```
                        ┌─────────────────────────────────────────────┐
                        │               INTERNET / RED                │
                        │   Servidores, firewalls, aplicaciones...    │
                        └──────────────────┬──────────────────────────┘
                                           │ syslog UDP :5140
                                           ▼
              ┌────────────────────────────────────────────────────┐
              │                 PIPELINE                            │
              │                                                     │
              │   Colector UDP  ──►  Parser  ──►  Base de Datos    │
              │   (recibe raw)      (RFC 3164      PostgreSQL      │
              │                       o JSON)                       │
              └─────────────────────┬───────────────────────────────┘
                                    │ evento normalizado
                                    ▼
              ┌────────────────────────────────────────────────────┐
              │          MOTOR DE CORRELACIÓN                      │
              │                                                     │
              │   Evalúa el evento contra TODAS las reglas activas  │
              │   Si una regla matchea → genera una alerta          │
              │                                                     │
              │   Reglas en caché:     ┌─────────────────┐          │
              │   ┌────────────────┐   │ AND              │          │
              │   │ event_type=    │──►│ └─ eq: auth      │          │
              │   │ authentication │   │ └─ eq: root      │          │
              │   │ user_name=root │   └─────────────────┘          │
              │   └────────────────┘                                │
              └──────────────────┬──────────────────────────────────┘
                                 │ alerta generada
                                 ▼
              ┌────────────────────────────────────────────────────┐
              │             BASE DE DATOS                          │
              │                                                     │
              │   ┌──────────┐  ┌──────────┐  ┌──────────┐        │
              │   │ Eventos  │  │  Reglas  │  │ Alertas  │        │
              │   └──────────┘  └──────────┘  └──────────┘        │
              └──────────────────┬──────────────────────────────────┘
                                 │ consultas
                                 ▼
              ┌────────────────────────────────────────────────────┐
              │       API REST (FastAPI) + Dashboard Web           │
              │                                                     │
              │   ┌──────────────────┐  ┌──────────────────┐       │
              │   │  /api/events     │  │  /               │       │
              │   │  /api/rules      │  │  /events         │       │
              │   │  /api/alerts     │  │  /alerts         │       │
              │   │  /api/health     │  │  /rules          │       │
              │   │  /docs (Swagger) │  │  Jinja2+Tailwind │       │
              │   └──────────────────┘  └──────────────────┘       │
              └────────────────────────────────────────────────────┘
```

---

## Recorrido completo

### 1. Un servidor envía un log

```bash
# El servidor Linux genera esto:
<14>Jun 22 10:00:00 server sshd[1234]: Failed password for root from 10.0.0.99 port 22 ssh2
```

Esto viaja por UDP al puerto 5140 de SentinelPy.

### 2. El colector lo recibe

```python
# SyslogCollector escucha en UDP :5140
# Cuando llega un datagrama, lo encola como tarea asíncrona
await pipeline.process(mensaje_raw, addr)
```

### 3. El pipeline detecta el formato y parsea

```python
# SyslogParser.detect() reconoce el formato RFC 3164
# SyslogParser.parse() extrae los campos:
```

| Campo | Valor extraído |
|-------|---------------|
| `event_type` | `authentication` |
| `severity` | `high` (derivado del facility 14) |
| `source_ip` | `10.0.0.99` |
| `user_name` | `root` |
| `description` | `Failed password for root from 10.0.0.99 port 22 ssh2` |

### 4. Se guarda en PostgreSQL

```sql
INSERT INTO events (...) VALUES (...);
-- El evento queda persistido con un UUID único
```

### 5. El motor de correlación evalúa

```python
# CorrelationEngine.evaluate(evento_dict) recorre todas las reglas activas

# Regla "SSH desde IP externa":
#   AND
#   ├── event_type = "authentication"  ✅  (matchea)
#   ├── user_name = "root"             ✅  (matchea)
#   └── source_ip != "192.168.1.1"     ✅  (10.0.0.99 ≠ 192.168.1.1)
#   → REGLA MATCHEA → genera alerta

# Otra regla cualquiera:
#   OR
#   ├── severity = "critical"          ❌  (es high)
#   └── AND (...)
#   → NO MATCHEA → no pasa nada
```

### 6. Se genera una alerta

```python
# El callback del engine crea la alerta en la base de datos
# y la muestra en consola:

{
  "title": "Ataque SSH desde IP externa",
  "severity": "high",
  "description": "Regla 'SSH desde IP externa' activada por evento authentication...",
  "status": "open"
}
```

### 7. Ves la alerta en el dashboard

```
http://localhost:8000/alerts

┌──────────────────────────────────────────────────────────┐
│ Alertas                         94 total                 │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Título           │ Severidad │ Estado │ Acción       │ │
│ │──────────────────────────────────────────────────────│ │
│ │ Ataque SSH       │ HIGH      │ open   │ [Ack ▾] OK │ │
│ │ desde IP externa │           │        │             │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ [+ Nueva regla (API)]  [← Anterior]  [Siguiente →]      │
└──────────────────────────────────────────────────────────┘
```

### 8. El analista investiga

Hace click en el selector → `investigating` → OK.

Cuando termina: `resolved` → OK.

Si era falso positivo: `false_positive` → OK (queda documentado que era esperable).

---

## Dashboard

### `/` — Dashboard principal

```
┌──────────────────────────────────────────────────────────┐
│  SentinelPy                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ EVENTOS HOY  │  │ALERTAS ACTIV │  │REGLAS ACTIVAS│   │
│  │      42      │  │      8       │  │      10      │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                          │
│  Últimos Eventos                              Ver todos →│
│  ┌────────────────────────────────────────────────────┐ │
│  │ 10:00:00 │ authentication │ HIGH │ server │ 10.0.0…│ │
│  │ 09:59:30 │ authentication │ HIGH │ server │ 10.0.0…│ │
│  │ 09:58:15 │ authentication │ INFO │ app    │ 192.168…│ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Cards:**

- **Eventos hoy** — cuántos eventos llegaron desde las 00:00 UTC de hoy
- **Alertas activas** — alertas que todavía no se resolvieron (open + acknowledged + investigating)
- **Reglas activas** — reglas de detección con status = active

**Tabla:** los últimos 10 eventos recibidos, con su severidad coloreada.

---

### `/events` — Eventos

Tabla completa con todos los eventos recibidos. Paginación (20 por página).

**Filtros por severidad:** CRITICAL / HIGH / MEDIUM / LOW / INFO.

Cada fila muestra: timestamp, tipo, severidad (con badge de color), source, IP origen, IP destino, puertos, usuario, descripción.

**¿Para qué usarlo?** Para revisar el volumen de eventos, ver patrones
(¿muchos authentication failures?), o inspeccionar eventos específicos
que no generaron alerta pero parecen sospechosos.

---

### `/alerts` — Alertas

**La página más importante del sistema.** Acá ves lo que el motor de correlación
detectó automáticamente.

**Filtros:**
- Por estado: todas / open / acknowledged / investigating / resolved / false_positive
- Por severidad: CRITICAL / HIGH / MEDIUM / LOW

**Ciclo de vida de una alerta:**

```
open ──► acknowledged ──► investigating ──► resolved
  │                                            │
  └──► false_positive (era esperable)  ◄───────┘
```

Cada fila tiene un formulario para cambiar el estado sin salir de la página.
Seleccionás el nuevo estado y hacés click en OK.

**Columnas:** título (con descripción abreviada), severidad (badge de color),
estado (badge de color), cantidad de eventos relacionados, fecha de creación,
fecha de resolución.

---

### `/rules` — Reglas de detección

Listado de reglas con:

- **Toggle activar/desactivar** — un botón que cambia el status de la regla
  sin tener que ir a la API
- **Badge de estado** — green = active, red = disabled, yellow = test
- **Tags** — hasta 3 visibles, si hay más muestra "+N"
- **Link a Swagger** para crear reglas nuevas (desde `/docs`)

**Regla = la lógica que decide qué eventos generan alertas.**

---

## API REST

Endpoint | Método | Descripción
---------|--------|------------
`/health` | GET | Estado de la app + reglas activas
`/api/events` | GET | Listar eventos (paginación, filtros)
`/api/events` | POST | Crear evento manualmente
`/api/events/estadisticas` | GET | Total eventos, eventos última hora
`/api/rules` | GET | Listar reglas
`/api/rules` | POST | Crear regla
`/api/rules/{id}` | GET | Obtener regla
`/api/rules/{id}` | PUT | Actualizar regla
`/api/rules/{id}` | DELETE | Eliminar regla
`/api/alerts` | GET | Listar alertas
`/api/alerts/{id}` | GET | Obtener alerta
`/api/alerts/{id}/estado` | PATCH | Cambiar estado de alerta
`/api/alerts/estadisticas` | GET | Alertas totales, abiertas, resueltas

**Swagger UI:** http://localhost:8000/docs — documentación interactiva
donde probás cada endpoint con datos reales de la base de datos.

### Ejemplo: crear una regla desde la API

```bash
curl -X POST http://localhost:8000/api/rules \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Puerto sospechoso",
    "description": "Detecta tráfico en puertos altos con UDP",
    "severity": "medium",
    "status": "active",
    "conditions": {
      "operator": "AND",
      "conditions": [
        {"field": "destination_port", "operator": "gt", "value": 1024},
        {"field": "protocol", "operator": "eq", "value": "UDP"}
      ]
    },
    "alert_title": "Tráfico UDP en puerto alto",
    "alert_severity": "medium"
  }'
```

### Ejemplo: enviar un evento manualmente

```bash
curl -X POST http://localhost:8000/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "firewall",
    "severity": "high",
    "source": "test",
    "source_ip": "10.0.0.99",
    "description": "Paquete sospechoso detectado"
  }'
```

(Esto también pasa por el motor de correlación — si matchea una regla,
genera alerta.)

---

## Tecnologías

| Componente | Tecnología | Por qué |
|------------|-----------|---------|
| Lenguaje | Python 3.12+ | Tipado fuerte, async/await nativo, ecosistema de seguridad |
| Framework web | FastAPI | Rendimiento, validación automática, Swagger integrado |
| Base de datos | PostgreSQL 16 + asyncpg | SQL que soporta JSON, buena para logs |
| ORM | SQLAlchemy 2.0 asyncio | Tipos, migrations con Alembic |
| Templates | Jinja2 + Tailwind (CDN) | Server-side rendering, sin build step |
| Colector | asyncio.DatagramProtocol | Async UDP nativo, sin dependencias |
| Docker | docker compose | PostgreSQL + API, un solo comando |
| Tests | pytest + pytest-asyncio | 47 tests, modo Strict |

---

## Comandos rápidos

```bash
# Levantar todo
docker compose up -d

# Ver logs
docker compose logs api --tail=50

# Reiniciar API
docker compose restart api

# Reconstruir imagen (si cambió requirements.txt)
docker compose up -d --build api

# Enviar syslog de prueba (PowerShell)
$udp = New-Object System.Net.Sockets.UdpClient('127.0.0.1',5140)
$bytes = [Text.Encoding]::UTF8.GetBytes("<14>Jun 22 10:00:00 server sshd[1234]: Failed password for root from 10.0.0.99 port 22 ssh2")
$udp.Send($bytes,$bytes.Length); $udp.Close()

# Ver reglas activas
curl http://localhost:8000/health

# Abrir dashboard
# http://localhost:8000/
```

---

## Resumen visual del flujo

```
Servidor ──UDP:5140──► Colector ──► Parser ──► DB ──► Engine ──► Alerta ──► Dashboard
                          │                      ▲                              │
                          │                      │                              │
                          └── pipeline.process() ─┘                              │
                                                                                  │
                                                                                  ▼
                                                                              Analista
                                                                              (investiga
                                                                               y resuelve)
```

1. **Sender** — cualquier dispositivo que mande logs por UDP
2. **SentinelPy** — recibe, parsea, guarda, evalúa, alerta
3. **Analista** — mira el dashboard, investiga alertas, cambia estados

---

## ¿Qué sigue?

El proyecto está en crecimiento. Las próximas fases prevén:

- **Correlación temporal** — alertar solo si ocurre N veces en X minutos
- **Gráficas** — timeline de eventos/alertas
- **Exportación** — PDF/CSV de alertas
- **React/TypeScript** — frontend moderno (Nivel 2)
- **Autenticación** — login de analistas
- **Notificaciones** — email, Slack, webhook

---

*Documento generado para entender el sistema completo sin leer código.*
*SentinelPy — Plataforma Inteligente de Monitoreo y Detección de Incidentes para PyMEs.*
