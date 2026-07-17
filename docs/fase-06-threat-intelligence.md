# Fase 6 — Threat Intelligence

## Introducción

Threat Intelligence (TI) es la capacidad de enriquecer eventos de seguridad con datos de amenazas externos. Cuando SentinelPy detecta una IP sospechosa en un evento, puede consultar proveedores de TI para determinar si esa IP es conocida como maliciosa, qué tipo de amenaza representa, y qué nivel de confianza tiene esa clasificación.

Esto permite a los analistas tomar decisiones informadas más rápido: en lugar de investigar manualmente cada IP, el sistema ya muestra si es un servidor C2, un nodo Tor, o una IP benigna de cloud.

## Providers soportados

| Provider | Tipos de IOC | API Key | Rate Limit | Descripción |
|----------|-------------|---------|------------|-------------|
| **AbuseIPDB** | IP | Requerida (gratis) | 1000/día | Reputación de IPs, confidence score |
| **AlienVault OTX** | IP, dominio, hash | Opcional (gratis) | Sin límite estricto | Pulses de amenazas, IOCs públicos |
| **VirusTotal** | IP, dominio, hash | Requerida (gratis) | 4 req/min | Análisis multi-antivirus, detecciones |

### Configuración

Agregar al archivo `.env`:

```bash
# Threat Intelligence
ABUSEIPDB_API_KEY=your_key_here          # Obtener en https://www.abuseipdb.com/account/api
VIRUSTOTAL_API_KEY=your_key_here         # Obtener en https://www.virustotal.com/gui/my-apikey
OTX_API_KEY=                             # Opcional — OTX funciona sin API key para lookups básicos
TI_ENRICHMENT_ENABLED=true               # Habilitar/deshabilitar enrichment
TI_CACHE_TTL_MINUTES=60                  # TTL del cache en minutos
```

> Si una API key está vacía, el provider se deshabilita silenciosamente sin errores.

## Cómo funciona el enrichment

### Flujo de datos

```
Evento llega al Pipeline
    │
    ├── Parse → Save to DB
    │
    ├── create_task AnalysisService.analyze(event)     [existente]
    │
    ├── create_task ThreatIntelService.enrich(event)    [NUEVO]
    │       │
    │       ├── Extraer source_ip, destination_ip
    │       ├── Buscar en cache → hit? retornar cache
    │       ├── Consultar providers (AbuseIPDB, OTX, VT)
    │       ├── Guardar en tabla IOCEntry
    │       └── Escribir event.analysis_data["ti"] = {matches: [...]}
    │
    └── Engine.evaluate(event_dict)
            └── Lee event_dict["ti"]["matches"] si existe
```

### Características clave

- **Fire-and-forget**: El enrichment NO bloquea la ingesta de eventos. Usa `asyncio.create_task()` para ejecutar en background.
- **Cache TTL**: Los lookups se cachean en memoria (dict + timestamps, máx 1000 entries). Evita llamar APIs repetidamente.
- **Fallback graceful**: Si un provider falla, se loguea un warning y se retorna empty. Los errores NUNCA se propagan al pipeline.
- **Modo offline**: Si todas las API keys están vacías, el servicio se deshabilita silenciosamente.

### Almacenamiento

Los resultados del enrichment se guardan en `event.analysis_data["ti"]`:

```json
{
  "ti": {
    "matches": [
      {
        "type": "ip",
        "indicator": "185.220.101.34",
        "confidence": 95,
        "provider": "abuseipdb"
      }
    ]
  }
}
```

## API Endpoints

### GET /api/v1/threat-intel/feeds

Lista el estado de todos los providers registrados.

**Response:**
```json
{
  "feeds": [
    {
      "name": "abuseipdb",
      "status": "active",
      "supported_types": ["ip"]
    },
    {
      "name": "otx",
      "status": "active",
      "supported_types": ["ip", "domain", "hash"]
    },
    {
      "name": "virustotal",
      "status": "active",
      "supported_types": ["ip", "domain", "hash"]
    }
  ]
}
```

### POST /api/v1/threat-intel/lookup

Lookup manual de un IOC específico.

**Request:**
```json
{
  "indicator": "185.220.101.34",
  "ioc_type": "ip"
}
```

**Response:**
```json
{
  "indicator": "185.220.101.34",
  "ioc_type": "ip",
  "confidence": 95,
  "provider": "abuseipdb"
}
```

**Errores:**
- `404` — No se encontraron resultados para este indicador
- `503` — Servicio de TI no disponible

### GET /api/v1/threat-intel/iocs

Lista IOCs cacheados (paginado).

