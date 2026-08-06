import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import type { AlertsResponse, AlertGroupsResponse } from "@/lib/types"
import { useAuth } from "@/hooks/useAuth"
import { Card, CardContent } from "@/components/ui/card"
import { SeverityBadge } from "@/components/SeverityBadge"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import {
  ChevronLeft,
  ChevronRight,
  Download,
  LayoutGrid,
  List,
  Loader2,
} from "lucide-react"
import { RiskBadge } from "@/components/RiskBadge"
import { AlertGroupRow } from "@/components/AlertGroup"

const PAGE_SIZE = 20
const ALL_VALUE = "__all__"

// ── Status config ────────────────────────────────────────────────────
const STATUS_CONFIG: Record<
  string,
  { label: string; variant: "destructive" | "secondary" | "default" | "outline" }
> = {
  open: { label: "Open", variant: "destructive" },
  acknowledged: { label: "Acknowledged", variant: "secondary" },
  investigating: { label: "Investigating", variant: "secondary" },
  resolved: { label: "Resolved", variant: "default" },
  false_positive: { label: "False positive", variant: "outline" },
}

const SEVERITY_OPTIONS = [
  { value: ALL_VALUE, label: "All severities" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
]

const STATUS_OPTIONS = [
  { value: ALL_VALUE, label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "investigating", label: "Investigating" },
  { value: "resolved", label: "Resolved" },
  { value: "false_positive", label: "False positive" },
]

const STATUS_TRANSITIONS: Record<string, string[]> = {
  open: ["acknowledged", "investigating"],
  acknowledged: ["investigating"],
  investigating: ["resolved", "false_positive"],
  resolved: [],
  false_positive: [],
}

// ── Helpers ──────────────────────────────────────────────────────────
function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

function shortId(uuid: string): string {
  return uuid.split("-")[0] ?? uuid.slice(0, 8)
}

function statusBadge(status: string) {
  const cfg = STATUS_CONFIG[status] ?? {
    label: status,
    variant: "outline" as const,
  }
  return (
    <Badge variant={cfg.variant} className="font-mono text-xs">
      {cfg.label}
    </Badge>
  )
}

// ── Alerts Page ─────────────────────────────────────────────────────
export default function AlertsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(0)
  const [severityFilter, setSeverityFilter] = useState(ALL_VALUE)
  const [statusFilter, setStatusFilter] = useState(ALL_VALUE)
  const [viewMode, setViewMode] = useState<"flat" | "grouped">("flat")

  const desde = page * PAGE_SIZE
  const filterSeverity =
    severityFilter === ALL_VALUE ? undefined : severityFilter
  const filterStatus =
    statusFilter === ALL_VALUE ? undefined : statusFilter

  // ── Fetch alerts ──────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ["alerts", desde, filterSeverity ?? "all", filterStatus ?? "all"],
    queryFn: () => {
      let path = `/alerts?limite=${PAGE_SIZE}&desde=${desde}`
      if (filterSeverity) path += `&severidad=${filterSeverity}`
      if (filterStatus) path += `&estado=${filterStatus}`
      return apiFetch<AlertsResponse>(path)
    },
    placeholderData: (prev) => prev,
  })

  const alertas = data?.alertas ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // ── Fetch groups ──────────────────────────────────────────────────
  const { data: groupsData, isLoading: groupsLoading, isError: groupsError } = useQuery({
    queryKey: ["alert-groups"],
    queryFn: () => apiFetch<AlertGroupsResponse>("/alerts/groups"),
    enabled: viewMode === "grouped",
  })

  // ── PATCH status mutation with optimistic update ──────────────────
  const patchMutation = useMutation({
    mutationFn: ({
      alertaId,
      status,
    }: {
      alertaId: string
      status: string
    }) =>
      apiFetch<{ id: string; status: string }>(`/alerts/${alertaId}/estado`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    onMutate: async ({ alertaId, status }) => {
      // Cancel outgoing refetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: ["alerts"] })

      // Snapshot previous value for rollback
      const previousData = queryClient.getQueriesData<AlertsResponse>({
        queryKey: ["alerts"],
      })

      // Optimistically update all cached alerts pages
      queryClient.setQueriesData<AlertsResponse>(
        { queryKey: ["alerts"] },
        (old) => {
          if (!old) return old
          return {
            ...old,
            alertas: old.alertas.map((a) =>
              a.id === alertaId ? { ...a, status } : a,
            ),
          }
        },
      )

      return { previousData }
    },
    onError: (_err, _vars, context) => {
      // Rollback to previous value
      if (context?.previousData) {
        for (const [key, data] of context.previousData) {
          queryClient.setQueryData(key, data)
        }
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] })
    },
  })

  // ── Handlers ──────────────────────────────────────────────────────
  function handleSeverityChange(value: string) {
    setSeverityFilter(value)
    setPage(0)
  }

  function handleStatusChange(value: string) {
    setStatusFilter(value)
    setPage(0)
  }

  function handlePrevPage() {
    setPage((p) => Math.max(0, p - 1))
  }

  function handleNextPage() {
    setPage((p) => p + 1)
  }

  function handleClearFilters() {
    setSeverityFilter(ALL_VALUE)
    setStatusFilter(ALL_VALUE)
    setPage(0)
  }

  function handleStatusTransition(alertaId: string, newStatus: string) {
    patchMutation.mutate({ alertaId, status: newStatus })
  }

  const isAdmin = user?.role === "admin"
  const hasFilters =
    severityFilter !== ALL_VALUE || statusFilter !== ALL_VALUE

  return (
    <div className="space-y-6">
      {/* ── Header row ────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Alerts</h1>

        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={severityFilter}
            onValueChange={handleSeverityChange}
          >
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Filter by severity" />
            </SelectTrigger>
            <SelectContent>
              {SEVERITY_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={statusFilter}
            onValueChange={handleStatusChange}
          >
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex rounded-md border">
            <Button
              variant={viewMode === "flat" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("flat")}
            >
              <List className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === "grouped" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("grouped")}
            >
              <LayoutGrid className="h-4 w-4" />
            </Button>
          </div>

          <Button variant="outline" size="sm" asChild>
            <a href="/api/v1/stats/alerts/exportar" download>
              <Download className="mr-1 h-4 w-4" />
              Export CSV
            </a>
          </Button>
        </div>
      </div>

      {/* ── Grouped View ──────────────────────────────────────────── */}
      {viewMode === "grouped" ? (
        <Card>
          <CardContent className="p-0">
            {groupsLoading ? (
              <div className="flex h-64 items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              </div>
            ) : groupsError ? (
              <div className="flex h-64 items-center justify-center">
                <p className="text-sm text-destructive">Error loading groups</p>
              </div>
            ) : (groupsData?.groups ?? []).length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16">
                <p className="text-sm text-muted-foreground">No alert groups</p>
              </div>
            ) : (
              <div>
                {groupsData!.groups.map((group) => (
                  <AlertGroupRow key={group.group_key} group={group} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        /* ── Flat table ──────────────────────────────────────────────── */
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex h-64 items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              </div>
            ) : isError ? (
              <div className="flex h-64 items-center justify-center">
                <p className="text-sm text-destructive">
                  Error loading alerts
                </p>
              </div>
            ) : alertas.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-16">
                <p className="text-sm text-muted-foreground">
                  No alerts found
                </p>
                {hasFilters && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleClearFilters}
                  >
                    Clear filters
                  </Button>
                )}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Rule</TableHead>
                    <TableHead>Event</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Risk</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {alertas.map((alert) => {
                    const isPending =
                      patchMutation.isPending &&
                      patchMutation.variables?.alertaId === alert.id
                    const transitions =
                      STATUS_TRANSITIONS[alert.status] ?? []

                    return (
                      <TableRow key={alert.id}>
                        <TableCell className="font-mono text-xs whitespace-nowrap">
                          {formatTime(alert.created_at)}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {shortId(alert.rule_id)}
                        </TableCell>
                        <TableCell className="max-w-xs truncate">
                          {alert.title}
                          {alert.group_name && (
                            <span className="ml-2 text-xs text-muted-foreground">
                              ({alert.group_name})
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          <SeverityBadge severity={alert.severity} />
                        </TableCell>
                        <TableCell>
                          <RiskBadge score={alert.risk_score} />
                        </TableCell>
                        <TableCell>{statusBadge(alert.status)}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            {isPending && (
                              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                            )}
                            {isAdmin && transitions.length > 0 ? (
                              <Select
                                value={alert.status}
                                onValueChange={(val) =>
                                  handleStatusTransition(alert.id, val)
                                }
                              >
                                <SelectTrigger className="h-7 w-auto px-2 text-xs" size="sm">
                                  <SelectValue placeholder="Change" />
                                </SelectTrigger>
                                <SelectContent>
                                  {transitions.map((st) => {
                                    const cfg = STATUS_CONFIG[st] ?? {
                                      label: st,
                                      variant: "default" as const,
                                    }
                                    return (
                                      <SelectItem key={st} value={st}>
                                        {cfg.label}
                                      </SelectItem>
                                    )
                                  })}
                                </SelectContent>
                              </Select>
                            ) : isAdmin ? (
                              <span className="text-xs text-muted-foreground">
                                Final
                              </span>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Pagination ────────────────────────────────────────────── */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages} ({total} alerts)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={handlePrevPage}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={handleNextPage}
            >
              Next
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
