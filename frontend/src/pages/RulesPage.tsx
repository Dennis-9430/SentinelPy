import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import type { RulesResponse, ToggleRuleResponse } from "@/lib/types"
import { useAuth } from "@/hooks/useAuth"
import { Card, CardContent } from "@/components/ui/card"
import { SeverityBadge } from "@/components/SeverityBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  ChevronLeft,
  ChevronRight,
  Power,
  PowerOff,
  Loader2,
} from "lucide-react"

const PAGE_SIZE = 20

// ── Status badge config ──────────────────────────────────────────────
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

// ── Helpers ──────────────────────────────────────────────────────────
function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + "…"
}

// ── Rules Page ───────────────────────────────────────────────────────
export default function RulesPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(0)

  const desde = page * PAGE_SIZE

  // ── Fetch rules ───────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ["rules", desde],
    queryFn: () =>
      apiFetch<RulesResponse>(`/rules?limite=${PAGE_SIZE}&desde=${desde}`),
    placeholderData: (prev) => prev,
  })

  const reglas = data?.reglas ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // ── Toggle mutation ───────────────────────────────────────────────
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

      // Optimistically toggle the status
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

  function handleToggle(ruleId: string) {
    toggleMutation.mutate(ruleId)
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
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Reglas</h1>
      </div>

      {/* ── Table ─────────────────────────────────────────────────── */}
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
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Descripción</TableHead>
                  <TableHead>Severidad</TableHead>
                  <TableHead>Estado</TableHead>
                  {isAdmin && <TableHead className="text-right">Acción</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {reglas.map((rule) => {
                  const isPending =
                    toggleMutation.isPending &&
                    toggleMutation.variables === rule.id
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
                          <Button
                            variant={isActive ? "destructive" : "default"}
                            size="sm"
                            disabled={isPending}
                            onClick={() => handleToggle(rule.id)}
                          >
                            {isPending ? (
                              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                            ) : isActive ? (
                              <PowerOff className="mr-1 h-4 w-4" />
                            ) : (
                              <Power className="mr-1 h-4 w-4" />
                            )}
                            {isActive ? "Desactivar" : "Activar"}
                          </Button>
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

      {/* ── Pagination ────────────────────────────────────────────── */}
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
    </div>
  )
}
