import {
  Activity,
  Bell,
  Bot,
  Database,
  GitBranch,
  LayoutDashboard,
  List,
  Shield,
  ShieldCheck,
  Users,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

// ── Data ─────────────────────────────────────────────────────────────────
const dataFlow = [
  {
    title: "Ingesta",
    description:
      "Los eventos llegan por dos vías: el colector syslog (puerto 5140) que recibe logs de firewalls, servidores y aplicaciones, o los agentes remotos (Python) que monitorean endpoints y envían logs vía API con autenticación por API key.",
    icon: Database,
  },
  {
    title: "Normalización",
    description:
      "El pipeline parsea los logs crudos y los normaliza a un formato estructurado con campos comunes: timestamp, tipo de evento, severidad, IP fuente y metadatos.",
    icon: Activity,
  },
  {
    title: "Correlación",
    description:
      "El motor de correlación evalúa cada evento contra las reglas activas. Las reglas estilo Sigma detectan patrones (ej. fuerza bruta SSH) contando ocurrencias en ventanas temporales.",
    icon: GitBranch,
  },
  {
    title: "Alertas",
    description:
      "Cuando una regla coincide, se crea o actualiza una alerta con severidad, estado y conteo de eventos relacionados. Las alertas se agrupan automáticamente por regla + IP fuente.",
    icon: Bell,
  },
  {
    title: "Análisis",
    description:
      "El servicio de análisis complementa las reglas con detección de anomalías (IsolationForest), baselines z-score y scoring de riesgo por entidad.",
    icon: ShieldCheck,
  },
  {
    title: "Enriquecimiento",
    description:
      "Threat Intelligence consulta providers externos (AbuseIPDB, AlienVault OTX, VirusTotal) para enriquecer indicadores de compromiso (IOC) con reputación y contexto.",
    icon: Shield,
  },
  {
    title: "Notificación",
    description:
      "Si la severidad lo amerita, los notificadores envían alertas por email (SMTP) o webhook (Slack/Discord) para avisar al equipo sin esperar a que alguien abra el dashboard.",
    icon: Bell,
  },
  {
    title: "Almacenamiento y consulta",
    description:
      "Todos los eventos, reglas, alertas y agentes se persisten en PostgreSQL. La SPA consulta los datos a través de la API REST con autenticación JWT.",
    icon: Database,
  },
]

const appSections = [
  {
    title: "Dashboard",
    description:
      "Vista principal con estadísticas en vivo: eventos por hora, distribución por severidad, métricas de alertas y las últimas alertas generadas.",
    icon: LayoutDashboard,
    path: "/",
  },
  {
    title: "Eventos",
    description:
      "Tabla paginada de todos los eventos normalizados con filtro por severidad. Es el detalle crudo de lo que el sistema está recibiendo.",
    icon: List,
    path: "/events",
  },
  {
    title: "Alertas",
    description:
      "Alertas generadas por el motor de correlación. Permite cambiar su estado (open, investigating, resolved), exportar a CSV y ver agrupaciones.",
    icon: Bell,
    path: "/alerts",
  },
  {
    title: "Reglas",
    description:
      "Reglas de detección estilo Sigma: condición, umbral y ventana temporal. Solo admin puede crearlas, activarlas/desactivarlas o eliminarlas.",
    icon: Shield,
    path: "/rules",
  },
  {
    title: "Agentes",
    description:
      "Gestión de agentes remotos: crear agentes con API key, ver su estado y heartbeats. Acceso restringido a admin.",
    icon: Bot,
    path: "/agents",
  },
  {
    title: "Usuarios",
    description:
      "CRUD de usuarios del sistema con roles. Solo admin puede crear usuarios o desactivarlos.",
    icon: Users,
    path: "/users",
  },
]

const roles = [
  {
    role: "Admin",
    permissions: [
      "Crear, editar y eliminar reglas",
      "Activar/desactivar reglas",
      "Crear y desactivar usuarios",
      "Gestionar agentes remotos",
      "Todo lo que puede hacer un analyst",
    ],
  },
  {
    role: "Analyst",
    permissions: [
      "Ver dashboard, eventos y alertas",
      "Cambiar estado de alertas",
      "Exportar alertas a CSV",
      "Consulta de threat intel",
    ],
  },
]

// ── Help Page ───────────────────────────────────────────────────────────
export default function HelpPage() {
  return (
    <div className="space-y-8">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold">Ayuda</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Cómo funciona SentinelPy: arquitectura, flujo de datos, secciones y roles.
        </p>
      </div>

      {/* ── Qué es ───────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>¿Qué es SentinelPy?</CardTitle>
          <CardDescription>
            SIEM ligero para PyMEs — Python + FastAPI + React + PostgreSQL
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="leading-relaxed text-muted-foreground">
            SentinelPy es un Security Information and Event Management diseñado
            para entornos de aprendizaje y pequeñas/medianas empresas. Colecta
            eventos de seguridad, los normaliza, corre reglas de correlación en
            tiempo real y genera alertas con notificaciones por email/webhook.
          </p>
        </CardContent>
      </Card>

      {/* ── Flujo de datos ───────────────────────────────────────────── */}
      <div>
        <h2 className="mb-4 text-lg font-semibold">Cómo fluyen los datos</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {dataFlow.map((step, i) => (
            <Card key={step.title}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                    {i + 1}
                  </span>
                  <step.icon className="h-4 w-4 text-primary" />
                  {step.title}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {step.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* ── Secciones ────────────────────────────────────────────────── */}
      <div>
        <h2 className="mb-4 text-lg font-semibold">Secciones de la aplicación</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {appSections.map((section) => (
            <Card key={section.title}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <section.icon className="h-4 w-4 text-primary" />
                  {section.title}
                  <span className="ml-auto rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                    {section.path}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {section.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* ── Roles ────────────────────────────────────────────────────── */}
      <div>
        <h2 className="mb-4 text-lg font-semibold">Roles y permisos</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {roles.map((r) => (
            <Card key={r.role}>
              <CardHeader>
                <CardTitle>{r.role}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  {r.permissions.map((p) => (
                    <li key={p} className="flex items-start gap-2">
                      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* ── Conceptos clave ──────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Conceptos clave</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Evento</p>
              <p className="text-sm text-muted-foreground">
                Un log normalizado (intento de login, conexión de firewall,
                proceso, etc.) con campos estructurados. Es la unidad base de
                información.
              </p>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Regla</p>
              <p className="text-sm text-muted-foreground">
                Una condición de detección estilo Sigma (ej. "≥10 fallos de
                autenticación en 5 minutos desde una IP"). Define qué patrón
                buscar y con qué severidad alertar.
              </p>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Alerta</p>
              <p className="text-sm text-muted-foreground">
                El resultado de que una regla haya coincidido. Tiene severidad,
                estado y conteo de eventos relacionados. Puede agruparse por
                regla + IP fuente.
              </p>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Threat Intelligence</p>
              <p className="text-sm text-muted-foreground">
                Enriquecimiento de indicadores (IPs, hashes, dominios) con
                reputación externa de AbuseIPDB, AlienVault OTX y VirusTotal
                para priorizar investigaciones.
              </p>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Agente remoto</p>
              <p className="text-sm text-muted-foreground">
                Cliente Python asyncio que monitorea logs en un endpoint y los
                envía al servidor vía API segura con rate limiting, cola local
                y heartbeats.
              </p>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Correlación temporal</p>
              <p className="text-sm text-muted-foreground">
                El motor cuenta eventos de un mismo tipo dentro de una ventana
                de tiempo (ej. 10 minutos) y dispara la alerta al superar el
                umbral configurado.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
