import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { apiFetch } from "@/lib/api"
import type { CreateAgentPayload, CreateAgentResponse } from "@/lib/types"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"
import { Loader2, Copy, Check } from "lucide-react"

// ── API Key Modal ─────────────────────────────────────────────────────
function ApiKeyModal({
  apiKey,
  agentName,
  open,
  onClose,
}: {
  apiKey: string
  agentName: string
  open: boolean
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(apiKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-destructive">
            ⚠️ API Key — {agentName}
          </DialogTitle>
          <DialogDescription>
            <strong className="block text-destructive text-base">
              GUARDA ESTA KEY — no se mostrará de nuevo
            </strong>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            El agente necesita esta API key para autenticarse contra el servidor.
            Si la pierdes, deberás generar una nueva.
          </p>

          <div className="flex items-center gap-2 rounded-md border bg-muted/30 p-3">
            <code className="flex-1 break-all font-mono text-sm select-all">
              {apiKey}
            </code>
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopy}
              className="shrink-0"
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-600" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={onClose}>Entendido, la guardé</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Create Agent Dialog ───────────────────────────────────────────────
export function CreateAgentDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const [hostname, setHostname] = useState("")
  const [apiKeyResult, setApiKeyResult] = useState<{
    key: string
    name: string
  } | null>(null)

  const createMutation = useMutation({
    mutationFn: (payload: CreateAgentPayload) =>
      apiFetch<CreateAgentResponse>("/admin/agents", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (data) => {
      setApiKeyResult({ key: data.api_key, name: data.name })
      // Reset form
      setName("")
      setHostname("")
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    createMutation.mutate({ name, hostname })
  }

  function handleApiKeyModalClose() {
    setApiKeyResult(null)
    onOpenChange(false)
    queryClient.invalidateQueries({ queryKey: ["agents"] })
  }

  return (
    <>
      <Dialog open={open && !apiKeyResult} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Crear agente</DialogTitle>
            <DialogDescription>
              Nuevo agente remoto. La API key se generará automáticamente.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Nombre *</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="servidor-produccion-01"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">Hostname *</label>
              <Input
                value={hostname}
                onChange={(e) => setHostname(e.target.value)}
                placeholder="srv-prod-01.example.com"
                required
              />
            </div>

            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancelar
                </Button>
              </DialogClose>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? (
                  <>
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    Creando...
                  </>
                ) : (
                  "Crear agente"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* API Key reveal modal — shown only once after creation */}
      {apiKeyResult && (
        <ApiKeyModal
          apiKey={apiKeyResult.key}
          agentName={apiKeyResult.name}
          open={true}
          onClose={handleApiKeyModalClose}
        />
      )}
    </>
  )
}
