# Fase 05: Correlación Temporal, Gráficas y Exportación

## Objetivo

Agregar tres capacidades clave que transforman SentinelPy de un prototipo
funcional a una herramienta de monitoreo seria:

1. **Correlación temporal**: agrupar múltiples eventos en una ventana de
   tiempo dentro de una sola alerta (evita inundar de alertas repetidas)
2. **Gráficas en el dashboard**: visualizar eventos y alertas con Chart.js
3. **Exportación a CSV**: descargar alertas para análisis externo

## Arquitectura

```
                    ┌─────────────────────────────────────┐
                    │         CorrelationEngine            │
                    │                                     │
                    │  ┌─────────────────────────────┐    │
                    │  │       _ventanas: dict       │    │
                    │  │  rule_id → {               │    │
                    │  │    event_count,             │    │
                    │  │    first_event_at,          │    │
                    │  │    last_event_at,           │    │
                    │  │    expires_at               │    │
                    │  │  }                          │    │
                    │  └─────────────────────────────┘    │
                    │                                     │
                    │  Match → ¿tiene correlation_window? │
                    │    ├── No → callback crear alerta   │
                    │    └── Sí → ¿ventana activa?       │
                    │         ├── No/Sí expirada          │
                    │         │   → callback crear alerta │
                    │         │   → registrar ventana     │
                    │         └── Sí, dentro de ventana   │
                    │             → callback actualizar   │
                    │             → event_count++         │
                    └─────────┬───────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
    callback crear                    callback actualizar
    → AlertService.crear_alerta()    → AlertService.actualizar_contadores()
                              │
                              ▼
                    ┌──────────────────────┐
                    │   Dashboard Web      │
                    │   ┌───────────────┐  │
                    │   │ Chart.js      │  │
                    │   │ → timeline    │  │
                    │   │ → severidad   │  │
                    │   └───────────────┘  │
                    │   ┌───────────────┐  │
                    │   │ CSV export    │  │
                    │   │ ↓ alertas.csv │  │
                    │   └───────────────┘  │
                    └──────────────────────┘
```

## Componentes Modificados

### 1. CorrelationEngine — Ventanas Temporales

El engine ahora mantiene `_ventanas: dict[str, dict]`, un diccionario
en memoria que asocia cada `rule_id` con el estado de su ventana:

```python
self._ventanas[rule_id] = {
    "event_count": 1,
    "first_event_at": timestamp,
    "last_event_at": timestamp,
    "expires_at": ahora + timedelta(seconds=correlation_window),
}
```

**Flujo de evaluación** (`_manejar_match`):

1. La regla matchea → se verifica si tiene `correlation_window`
2. **Sin ventana** → alerta inmediata (comportamiento original)
3. **Con ventana, sin ventana activa** → crea alerta y registra ventana
4. **Con ventana activa** → incrementa `event_count`, actualiza
   `last_event_at`, llama a los callbacks de actualización (no crea alerta)
5. **Ventana expirada** → se crea una nueva alerta con contador
   reiniciado (la anterior queda con su conteo final en la BD)

**Callbacks duales:**

| Callback | Cuándo se ejecuta | Qué recibe |
|----------|------------------|------------|
| `registrar_callback` | Al crear una alerta | `datos_alerta` completos |
| `registrar_callback_actualizar` | Al actualizar dentro de ventana | `rule_id`, `event_count`, `last_event_at` |

**Limpieza automática:** al recargar reglas (`cargar_reglas()`), las
ventanas se limpian para evitar inconsistencias con reglas modificadas.

### 2. AlertService — actualizar_contadores()

Nuevo método que actualiza `event_count` y `last_event_at` en la alerta
abierta más reciente de una regla:

```python
async def actualizar_contadores(self, rule_id, event_count, last_event_at):
    alerta = await self.session.execute(
        select(Alert).where(
            Alert.rule_id == UUID(rule_id),
            Alert.status == "open",
        ).order_by(Alert.created_at.desc()).limit(1)
    )
    alerta.event_count = event_count
    alerta.last_event_at = last_event_at
```

Busca la alerta `open` más reciente para esa regla — así múltiples
eventos dentro de la ventana actualizan una sola alerta.

### 3. Gráficas con Chart.js

