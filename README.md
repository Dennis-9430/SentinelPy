# SentinelPy 🔍

**Plataforma Inteligente de Monitoreo y Detección de Incidentes para PyMEs.**

SentinelPy es un SIEM (Security Information and Event Management) ligero diseñado
para entornos de aprendizaje y pequeñas/medianas empresas. Construido con Python,
FastAPI, y PostgreSQL.

## Arquitectura

```
                    ┌─────────────┐
                    │  Dashboard   │
                    │ (Jinja2/React)│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Engine    │
                    │ (Correlation)│
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼────┐ ┌────▼───┐ ┌─────▼────┐
        │ Collector │ │ Parser │ │ PostgreSQL│
        │ (Inputs)  │ │(Normal-│ │ (Storage) │
        │           │ │ izer)  │ │           │
        └───────────┘ └────────┘ └──────────┘
```

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.13+, FastAPI |
| Base de datos | PostgreSQL 16 + SQLAlchemy 2.0 |
| Frontend N1 | Jinja2 + Tailwind CSS |
| Frontend N2 | React + TypeScript |
| Contenedores | Docker + Docker Compose |

## Inicio Rápido

```bash
# Clonar
git clone https://github.com/Dennis-9430/SentinelPy.git
cd SentinelPy

# Iniciar servicios
docker compose up -d

# La API se sirve en http://localhost:8000
```

## Fases del Proyecto

| Fase | Descripción | Estado |
|------|-------------|--------|
| 01 | Fundamentos y estructura | ✅ |
| 02 | Colectores y parsing | ⏳ |
| 03 | Motor de correlación | 📅 |
| 04 | Dashboard en vivo | 📅 |
| 05 | Agente remoto | 📅 |
| 06 | IA y análisis | 📅 |

## Licencia

Proyecto educativo — sin licencia formal.
