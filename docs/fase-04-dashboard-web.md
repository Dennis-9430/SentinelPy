# Fase 04: Dashboard Web con Jinja2 y Tailwind

## Objetivo

Construir un dashboard web server-side rendering (SSR) con Jinja2 y Tailwind
CSS para visualizar eventos, alertas y reglas de detección en tiempo real,
sin necesidad de un frontend JavaScript pesado.

## Arquitectura

```
                     ┌──────────────────────────────────────┐
                     │            FastAPI App                │
                     │                                      │
                     │  ┌────────────────────────────────┐  │
                     │  │      Rutas HTML (SSR)           │  │
                     │  │  GET / → dashboard              │  │
                     │  │  GET /events → lista eventos    │  │
                     │  │  GET /alerts → lista alertas    │  │
                     │  │  GET /rules → lista reglas      │  │
                     │  └──────────┬─────────────────────┘  │
                     │             │                         │
                     │  ┌──────────▼─────────────────────┐  │
                     │  │    Jinja2 Environment           │  │
                     │  │    (cache_size=0)               │  │
                     │  └──────────┬─────────────────────┘  │
                     │             │                         │
                     │  ┌──────────▼─────────────────────┐  │
                     │  │    Templates/*.html             │  │
                     │  │    base.html (layout)           │  │
                     │  │    index.html (dashboard)       │  │
                     │  │    events.html                  │  │
                     │  │    alerts.html                  │  │
                     │  │    rules.html                   │  │
                     │  └────────────────────────────────┘  │
                     └──────────────────────────────────────┘
```

## Componentes Nuevos

### 1. Layout base (`base.html`)

Plantilla base que define la estructura HTML común:

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }} — {% block title %}Dashboard{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100">
    <nav><!-- navegación común --></nav>
    <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

- Tailwind CSS vía CDN — sin build step, ideal para prototipado
- Navegación superior fija con links a Dashboard, Eventos, Alertas, Reglas
- Bloque `{% block content %}` que cada página hija llena
- Tema oscuro (`bg-gray-900`) para reducir fatiga visual en herramientas de seguridad

### 2. Dashboard (`index.html`)

Página principal con métricas en vivo:

- **3 cards superiores**: Eventos hoy, Alertas activas, Reglas activas
  - Cada card lee datos reales de la BD a través de consultas SQLAlchemy
  - Colores semánticos: cyan para eventos, amarillo para alertas, verde para reglas
- **Tabla de últimos 10 eventos**: timestamp, tipo, severidad (con colores), source, IP origen, descripción
  - Severidad se pinta con colores: CRITICAL (rojo), HIGH (naranja), MEDIUM (amarillo), LOW (azul), INFO (gris)
  - Link "Ver todos →" que lleva a `/events`

### 3. Eventos (`events.html`)

Lista paginada de eventos con filtros:

- **Filtro por severidad**: botones tipo pill para filtrar por critical/high/medium/low/info
  - El filtro activo se marca con `bg-cyan-600`
  - Los botones preservan el resto de parámetros de la URL
- **Tabla completa**: timestamp, tipo, severidad, source, IP origen, IP destino, puerto, usuario, descripción
- **Paginación**: botones "Anterior / Siguiente" con preservación de filtros en la URL
  - Muestra "Página X de Y" con el total de eventos

### 4. Alertas (`alerts.html`)

Lista paginada de alertas con filtros duales y acciones:

- **Filtros combinados**: estado + severidad funcionan juntos
  - Cada filtro preserva el otro en los parámetros de URL
  - Ejemplo: `/alerts?estado=open&severidad=critical`
- **Tabla**: título + descripción truncada, severidad, estado (con badges de colores),
  contador de eventos, fecha de creación, fecha de resolución
- **Formulario de cambio de estado**: select + botón OK por cada alerta abierta
  - Opciones: Ack, Investigar, Resolver, Falso Positivo
  - Se envía como POST a `/alerts/{id}/estado` (los formularios HTML
    nativos solo soportan GET/POST, no PATCH)
  - Las alertas ya resueltas/falsos positivos muestran "—" en lugar del formulario

### 5. Reglas (`rules.html`)

Lista paginada de reglas de detección:

- **Filtro por estado**: active / disabled / test
- **Tabla**: título, descripción truncada, severidad, estado, alert_title + alert_severity,
  fecha de creación, tags (máximo 3 visibles + "N más"), botón de acción
- **Toggle activar/desactivar**: formulario POST a `/rules/{id}/toggle`
  - Si está activa → botón rojo "Desactivar"
  - Si está desactivada/en test → botón verde "Activar"
  - Al togglear, recarga el engine de correlación automáticamente
- **Link a Swagger**: botón "+ Nueva regla (API)" que lleva a `/docs`
  porque crear reglas requiere JSON complejo (condiciones anidadas)

## El Bug de Jinja2 3.1.x + Python 3.13

### Síntoma

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
```

Esto lanzaba:

```
TypeError: unhashable type: 'dict'
```

### Causa raíz

Jinja2 3.1.x introdujo un cambio donde el cache key de TemplateResponse
intenta hashear el diccionario `globals` del `Environment`. Cuando se usa
`Jinja2Templates` de Starlette, internamente el `Environment` tiene
`globals` que incluye una referencia al `request` (que es un dict de
Starlette Request). Jinja2 intenta usar ese dict como parte del cache key,
pero los dicts no son hasheables en Python 3.13.

### Solución

Reemplazar Starlette `Jinja2Templates` con Jinja2 directamente:

```python
from jinja2 import Environment, FileSystemLoader, select_autoescape

jinja_env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0,  # Deshabilitar caché para evitar el bug
)

