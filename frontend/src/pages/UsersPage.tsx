import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiFetch, ApiError } from "@/lib/api"
import type { UsersResponse, CreateUserPayload } from "@/lib/types"
import { useAuth } from "@/hooks/useAuth"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"
import { Navigate } from "react-router-dom"
import { Loader2, Plus, Ban, CheckCircle2, AlertCircle } from "lucide-react"

// ── Role badge config ──────────────────────────────────────────────────
function roleBadge(role: string) {
  const isAdmin = role === "admin"
  return (
    <Badge
      variant={isAdmin ? "default" : "secondary"}
      className={
        isAdmin
          ? "bg-purple-600/15 text-purple-700 dark:text-purple-400"
          : "bg-blue-600/15 text-blue-700 dark:text-blue-400"
      }
    >
      {isAdmin ? "Admin" : "Analyst"}
    </Badge>
  )
}

// ── Active status badge ────────────────────────────────────────────────
function activeBadge(active: boolean | undefined) {
  return active ? (
    <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
      <CheckCircle2 className="h-3 w-3" />
      Activo
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Ban className="h-3 w-3" />
      Inactivo
    </span>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────
function formatDate(iso: string | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return d.toLocaleDateString("es-AR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
}

// ── Create User Dialog ─────────────────────────────────────────────────
function CreateUserDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [role, setRole] = useState("analyst")
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: (payload: CreateUserPayload) =>
      apiFetch<{ id: string; username: string; role: string }>("/users", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      resetForm()
      onOpenChange(false)
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setApiError(err.message)
      } else {
        setApiError("Error al crear usuario")
      }
    },
  })

  function resetForm() {
    setUsername("")
    setPassword("")
    setRole("analyst")
    setFieldErrors({})
    setApiError(null)
  }

  function validate(): boolean {
    const errors: Record<string, string> = {}

    if (!username.trim()) {
      errors.username = "El usuario es obligatorio"
    } else if (username.trim().length < 3) {
      errors.username = "Mínimo 3 caracteres"
    }

    if (!password) {
      errors.password = "La contraseña es obligatoria"
    } else if (password.length < 6) {
      errors.password = "Mínimo 6 caracteres"
    }

    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setApiError(null)

    if (!validate()) return

    createMutation.mutate({
      username: username.trim(),
      password,
      role,
    })
  }

  function handleOpenChange(open: boolean) {
    if (!open) resetForm()
    onOpenChange(open)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Crear Usuario</DialogTitle>
          <DialogDescription>
            Ingresá los datos del nuevo usuario del sistema
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {apiError && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{apiError}</span>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium">Usuario</label>
            <Input
              placeholder="nombre de usuario"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-invalid={!!fieldErrors.username}
            />
            {fieldErrors.username && (
              <p className="text-xs text-destructive">{fieldErrors.username}</p>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Contraseña</label>
            <Input
              type="password"
              placeholder="••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={!!fieldErrors.password}
            />
            {fieldErrors.password && (
              <p className="text-xs text-destructive">{fieldErrors.password}</p>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Rol</label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="analyst">Analyst</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
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
                "Crear Usuario"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ── Deactivate Confirmation Dialog ─────────────────────────────────────
function DeactivateDialog({
  open,
  onOpenChange,
  username,
  userId,
  onConfirm,
  isPending,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  username: string
  userId: string
  onConfirm: (id: string) => void
  isPending: boolean
}) {
  function handleConfirm() {
    onConfirm(userId)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Desactivar Usuario</DialogTitle>
          <DialogDescription>
            ¿Estás seguro de que querés desactivar a <strong>{username}</strong>?
            El usuario no podrá iniciar sesión hasta que sea reactivado.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancelar
            </Button>
          </DialogClose>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                Desactivando...
              </>
            ) : (
              "Desactivar"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Users Page ─────────────────────────────────────────────────────────
export default function UsersPage() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()

  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [deactivateTarget, setDeactivateTarget] = useState<{
    id: string
    username: string
  } | null>(null)
  const [feedback, setFeedback] = useState<{
    type: "success" | "error"
    message: string
  } | null>(null)

  // ── Non-admin redirect ─────────────────────────────────────────────
  if (currentUser && currentUser.role !== "admin") {
    return <Navigate to="/" replace />
  }

  // ── Fetch users ────────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ["users"],
    queryFn: () => apiFetch<UsersResponse>("/users"),
    enabled: currentUser?.role === "admin",
  })

  const usuarios = data?.usuarios ?? []

  // ── Deactivate mutation with optimistic update ─────────────────────
  const deactivateMutation = useMutation({
    mutationFn: (userId: string) =>
      apiFetch<{ mensaje: string }>(`/users/${userId}/desactivar`, {
        method: "PATCH",
      }),
    onMutate: async (userId) => {
      await queryClient.cancelQueries({ queryKey: ["users"] })

      const previousData = queryClient.getQueryData<UsersResponse>(["users"])

      // Optimistically deactivate
      queryClient.setQueryData<UsersResponse>(["users"], (old) => {
        if (!old) return old
        return {
          ...old,
          usuarios: old.usuarios.map((u) =>
            u.id === userId ? { ...u, active: false } : u,
          ),
        }
      })

      return { previousData }
    },
    onSuccess: () => {
      setFeedback({ type: "success", message: "Usuario desactivado correctamente" })
      setDeactivateTarget(null)
    },
    onError: (_err, _vars, context) => {
      // Rollback
      if (context?.previousData) {
        queryClient.setQueryData(["users"], context.previousData)
      }
      setFeedback({ type: "error", message: "Error al desactivar usuario" })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  function handleDeactivate(userId: string) {
    deactivateMutation.mutate(userId)
  }

  function handleCloseDeactivateDialog() {
    setDeactivateTarget(null)
  }

  // Auto-dismiss feedback after 4 seconds
  useEffect(() => {
    if (!feedback) return
    const id = setTimeout(() => setFeedback(null), 4000)
    return () => clearTimeout(id)
  }, [feedback])

  const isAdmin = currentUser?.role === "admin"

  return (
    <div className="space-y-6">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Usuarios</h1>

        {isAdmin && (
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Crear Usuario
          </Button>
        )}
      </div>

      {/* ── Feedback banner ────────────────────────────────────────── */}
      {feedback && (
        <div
          className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm ${
            feedback.type === "success"
              ? "border-green-600/20 bg-green-600/10 text-green-700 dark:text-green-400"
              : "border-destructive/20 bg-destructive/10 text-destructive"
          }`}
        >
          {feedback.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* ── Table ──────────────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex h-64 items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          ) : isError ? (
            <div className="flex h-64 items-center justify-center">
              <p className="text-sm text-destructive">
                Error al cargar usuarios
              </p>
            </div>
          ) : usuarios.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <p className="text-sm text-muted-foreground">
                No se encontraron usuarios
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Usuario</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="hidden sm:table-cell">Creado</TableHead>
                  <TableHead className="text-right">Acción</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usuarios.map((u) => {
                  const isSelf = currentUser?.id === u.id
                  const isPending =
                    deactivateMutation.isPending &&
                    deactivateMutation.variables === u.id

                  return (
                    <TableRow key={u.id}>
                      <TableCell className="font-medium">
                        {u.username}
                        {isSelf && (
                          <span className="ml-2 text-xs text-muted-foreground">
                            (vos)
                          </span>
                        )}
                      </TableCell>
                      <TableCell>{roleBadge(u.role)}</TableCell>
                      <TableCell>{activeBadge(u.active)}</TableCell>
                      <TableCell className="hidden text-muted-foreground sm:table-cell">
                        {formatDate(u.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        {u.active && !isSelf && (
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={isPending}
                            onClick={() =>
                              setDeactivateTarget({
                                id: u.id,
                                username: u.username,
                              })
                            }
                          >
                            {isPending ? (
                              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                            ) : (
                              <Ban className="mr-1 h-4 w-4" />
                            )}
                            Desactivar
                          </Button>
                        )}
                        {isSelf && (
                          <span className="text-xs text-muted-foreground">
                            —
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Create User Dialog ─────────────────────────────────────── */}
      <CreateUserDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
      />

      {/* ── Deactivate Confirmation Dialog ─────────────────────────── */}
      <DeactivateDialog
        open={!!deactivateTarget}
        onOpenChange={handleCloseDeactivateDialog}
        username={deactivateTarget?.username ?? ""}
        userId={deactivateTarget?.id ?? ""}
        onConfirm={handleDeactivate}
        isPending={deactivateMutation.isPending}
      />
    </div>
  )
}
