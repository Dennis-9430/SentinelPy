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
import type { Event, EventStats, AlertStats, AnomaliesResponse, RisksResponse } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { SeverityBadge } from "@/components/SeverityBadge"
import { RiskBadge } from "@/components/RiskBadge"
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
  return d.toLocaleString("en-US", {
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
  description,
  loading,
  error,
}: {
  title: string
  value?: string | number
  description?: string
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
          <p className="text-xs text-destructive">Error loading</p>
        ) : (
          <>
            <p className="text-3xl font-bold">{value ?? "—"}</p>
            {description && (
              <p className="mt-1 text-xs text-muted-foreground">{description}</p>
            )}
          </>
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
          apiFetch<EventStats>("/stats/events?horas=24"),
      },
      {
        queryKey: ["alerts-stats"],
        queryFn: () =>
          apiFetch<AlertStats>("/stats/alerts"),
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
      {
        queryKey: ["anomalies-count"],
        queryFn: () => apiFetch<AnomaliesResponse>("/analysis/anomalies?limite=1"),
      },
      {
        queryKey: ["top-risks"],
        queryFn: () => apiFetch<RisksResponse>("/analysis/risks?limite=5"),
      },
    ],
  })

  const [eventsStats, alertsStats, rulesData, recentEvents, anomaliesData, topRisks] = queries

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
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatCard
          title="Events 24h"
          description="Events received in the last 24 hours"
          value={totalEvents}
          loading={eventsStats.isLoading}
          error={eventsStats.isError}
        />
        <StatCard
          title="Active alerts"
          description="Open alerts that need attention"
          value={openAlerts}
          loading={alertsStats.isLoading}
          error={alertsStats.isError}
        />
        <StatCard
          title="Active rules"
          description="Enabled detection rules"
          value={activeRules}
          loading={rulesData.isLoading}
          error={rulesData.isError}
        />
        <StatCard
          title="Recent events"
          description="Total events recorded in the system"
          value={recentEvents.data?.total ?? 0}
          loading={recentEvents.isLoading}
          error={recentEvents.isError}
        />
        <StatCard
          title="Anomalies"
          description="Anomalous behaviors detected"
          value={anomaliesData.data?.total ?? 0}
          loading={anomaliesData.isLoading}
          error={anomaliesData.isError}
        />
        <StatCard
          title="Entities at risk"
          description="Hosts or users with the highest risk"
          value={topRisks.data?.total ?? 0}
          loading={topRisks.isLoading}
          error={topRisks.isError}
        />
      </div>

      {/* ── Charts Row ───────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Timeline LineChart */}
        <Card>
          <CardHeader>
            <CardTitle>Events 24h</CardTitle>
            <p className="text-xs text-muted-foreground">
              Hourly distribution of events in the last 24 hours
            </p>
          </CardHeader>
          <CardContent>
            {eventsStats.isLoading ? (
              <ChartSkeleton />
            ) : eventsStats.isError ? (
              <ChartError message="Error loading timeline" />
            ) : timelineData.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No data in the last 24 hours
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
            <CardTitle>By severity</CardTitle>
            <p className="text-xs text-muted-foreground">
              Event distribution by severity level
            </p>
          </CardHeader>
          <CardContent>
            {eventsStats.isLoading ? (
              <ChartSkeleton />
            ) : eventsStats.isError ? (
              <ChartError message="Error loading distribution" />
            ) : severityData.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No severity data
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

      {/* ── Top Risks ────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Top Entities at Risk</CardTitle>
          <p className="text-xs text-muted-foreground">
            Hosts or users with the highest accumulated risk score
          </p>
        </CardHeader>
        <CardContent>
          {topRisks.isLoading ? (
            <ChartSkeleton />
          ) : topRisks.isError ? (
            <ChartError message="Error loading risks" />
          ) : (topRisks.data?.risks ?? []).length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No risk data
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Entity</TableHead>
                  <TableHead className="text-right">Risk</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topRisks.data!.risks.map((risk) => (
                  <TableRow key={risk.entity_key}>
                    <TableCell className="font-mono text-sm">{risk.entity_key}</TableCell>
                    <TableCell className="text-right">
                      <RiskBadge score={risk.risk_score} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Recent Events Table ──────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Recent events</CardTitle>
          <p className="text-xs text-muted-foreground">
            The 10 most recent events recorded in the system
          </p>
        </CardHeader>
        <CardContent>
          {recentEvents.isLoading ? (
            <ChartSkeleton />
          ) : recentEvents.isError ? (
            <ChartError message="Error loading recent events" />
          ) : eventos.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No events recorded
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Description</TableHead>
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