def render_template(name: str, context: dict) -> HTMLResponse:
    template = jinja_env.get_template(name)
    content = template.render(context)
    return HTMLResponse(content)
```

Puntos clave:
- `cache_size=0` deshabilita el caché de Jinja2, evitando completamente
  el problema de hashing
- Sin `Jinja2Templates`, no hay `request` mágico en el contexto — hay que
  pasarlo explícitamente en el dict de contexto
- `render_template()` devuelve `HTMLResponse` directamente

## Lecciones Aprendidas

### 1. HTML Forms solo soportan GET y POST

HTML nativo solo permite `<form method="get|post">`. Para acciones REST
como PATCH (actualizar estado de alerta), el formulario envía POST a una
ruta dedicada (`/alerts/{id}/estado`), no directamente al endpoint REST.

```html
<form action="/alerts/{{ a.id }}/estado" method="post">
    <select name="estado">
        <option value="acknowledged">Ack</option>
        <option value="investigating">Investigar</option>
        <option value="resolved">Resolver</option>
    </select>
    <button type="submit">OK</button>
</form>
```

### 2. Depends() no funciona en rutas de templates

FastAPI `Depends()` obtiene la sesión de BD del sistema de dependencias,
que está diseñado para endpoints API que devuelven JSON. Para rutas HTML
con `response_class=HTMLResponse`, hay que usar el async generator
directamente:

```python
async def obtener_session():
    from app.database import async_session
    async with async_session() as session:
        yield session

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    async for session in obtener_session():
        # ... consultas ...
        return render_template("index.html", context)
```

### 3. Paginación con preservación de filtros

Cada link de paginación debe preservar los filtros activos en la URL.
La sintaxis Jinja2 es verbosa pero necesaria:

```jinja2
<a href="/events?pagina={{ pagina_actual + 1 }}
  {%- if severidad_seleccionada %}
    &severidad={{ severidad_seleccionada }}
  {%- endif %}">
```

El `{%- %}` (con guión) elimina whitespace antes/después, evitando
espacios extras en la URL.

### 4. Badges de severidad con colores semánticos

En vez de usar librerías externas de badges, se usa Tailwind con
colores semánticos inline:

| Severidad | Color | Clase Tailwind |
|-----------|-------|----------------|
| critical | rojo | `bg-red-900/50 text-red-400` |
| high | naranja | `bg-orange-900/50 text-orange-400` |
| medium | amarillo | `bg-yellow-900/50 text-yellow-400` |
| low | azul | `bg-blue-900/50 text-blue-400` |
| info | gris | `bg-gray-700 text-gray-400` |

El patrón es: fondo semitransparente + texto del mismo color a full opacidad.
Esto funciona bien sobre el fondo oscuro.

### 5. Tema oscuro como estándar de seguridad

Las herramientas de seguridad (SIEM, dashboards de monitoreo) usan
tema oscuro por defecto porque:
- Reduce fatiga visual en monitoreo continuo
- Mejor contraste para alerts críticos (rojo sobre negro resalta más)
- Consume menos energía en pantallas OLED
- Es el estándar de la industria (Splunk, Sentinel, Grafana)

### 6. CDN Tailwind para prototipado, build para producción

Usar Tailwind vía CDN (`<script src="https://cdn.tailwindcss.com">`)
es excelente para desarrollo y prototipado rápido porque:
- No requiere npm, node_modules, ni build step
- Hot-reload funciona editando HTML directamente
- Para producción se reemplaza con el build estático de Tailwind CLI

## Archivos Creados/Modificados

| Archivo | Descripción |
|---------|-------------|
| `app/templates/base.html` | Layout base con navegación y Tailwind CDN |
| `app/templates/index.html` | Dashboard con cards + eventos recientes |
| `app/templates/events.html` | Lista de eventos con paginación y filtros |
| `app/templates/alerts.html` | Lista de alertas con filtros + cambio de estado |
| `app/templates/rules.html` | Lista de reglas con toggle activar/desactivar |
| `app/main.py` | Rutas HTML, `render_template()`, Jinja2 Environment |
| `app/static/` | Directorio para archivos estáticos (CSS/JS) |

## Próximos Pasos (Fase 05)

- **Correlación temporal**: usar `correlation_window` para contar eventos
  en una ventana de tiempo y solo alertar si se supera un umbral
- **Gráficas con Chart.js**: timeline de eventos, distribución por severidad
- **Exportación CSV**: botón para descargar alertas como CSV
- **Notificaciones por email**: enviar alertas por correo electrónico
