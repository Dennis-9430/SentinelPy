import { useQueries } from "@tanstack/react-query"
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { apiFetch } from "@/lib/api"
import type { Event, EventStats, AlertStats } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { SeverityBadge } from "@/components/SeverityBadge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

// ── Severity pie colors ─────────────────────────────────────────────
const SEV_PIE_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
  info: "#6b7280",
}

// ── Helpers ─────────────────────────────────────────────────────────
function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function sumValues(obj: Record<string, number>): number {
  return Object.values(obj).reduce((a, b) => a + b, 0)
}

// ── Stat Card ───────────────────────────────────────────────────────
function StatCard({
  title,
  value,
  loading,
  error,
}: {
  title: string
  value?: string | number
  loading: boolean
  error: boolean
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="h-8 w-20 animate-pulse rounded-md bg-muted" />
        ) : error ? (
          <p className="text-xs text-destructive">Error al cargar</p>
        ) : (
          <p className="text-3xl font-bold">{value ?? "—"}</p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Chart loading skeleton ──────────────────────────────────────────
function ChartSkeleton() {
  return (
    <div className="flex h-64 items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
    </div>
  )
}

// ── Chart error banner ──────────────────────────────────────────────
function ChartError({ message }: { message: string }) {
  return (
    <div className="flex h-64 items-center justify-center rounded-md border border-destructive/30 bg-destructive/5 p-4">
      <p className="text-sm text-destructive">{message}</p>
    </div>
  )
}

// ── Dashboard Page ──────────────────────────────────────────────────
export default function DashboardPage() {
  const queries = useQueries({
    queries: [
      {
        queryKey: ["events-stats"],
        queryFn: () =>
          apiFetch<EventStats>("/events/stats?horas=24"),
      },
      {
        queryKey: ["alerts-stats"],
        queryFn: () =>
          apiFetch<AlertStats>("/alerts/stats"),
      },
      {
        queryKey: ["rules-active"],
        queryFn: () =>
          apiFetch<{ reglas: unknown[]; total: number }>(
            "/rules?estado=active&limite=1",
          ),
      },
      {
        queryKey: ["recent-events"],
        queryFn: () =>
          apiFetch<{ eventos: Event[]; total: number }>("/events?limite=10"),
      },
    ],
  })

  const [eventsStats, alertsStats, rulesData, recentEvents] = queries

  // Computed stats
  const totalEvents = eventsStats.data
    ? sumValues(eventsStats.data.por_severidad)
    : 0

  const openAlerts = alertsStats.data
    ? Object.entries(alertsStats.data.por_estado)
        .filter(([status]) =>
          ["open", "acknowledged", "investigating"].includes(status),
        )
        .reduce((sum, [, count]) => sum + count, 0)
    : 0

  const activeRules = rulesData.data?.total ?? 0

  // Chart data
  const timelineData =
    eventsStats.data?.timeline.map((t) => ({
      hora: new Date(t.hora).getHours() + ":00",
      total: t.total,
    })) ?? []

  const severityData = eventsStats.data
    ? Object.entries(eventsStats.data.por_severidad).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value,
        color: SEV_PIE_COLORS[name] ?? "#6b7280",
      }))
    : []

  const eventos = recentEvents.data?.eventos ?? []

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* ── Stat Cards ───────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          title="Eventos 24h"
          value={totalEvents}
          loading={eventsStats.isLoading}
          error={eventsStats.isError}
        />
        <StatCard
          title="Alertas activas"
          value={openAlerts}
          loading={alertsStats.isLoading}
          error={alertsStats.isError}
        />
        <StatCard
          title="Reglas activas"
          value={activeRules}
          loading={rulesData.isLoading}
          error={rulesData.isError}
        />
        <StatCard
          title="Últimos eventos"
          value={recentEvents.data?.total ?? 0}
          loading={recentEvents.isLoading}
          error={recentEvents.isError}
        />
      </div>

      {/* ── Charts Row ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Timeline LineChart */}
        <Card>
          <CardHeader>
            <CardTitle>Eventos 24h</CardTitle>
          </CardHeader>
          <CardContent>
            {eventsStats.isLoading ? (
              <ChartSkeleton />
            ) : eventsStats.isError ? (
              <ChartError message="Error al cargar línea de tiempo" />
            ) : timelineData.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Sin datos en las últimas 24 horas
              </p>
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={timelineData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="hsl(var(--border))"
                    />
                    <XAxis
                      dataKey="hora"
                      tick={{ fontSize: 12 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fontSize: 12 }}
                    />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="total"
                      stroke="#22d3ee"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Severity PieChart */}
        <Card>
          <CardHeader>
            <CardTitle>Por severidad</CardTitle>
          </CardHeader>
          <CardContent>
            {eventsStats.isLoading ? (
              <ChartSkeleton />
            ) : eventsStats.isError ? (
              <ChartError message="Error al cargar distribución" />
            ) : severityData.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Sin datos de severidad
              </p>
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={severityData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={({ name, percent }) =>
                        `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
                      }
                    >
                      {severityData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Recent Events Table ──────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Últimos eventos</CardTitle>
        </CardHeader>
        <CardContent>
          {recentEvents.isLoading ? (
            <ChartSkeleton />
          ) : recentEvents.isError ? (
            <ChartError message="Error al cargar eventos recientes" />
          ) : eventos.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No hay eventos registrados
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Severidad</TableHead>
                  <TableHead>Fuente</TableHead>
                  <TableHead>Descripción</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {eventos.map((ev) => (
                  <TableRow key={ev.id}>
                    <TableCell className="font-mono text-xs">
                      {formatTime(ev.event_timestamp)}
                    </TableCell>
                    <TableCell>{ev.event_type}</TableCell>
                    <TableCell>
                      <SeverityBadge severity={ev.severity} />
                    </TableCell>
                    <TableCell className="max-w-[120px] truncate">
                      {ev.source}
                    </TableCell>
                    <TableCell className="max-w-xs truncate">
                      {ev.description}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
