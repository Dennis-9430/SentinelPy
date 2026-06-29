import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import type { Event } from "@/lib/types"
import { Card, CardContent } from "@/components/ui/card"
import { SeverityBadge } from "@/components/SeverityBadge"
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
import { ChevronLeft, ChevronRight } from "lucide-react"

const PAGE_SIZE = 20
const ALL_VALUE = "__all__"

const SEVERITY_OPTIONS = [
  { value: ALL_VALUE, label: "Todas las severidades" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "info", label: "Info" },
]

// ── Helpers ─────────────────────────────────────────────────────────
function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString("es-AR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

// ── Events Page ─────────────────────────────────────────────────────
export default function EventsPage() {
  const [page, setPage] = useState(0)
  const [severity, setSeverity] = useState(ALL_VALUE)

  const desde = page * PAGE_SIZE
  const filterSeverity =
    severity === ALL_VALUE ? undefined : severity

  const { data, isLoading, isError } = useQuery({
    queryKey: ["events", desde, filterSeverity ?? "all"],
    queryFn: () => {
      let path = `/events?limite=${PAGE_SIZE}&desde=${desde}`
      if (filterSeverity) {
        path += `&severidad=${filterSeverity}`
      }
      return apiFetch<{ eventos: Event[]; total: number }>(path)
    },
    placeholderData: (prev) => prev,
  })

  const eventos = data?.eventos ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function handleSeverityChange(value: string) {
    setSeverity(value)
    setPage(0)
  }

  function handlePrevPage() {
    setPage((p) => Math.max(0, p - 1))
  }

  function handleNextPage() {
    setPage((p) => p + 1)
  }

  function handleClearFilters() {
    setSeverity(ALL_VALUE)
    setPage(0)
  }

  return (
    <div className="space-y-6">
      {/* ── Header row ───────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Eventos</h1>

        <Select value={severity} onValueChange={handleSeverityChange}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="Filtrar por severidad" />
          </SelectTrigger>
          <SelectContent>
            {SEVERITY_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* ── Table ────────────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex h-64 items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          ) : isError ? (
            <div className="flex h-64 items-center justify-center">
              <p className="text-sm text-destructive">
                Error al cargar eventos
              </p>
            </div>
          ) : eventos.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <p className="text-sm text-muted-foreground">
                No se encontraron eventos
              </p>
              {severity !== ALL_VALUE && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleClearFilters}
                >
                  Limpiar filtros
                </Button>
              )}
            </div>
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
                    <TableCell className="font-mono text-xs whitespace-nowrap">
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

      {/* ── Pagination ───────────────────────────────────────────── */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Página {page + 1} de {totalPages} ({total} eventos)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={handlePrevPage}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={handleNextPage}
            >
              Siguiente
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
