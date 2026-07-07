import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import type { AgentsResponse, DeactivateAgentResponse } from "@/lib/types"
import { useAuth } from "@/hooks/useAuth"
import { Card, CardContent } from "@/components/ui/card"
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
import { Loader2, Plus, PowerOff } from "lucide-react"
import { CreateAgentDialog } from "./CreateAgentDialog"

// ── Helpers ────────────────────────────────────────────────────────────

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return "—"
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diffMs = now - then

  // Handle future dates or invalid
  if (diffMs < 0) return "justo ahora"

  const seconds = Math.floor(diffMs / 1000)
  if (seconds < 60) return "hace segundos"

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `hace ${minutes}min`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `hace ${hours}h`

  const days = Math.floor(hours / 24)
  if (days < 30) return `hace ${days}d`

  const months = Math.floor(days / 30)
  if (months < 12) return `hace ${months}mes`

  const years = Math.floor(months / 12)
  return `hace ${years}a`
}

function statusBadge(active: boolean) {
  return (
    <Badge
      variant={active ? "default" : "secondary"}
      className={
        active
          ? "bg-green-600/15 text-green-700 dark:text-green-400"
          : "text-muted-foreground"
      }
    >
      {active ? "Activo" : "Inactivo"}
    </Badge>
  )
}

// ── Agents Page ─────────────────────────────────────────────────────────
export default function AgentsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)

  // ── Fetch agents ────────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiFetch<AgentsResponse>("/admin/agents"),
    placeholderData: (prev) => prev,
  })

  const agents = data?.agents ?? []

  // ── Deactivate mutation ─────────────────────────────────────────────
  const deactivateMutation = useMutation({
    mutationFn: (agentId: number) =>
      apiFetch<DeactivateAgentResponse>(`/admin/agents/${agentId}/deactivate`, {
        method: "PATCH",
      }),
    onMutate: async (agentId) => {
      await queryClient.cancelQueries({ queryKey: ["agents"] })
      const previousData = queryClient.getQueriesData<AgentsResponse>({
        queryKey: ["agents"],
      })
      queryClient.setQueriesData<AgentsResponse>(
        { queryKey: ["agents"] },
        (old) => {
          if (!old) return old
          return {
            ...old,
            agents: old.agents.map((a) =>
              a.id === agentId ? { ...a, active: false } : a,
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
      queryClient.invalidateQueries({ queryKey: ["agents"] })
    },
  })

  function handleDeactivate(agentId: number) {
    if (window.confirm("¿Desactivar este agente?")) {
      deactivateMutation.mutate(agentId)
    }
  }

  const isAdmin = user?.role === "admin"

  return (
    <div className="space-y-6">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Agentes</h1>
        {isAdmin && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Crear agente
          </Button>
        )}
      </div>

      {/* ── Table ──────────────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div
              data-testid="skeleton-loader"
              className="flex h-64 items-center justify-center"
            >
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          ) : isError ? (
            <div className="flex h-64 items-center justify-center">
              <p className="text-sm text-destructive">
                Error al cargar agentes
              </p>
            </div>
          ) : agents.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <p className="text-sm text-muted-foreground">
                No se encontraron agentes
              </p>
              {isAdmin && (
                <Button variant="outline" onClick={() => setCreateOpen(true)}>
                  <Plus className="mr-1 h-4 w-4" />
                  Crear primer agente
                </Button>
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Hostname</TableHead>
                  <TableHead>Último contacto</TableHead>
                  <TableHead>Estado</TableHead>
                  {isAdmin && (
                    <TableHead className="text-right">Acción</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {agents.map((agent) => {
                  const isDeactivating =
                    deactivateMutation.isPending &&
                    deactivateMutation.variables === agent.id

                  return (
                    <TableRow key={agent.id}>
                      <TableCell className="font-medium">
                        {agent.name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {agent.hostname}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatRelativeTime(agent.last_seen)}
                      </TableCell>
                      <TableCell>{statusBadge(agent.active)}</TableCell>
                      {isAdmin && (
                        <TableCell className="text-right">
                          {agent.active && (
                            <Button
                              variant="destructive"
                              size="sm"
                              disabled={isDeactivating}
                              onClick={() => handleDeactivate(agent.id)}
                            >
                              {isDeactivating ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <PowerOff className="h-4 w-4" />
                              )}
                            </Button>
                          )}
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

      {/* ── Create Agent Dialog ──────────────────────────────────── */}
      <CreateAgentDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
