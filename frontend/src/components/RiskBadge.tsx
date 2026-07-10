import { Badge } from "@/components/ui/badge"

const riskConfig: Record<
  string,
  { variant: "destructive" | "secondary" | "default" | "outline"; className: string; label: string }
> = {
  high: {
    variant: "destructive",
    className: "border-red-500/50",
    label: "High Risk",
  },
  medium: {
    variant: "outline",
    className: "border-yellow-500/50 text-yellow-600 dark:text-yellow-400",
    label: "Medium Risk",
  },
  low: {
    variant: "default",
    className: "border-green-500/30 text-green-700 dark:text-green-400",
    label: "Low Risk",
  },
}

function getRiskLevel(score: number | null): string {
  if (score === null || score === undefined) return "low"
  if (score >= 0.6) return "high"
  if (score >= 0.3) return "medium"
  return "low"
}

export function RiskBadge({ score }: { score: number | null }) {
  const level = getRiskLevel(score)
  const config = riskConfig[level]
  return (
    <Badge variant={config.variant} className={config.className}>
      {score !== null ? `${(score * 100).toFixed(0)}%` : "—"}
    </Badge>
  )
}