**Query params:** `limit=50`, `offset=0`

**Response:**
```json
{
  "iocs": [
    {
      "id": "uuid",
      "indicator": "185.220.101.34",
      "ioc_type": "ip",
      "provider": "abuseipdb",
      "confidence": 95,
      "first_seen": "2026-01-15T10:30:00Z",
      "last_seen": "2026-01-15T12:45:00Z",
      "expires_at": "2026-01-15T13:45:00Z"
    }
  ],
  "total": 123
}
```

## Frontend

### ThreatIntelPage (`/threat-intel`)

La página incluye:

1. **Provider Status Cards** — Muestra cada provider con nombre, estado, y tipos de IOC soportados
2. **Manual Lookup Form** — Input para indicador + select de tipo → resultados en tabla
3. **Cached IOCs Table** — Tabla paginada con todos los IOCs consultados

### Componentes utilizados

- React Query (`useQuery`, `useMutation`) para data fetching
- shadcn/ui (Card, Table, Input, Button, Select)
- `apiFetch<T>()` wrapper existente

## Correlación con Reglas

Las reglas de correlación pueden referenciar datos de TI usando notación punto:

```json
{
  "field": "ti.confidence",
  "operator": "gte",
  "value": 80
}
```

Esto permite crear reglas como:
- "Si una IP tiene confidence >= 80 en AbuseIPDB → alerta CRITICAL"
- "Si un dominio tiene IOCs en más de 2 providers → alerta HIGH"

## Testing

### Unit tests (sin DB)

- `test_ti_providers_base.py` — IOCResult, BaseTIProvider ABC, dispatch
- `test_ti_abuseipdb.py` — Success, 429, network error, empty data
- `test_ti_otx.py` — IP/domain/hash lookups, errors
- `test_ti_virustotal.py` — Confidence calculation, errors
- `test_threat_intel_service.py` — Cache hit/miss/TTL/eviction, enrich, feeds
- `test_engine_ti.py` — Engine handles TI data in conditions

### Integration tests

- `test_pipeline_ti.py` — Enrichment hook writes to analysis_data["ti"]
- `test_api_threat_intel.py` — API endpoints (feeds, lookup, iocs)

### E2E tests

- `test_e2e_threat_intel.py` — Full enrichment flow, caching, disabled mode

**Total: 180+ tests nuevos**

## Archivos creados/modificados

### Nuevos (15 archivos)

| Archivo | Descripción |
|---------|-------------|
| `backend/app/models/threat_intel.py` | ThreatIntelFeed + IOCEntry models |
| `backend/alembic/versions/009_create_threat_intel_tables.py` | Migración |
| `backend/app/services/threat_intel_service.py` | Servicio core + cache |
| `backend/app/services/ti_providers/__init__.py` | Package |
| `backend/app/services/ti_providers/base.py` | BaseTIProvider + IOCResult |
| `backend/app/services/ti_providers/abuseipdb.py` | AbuseIPDB provider |
| `backend/app/services/ti_providers/otx.py` | AlienVault OTX provider |
| `backend/app/services/ti_providers/virustotal.py` | VirusTotal provider |
| `backend/app/schemas/threat_intel.py` | Pydantic schemas |
| `backend/app/api/threat_intel.py` | API router (3 endpoints) |
| `frontend/src/pages/ThreatIntelPage.tsx` | Página Threat Intel |
| `backend/tests/test_config_ti.py` | Config tests |
| `backend/tests/test_models_threat_intel.py` | Model tests |
| `backend/tests/test_ti_providers_base.py` | Provider base tests |
| `backend/tests/test_ti_abuseipdb.py` | AbuseIPDB tests |
| `backend/tests/test_threat_intel_service.py` | Service tests |
| `backend/tests/test_ti_otx.py` | OTX tests |
| `backend/tests/test_ti_virustotal.py` | VirusTotal tests |
| `backend/tests/test_pipeline_ti.py` | Pipeline hook tests |
| `backend/tests/test_engine_ti.py` | Engine IOC tests |
| `backend/tests/test_api_threat_intel.py` | API tests |
| `backend/tests/test_e2e_threat_intel.py` | E2E tests |

### Modificados (5 archivos)

| Archivo | Cambio |
|---------|--------|
| `backend/app/config.py` | API keys + TI settings |
| `backend/app/services/pipeline.py` | TI enrichment hook |
| `backend/app/main.py` | ThreatIntelService wiring + router |
| `frontend/src/router.tsx` | Ruta /threat-intel |
| `frontend/src/components/Layout.tsx` | Nav item |
