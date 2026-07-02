import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import type {
  RulesResponse,
  ToggleRuleResponse,
  CreateRulePayload,
  CreateRuleResponse,
} from "@/lib/types"
import { useAuth } from "@/hooks/useAuth"
import { Card, CardContent } from "@/components/ui/card"
import { SeverityBadge } from "@/components/SeverityBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  ChevronLeft,
  ChevronRight,
  Power,
  PowerOff,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react"

const PAGE_SIZE = 20

// ── Status badge ───────────────────────────────────────────────────────
function statusBadge(status: string) {
  const isActive = status === "active"
  return (
    <Badge
      variant={isActive ? "default" : "secondary"}
      className={
        isActive
          ? "bg-green-600/15 text-green-700 dark:text-green-400"
          : "text-muted-foreground"
      }
    >
      {isActive ? "Activa" : "Desactivada"}
    </Badge>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────
function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + "…"
}

// ── Create Rule Dialog ────────────────────────────────────────────────
function CreateRuleDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [severity, setSeverity] = useState("medium")
  const [alertTitle, setAlertTitle] = useState("")
  const [alertSeverity, setAlertSeverity] = useState("medium")
  const [eventType, setEventType] = useState("")
  const [threshold, setThreshold] = useState("5")
  const [windowMinutes, setWindowMinutes] = useState("10")
  const [author, setAuthor] = useState("")
  const [tags, setTags] = useState("")
  const [status, setStatus] = useState("active")

  const createMutation = useMutation({
    mutationFn: (payload: CreateRulePayload) =>
      apiFetch<CreateRuleResponse>("/rules", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] })
      onOpenChange(false)
      // Reset form
      setTitle("")
      setDescription("")
      setSeverity("medium")
      setAlertTitle("")
      setAlertSeverity("medium")
      setEventType("")
      setThreshold("5")
      setWindowMinutes("10")
      setAuthor("")
      setTags("")
      setStatus("active")
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const conditions: Record<string, unknown> = {
      event_type: eventType,
      threshold: Number(threshold),
    }
    const payload: CreateRulePayload = {
      title,
      description,
      severity,
      alert_title: alertTitle,
      alert_severity: alertSeverity,
      conditions,
      correlation_window: Number(windowMinutes),
      status,
      author: author || undefined,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    }
    createMutation.mutate(payload)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Crear regla</DialogTitle>
          <DialogDescription>
            Nueva regla de detección estilo Sigma. Se cargará automáticamente
            en el motor de correlación.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* ── Title ────────────────────────────────────────────────── */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Título *</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Detección de fuerza bruta SSH"
              required
            />
          </div>

          {/* ── Description ──────────────────────────────────────────── */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Descripción *</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              rows={3}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Detecta múltiples fallos de autenticación SSH en un período corto"
            />
          </div>

          {/* ── Severity + Status ────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Severidad *</label>
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="critical">Critical</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Estado</label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Activa</SelectItem>
                  <SelectItem value="disabled">Desactivada</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* ── Alert title + Alert severity ─────────────────────────── */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Título de alerta *</label>
              <Input
                value={alertTitle}
                onChange={(e) => setAlertTitle(e.target.value)}
                placeholder="Alerta: Fuerza bruta SSH"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Severidad alerta</label>
              <Select value={alertSeverity} onValueChange={setAlertSeverity}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="critical">Critical</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* ── Condiciones: Event type + Threshold + Window ──────────── */}
          <div className="rounded-md border bg-muted/30 p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              Condiciones de detección
            </p>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Tipo de evento</label>
                <Input
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value)}
                  placeholder="auth_failure"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Umbral</label>
                <Input
                  type="number"
                  min={1}
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium">Ventana (min)</label>
                <Input
                  type="number"
                  min={1}
                  value={windowMinutes}
                  onChange={(e) => setWindowMinutes(e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* ── Author + Tags ────────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Autor</label>
              <Input
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="Tu nombre"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Tags</label>
              <Input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="ssh, brute-force"
              />
            </div>
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancelar
              </Button>
            </DialogClose>
            <Button
              type="submit"
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? (
                <>
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  Creando...
                </>
              ) : (
                "Crear regla"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ── Rules Page ─────────────────────────────────────────────────────────
export default function RulesPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)

  const desde = page * PAGE_SIZE

  // ── Fetch rules ─────────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ["rules", desde],
    queryFn: () =>
      apiFetch<RulesResponse>(`/rules?limite=${PAGE_SIZE}&desde=${desde}`),
    placeholderData: (prev) => prev,
  })

  const reglas = data?.reglas ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // ── Toggle mutation ──────────────────────────────────────────────────
  const toggleMutation = useMutation({
    mutationFn: (ruleId: string) =>
      apiFetch<ToggleRuleResponse>(`/rules/${ruleId}/toggle`, {
        method: "PATCH",
      }),
    onMutate: async (ruleId) => {
      await queryClient.cancelQueries({ queryKey: ["rules"] })
      const previousData = queryClient.getQueriesData<RulesResponse>({
        queryKey: ["rules"],
      })
      queryClient.setQueriesData<RulesResponse>(
        { queryKey: ["rules"] },
        (old) => {
          if (!old) return old
          return {
            ...old,
            reglas: old.reglas.map((r) =>
              r.id === ruleId
                ? {
                    ...r,
                    status: r.status === "active" ? "disabled" : "active",
                  }
                : r,
            ),
          }
        },
      )
      return { previousData }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        for (const [key, data] of context.previousData) {
          queryClient.setQueryData(key, data)
        }
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] })
    },
  })

  // ── Delete mutation ──────────────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (ruleId: string) =>
      apiFetch<void>(`/rules/${ruleId}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rules"] })
    },
  })

  function handleToggle(ruleId: string) {
    toggleMutation.mutate(ruleId)
  }

  function handleDelete(ruleId: string) {
    if (window.confirm("¿Eliminar esta regla definitivamente?")) {
      deleteMutation.mutate(ruleId)
    }
  }

  function handlePrevPage() {
    setPage((p) => Math.max(0, p - 1))
  }

  function handleNextPage() {
    setPage((p) => p + 1)
  }

  const isAdmin = user?.role === "admin"

  return (
    <div className="space-y-6">
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Reglas</h1>
        {isAdmin && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Nueva regla
          </Button>
        )}
      </div>

      {/* ── Table ────────────────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex h-64 items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          ) : isError ? (
            <div className="flex h-64 items-center justify-center">
              <p className="text-sm text-destructive">
                Error al cargar reglas
              </p>
            </div>
          ) : reglas.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <p className="text-sm text-muted-foreground">
                No se encontraron reglas
              </p>
              {isAdmin && (
                <Button variant="outline" onClick={() => setCreateOpen(true)}>
                  <Plus className="mr-1 h-4 w-4" />
                  Crear primera regla
                </Button>
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Descripción</TableHead>
                  <TableHead>Severidad</TableHead>
                  <TableHead>Estado</TableHead>
                  {isAdmin && (
                    <TableHead className="text-right">Acción</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {reglas.map((rule) => {
                  const isToggling =
                    toggleMutation.isPending &&
                    toggleMutation.variables === rule.id
                  const isDeleting =
                    deleteMutation.isPending &&
                    deleteMutation.variables === rule.id
                  const isActive = rule.status === "active"

                  return (
                    <TableRow key={rule.id}>
                      <TableCell className="font-medium">
                        {rule.title}
                      </TableCell>
                      <TableCell className="max-w-sm truncate text-muted-foreground">
                        {truncate(rule.description, 120)}
                      </TableCell>
                      <TableCell>
                        <SeverityBadge severity={rule.severity} />
                      </TableCell>
                      <TableCell>{statusBadge(rule.status)}</TableCell>
                      {isAdmin && (
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant={isActive ? "destructive" : "default"}
                              size="sm"
                              disabled={isToggling || isDeleting}
                              onClick={() => handleToggle(rule.id)}
                            >
                              {isToggling ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : isActive ? (
                                <PowerOff className="h-4 w-4" />
                              ) : (
                                <Power className="h-4 w-4" />
                              )}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={isToggling || isDeleting}
                              onClick={() => handleDelete(rule.id)}
                              className="text-muted-foreground hover:text-destructive"
                            >
                              {isDeleting ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </Button>
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Pagination ───────────────────────────────────────────────── */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Página {page + 1} de {totalPages} ({total} reglas)
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

      {/* ── Create Rule Dialog ────────────────────────────────────────── */}
      {isAdmin && (
        <CreateRuleDialog open={createOpen} onOpenChange={setCreateOpen} />
      )}
    </div>
  )
}