**CDN sin build step:**

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
```

**Endpoints de datos:**

| Endpoint | Retorna | Uso |
|----------|---------|-----|
| `GET /api/events/stats?horas=24` | `{timeline, por_severidad}` | Timeline de eventos por hora |
| `GET /api/alerts/stats` | `{por_severidad, por_estado}` | Distribución de alertas |

**Dashboard con dos gráficas:**

- **Timeline**: línea de eventos por hora en las últimas 24h
  - Datos agrupados con `date_trunc('hour', event_timestamp)`
  - Fetch client-side desde `/api/events/stats`
  - Chart.js `type: 'line'` con relleno degradado

- **Distribución por severidad**: dona con colores semánticos
  - critical → rojo, high → naranja, medium → amarillo, low → azul, info → gris
  - Chart.js `type: 'doughnut'`

> **Nota:** Los datos se cargan via `fetch()` desde el frontend, no
> server-side rendering, para mantener el dashboard reactivo sin recargar.

### 4. Exportación CSV

**Endpoint:** `GET /api/alerts/exportar?estado=&severidad=`

- Acepta los mismos filtros que la web (`estado`, `severidad`)
- Usa `csv.writer` de la stdlib con `StringIO`
- Devuelve `StreamingResponse` con `Content-Type: text/csv`
- Header `Content-Disposition: attachment; filename=alertas.csv`

**Botón en alerts.html:**

```html
<a href="/api/alerts/exportar?estado=open&severidad=critical">↓ CSV</a>
```

El link preserva los filtros actuales: si estás viendo alertas `open`
con severidad `critical`, la exportación descarga exactamente esas.

## Archivos Modificados/Creados

| Archivo | Cambio |
|---------|--------|
| `app/services/engine.py` | Ventanas temporales, `_manejar_match()`, `registrar_callback_actualizar()`, `ventanas_activas` |
| `app/services/alert_service.py` | Nuevo método `actualizar_contadores()` |
| `app/main.py` | Update callback, endpoints `/api/events/stats`, `/api/alerts/stats`, `/api/alerts/exportar` |
| `app/templates/base.html` | Chart.js CDN, `{% block scripts %}` |
| `app/templates/index.html` | 4 cards (nueva: ventanas activas), contenedores Chart.js, JS de gráficas |
| `app/templates/alerts.html` | Botón "↓ CSV" con filtros preservados |
| `tests/test_engine.py` | 9 tests de correlación temporal (42 total) |
| `docs/fase-05-correlacion-temporal-graficas.md` | Este documento |

## Tests Nuevos (9 tests de correlación temporal)

| Test | Qué verifica |
|------|-------------|
| `test_primer_evento_crea_alerta` | El primer match con ventana crea alerta |
| `test_segundo_evento_no_crea_alerta` | Segundo match en ventana NO crea nueva alerta |
| `test_update_callback_ejecutado` | El callback de actualización se ejecuta |
| `test_event_count_se_acumula` | event_count se incrementa en cada match |
| `test_regla_sin_ventana_siempre_crea_alerta` | Sin ventana: cada match es alerta nueva |
| `test_ventanas_activas_property` | Propiedad `ventanas_activas` funciona |
| `test_recarga_limpia_ventanas` | `cargar_reglas()` limpia ventanas |
| `test_ventana_expirada_crea_nueva_alerta` | Ventana expirada → nueva alerta |
| `test_regla_sin_id_no_ventana` | Regla sin ID no usa ventana (edge case) |

## Lecciones Aprendidas

### 1. Estado en memoria vs en BD

Las ventanas temporales viven en memoria dentro del engine. Esto es
intencional: la correlación temporal necesita ser rápida (no consultar
BD por cada evento). Pero tiene implicaciones:

- **Si la app se reinicia**, las ventanas se pierden (los contadores
  se reinician). Las alertas ya creadas siguen en BD.
- **En un cluster multi-instancia**, cada instancia tiene sus propias
  ventanas. Para producción habría que usar Redis o similar.

### 2. Callbacks duales vs un solo callback con acción

Inicialmente pensé en un solo callback que recibiera una `action`
("create" o "update"). Pero separar en dos listas de callbacks es más
limpio porque:

- Los callbacks de creación y actualización tienen firmas diferentes
  (actualización recibe menos campos)
- Se puede registrar solo un tipo sin tener que switchear por acción
- El engine no necesita saber qué callback es para qué — solo llama
  al que corresponde

### 3. date_trunc en SQLAlchemy async

Para agrupar eventos por hora, usé `func.date_trunc()` de PostgreSQL:

```python
select(
    func.date_trunc("hour", NormalizedEvent.event_timestamp).label("hora"),
    func.count(NormalizedEvent.id).label("total"),
).group_by("hora").order_by("hora")
```

Esto funciona con asyncpg + SQLAlchemy async sin problemas. El resultado
se serializa como `datetime` que convierto a ISO string con `.isoformat()`.

### 4. StreamingResponse con StringIO

Para CSV usé `io.StringIO` + `csv.writer` + `StreamingResponse`:

```python
output = io.StringIO()
writer = csv.writer(output)
writer.writerow(["id", "titulo", ...])
for a in alertas:
    writer.writerow([...])
output.seek(0)
return StreamingResponse(
    iter([output.getvalue()]),
    media_type="text/csv",
    headers={"Content-Disposition": "attachment; filename=alertas.csv"},
)
```

La clave: `StringIO` produce un string en memoria, `StreamingResponse`
lo envuelve como respuesta descargable. Para archivos más grandes se
usaría un iterador, pero para alertas (miles, no millones) está bien.

### 5. Chart.js con fetch para datos dinámicos

Las gráficas se cargan con JS asíncrono (`async IIFE`) que fetchea
los datos de `/api/events/stats` y renderiza los charts. Esto mantiene
el dashboard server-side pero permite que las gráficas sean reactivas.

El patrón:

```html
<canvas id="chart-timeline"></canvas>
<script>
(async function() {
    const res = await fetch('/api/events/stats?horas=24');
    const data = await res.json();
    new Chart(document.getElementById('chart-timeline'), { ... });
})();
</script>
```

## Próximos Pasos (Fase 06)

- **Autenticación de analistas** (login, roles, sesiones)
- **Notificaciones por email** (SMTP para alertas críticas)
- **Tests de integración** con base de datos real
- Refactor frontend a React/TypeScript (N2)
