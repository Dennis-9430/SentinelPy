# Fase 03: Motor de Correlación y Alertas

## Objetivo

Implementar el corazón de SentinelPy: un motor de correlación que evalúa
cada evento entrante contra reglas de detección estilo Sigma y genera
alertas de seguridad automáticamente.

## Arquitectura

```
                    ┌──────────────────────┐
                    │   Pipeline existente  │
                    │  (colector → parser   │
                    │   → guardar en DB)    │
                    └──────────┬───────────┘
                               │ evento normalizado
                               ▼
                    ┌──────────────────────┐
                    │  CorrelationEngine   │
                    │  (caché en memoria)   │
                    │                      │
                    │  ┌──────┐ ┌──────┐   │
                    │  │Regla1│ │Regla2│…  │
                    │  └──┬───┘ └──┬───┘   │
                    │     │        │       │
                    │     ▼        ▼       │
                    │  ┌────────────────┐  │
                    │  │ ¿Matchea?      │  │
                    │  │ → genera alerta│  │
                    │  └──────┬─────────┘  │
                    └─────────┼────────────┘
                              │ callback
                              ▼
                    ┌──────────────────────┐
                    │  AlertService        │
                    │  → guarda en DB      │
                    │  → MultiNotifier     │
                    └──────────────────────┘
```

## Componentes Nuevos

### 1. DetectionRule (modelo SQLAlchemy)

Representa una regla de detección estilo Sigma con campos como:
- `title`, `description`, `author` — metadatos
- `severity` — severidad de la regla (info, low, medium, high, critical)
- `status` — active, disabled, test
- `conditions` — JSON con la estructura de condiciones
- `alert_title`, `alert_severity` — datos de la alerta generada
- `correlation_window` — ventana de tiempo en segundos (para futura correlación temporal)
- `tags`, `references`, `false_positives` — metadatos de clasificación

### 2. Alert (modelo SQLAlchemy)

Representa una alerta de seguridad generada por el motor:
- `rule_id` — FK a la regla que la disparó
- `title`, `severity`, `description` — datos de la alerta
- `status` — ciclo de vida: open → acknowledged → investigating → resolved | false_positive
- `event_count` — cantidad de eventos relacionados
- `first_event_at`, `last_event_at` — ventana temporal
- `resolution_notes` — notas del analista

### 3. RuleService

CRUD completo de reglas más método `cargar_reglas_activas()` que filtra
solo reglas con `status='active'` para cargar en el motor.

### 4. AlertService

CRUD de alertas con:
- `listar_alertas()` — paginación + filtros por estado/severidad
- `actualizar_estado()` — ciclo de vida de la alerta
- `obtener_estadisticas()` — conteos para el dashboard

### 5. CorrelationEngine

El corazón del sistema. Mantiene un caché de reglas activas en memoria
y evalúa cada evento contra todas ellas.

**Operadores soportados:**

| Operador | Descripción |
|----------|-------------|
| `eq` | Igualdad (case-insensitive para strings) |
| `neq` / `not` | No igual |
| `contains` | Substring case-insensitive |
| `gt`, `gte`, `lt`, `lte` | Comparaciones numéricas |
| `in` | Valor en lista (acepta string como lista de 1) |
| `regex` | Expresión regular |
| `exists` | El campo existe y no es None |
| `not_exists` | El campo es None o no existe |
| `startswith` | Empieza con el valor |
| `endswith` | Termina con el valor |

**Grupos lógicos:**

- **AND**: todas las sub-condiciones deben cumplirse
- **OR**: al menos una sub-condición debe cumplirse
- **NOT**: la sub-condición NO debe cumplirse (a nivel grupo)

Los operadores se normalizan a minúsculas internamente, tolerando
`AND`, `and`, `OR`, `or`, etc.

**Callbacks:** el engine soporta múltiples callbacks registrados
que se ejecutan cuando se genera una alerta. Esto permite separar
la persistencia (guardar en DB) de la notificación (consola, email,
Slack, etc.).

### 6. Pipeline extendido

El pipeline existente ahora acepta un `engine` opcional. Después de
guardar un evento en la base de datos, lo envía al motor para
evaluación:

```python
class Pipeline:
    def __init__(self, engine=None):
        self.syslog_parser = SyslogParser()
        self.json_parser = JSONParser()
        self.engine = engine
```

