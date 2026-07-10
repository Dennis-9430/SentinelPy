import { useState } from "react"
import { SeverityBadge } from "@/components/SeverityBadge"
import { RiskBadge } from "@/components/RiskBadge"
import { Badge } from "@/components/ui/badge"
import { ChevronDown, ChevronRight } from "lucide-react"
import type { AlertGroupItem } from "@/lib/types"

// Reuse the same formatTime from AlertsPage or import from a shared util
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

const STATUS_CONFIG: Record<string, { label: string; variant: "destructive" | "secondary" | "default" | "outline" }> = {
  open: { label: "Abierto", variant: "destructive" },
  acknowledged: { label: "Reconocido", variant: "secondary" },
  investigating: { label: "En investigación", variant: "secondary" },
  resolved: { label: "Resuelto", variant: "default" },
  false_positive: { label: "Falso positivo", variant: "outline" },
}

export function AlertGroupRow({ group }: { group: AlertGroupItem }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border-b last:border-b-0">
      {/* Group summary row */}
      <div
        className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-muted/50"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="flex-1 truncate font-medium">{group.group_name}</span>
        <Badge variant="secondary" className="text-xs">
          {group.alert_count} alertas
        </Badge>
        <SeverityBadge severity={group.max_severity} />
        <RiskBadge score={group.risk_score} />
      </div>

      {/* Expanded: child alerts */}
      {expanded && (
        <div className="bg-muted/30 px-8 py-2">
          {group.alerts.map((alert) => {
            const cfg = STATUS_CONFIG[alert.status] ?? { label: alert.status, variant: "outline" as const }
            return (
              <div key={alert.id} className="flex items-center gap-3 border-b border-border/50 py-2 text-sm last:border-b-0">
                <span className="w-40 font-mono text-xs text-muted-foreground">
                  {formatTime(alert.created_at)}
                </span>
                <span className="flex-1 truncate">{alert.title}</span>
                <SeverityBadge severity={alert.severity} />
                <Badge variant={cfg.variant} className="font-mono text-xs">
                  {cfg.label}
                </Badge>
                <span className="text-xs text-muted-foreground">×{alert.event_count}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