### 7. Notificadores

- `ConsoleNotifier` — escribe alertas a la consola con formato JSON
- `MultiNotifier` — permite combinar múltiples notificadores

## Estructura de Condiciones (JSON)

Una regla puede tener condiciones simples o grupos:

```json
{
  "operator": "AND",
  "conditions": [
    {"field": "event_type", "operator": "eq", "value": "authentication"},
    {"field": "user_name", "operator": "eq", "value": "root"}
  ]
}
```

Grupos anidados con OR:

```json
{
  "operator": "OR",
  "conditions": [
    {
      "operator": "AND",
      "conditions": [
        {"field": "severity", "operator": "eq", "value": "critical"},
        {"field": "event_type", "operator": "eq", "value": "authentication"}
      ]
    },
    {
      "operator": "AND",
      "conditions": [
        {"field": "severity", "operator": "eq", "value": "high"},
        {"field": "source_ip", "operator": "in", "value": ["10.0.0.1", "192.168.1.1"]}
      ]
    }
  ]
}
```

## Ciclo de Vida en la App

En `main.py`, el `lifespan` ahora:

1. Conecta la base de datos y crea tablas
2. Carga reglas activas en el motor de correlación
3. Registra el callback que crea alertas en DB y notifica
4. Configura notificadores (ConsoleNotifier)
5. Inicia colector syslog
6. En yield: la app corre
7. Al cerrar: detiene colectores gracefulmente

Cuando se crea/actualiza/elimina una regla vía API, se intenta
recargar el engine automáticamente para mantener el caché sincronizado
sin reiniciar la app.

## Endpoints Nuevos

### Reglas (`/api/rules`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/rules` | Listar reglas (paginación, filtros) |
| GET | `/api/rules/{id}` | Obtener regla |
| POST | `/api/rules` | Crear regla |
| PUT | `/api/rules/{id}` | Actualizar regla |
| DELETE | `/api/rules/{id}` | Eliminar regla |

### Alertas (`/api/alerts`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/alerts` | Listar alertas (paginación, filtros) |
| GET | `/api/alerts/{id}` | Obtener alerta |
| PATCH | `/api/alerts/{id}/estado` | Actualizar estado (ciclo de vida) |
| GET | `/api/alerts/estadisticas` | Estadísticas (totales, abiertas, resueltas) |

## Tests

33 tests unitarios para el motor de correlación que cubren:

- **Evaluación de condiciones** (13 tests): eq, neq, not, contains, gt, lt,
  in, regex, campo ausente, valores no numéricos
- **Evaluación de grupos** (8 tests): AND, OR, AND+OR anidados, NOT
- **Flujo completo** (9 tests): evaluate(), callbacks, reglas múltiples,
  reglas inactivas, recarga de caché
- **Casos borde** (3 tests): exists, gt con strings, in con string

Los tests usan pytest-asyncio con el modo Strict y no requieren
base de datos — el engine trabaja completamente en memoria.

## Lecciones Aprendidas

1. **Dict vs Objeto**: el engine recibe reglas como `DetectionRule` (SQLAlchemy)
   desde producción, pero como dicts desde tests. Agregar `_campo_regla()` como
   helper que soporta ambos con `getattr`/`get` evita acoplar el motor al ORM.

2. **Normalización de operadores**: los fixtures usaban `"AND"` (mayúsculas)
   pero el engine buscaba `"and"` (minúsculas). Normalizar con `.lower()` en
   todos los puntos de entrada evita bugs sutiles.

3. **Callbacks como lista vs singleton**: empezar con un solo callback es
   tentador, pero usar una lista desde el principio permite composición
   (persistencia + notificación + logging) sin refactor.

4. **Reglas inactivas**: el engine filtra `status='active'` en `cargar_reglas()`
   por seguridad defensiva, incluso si el caller ya filtró. Doble validación.

5. **_in_list con strings**: el operador `in` originalmente exigía una lista
   como value. Aceptar un string y envolverlo en `[value]` hace la API más
   tolerante para reglas con un solo valor.

## Próximos Pasos (Fase 04)

- Correlación temporal (ventana de tiempo en reglas)
- Dashboard web con métricas en vivo
- Exportación de alertas
- Notificaciones por email
