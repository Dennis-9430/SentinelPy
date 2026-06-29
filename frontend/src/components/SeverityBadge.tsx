import { Badge } from "@/components/ui/badge"
import type { VariantProps } from "class-variance-authority"

const severityConfig: Record<
  string,
  { variant: VariantProps<typeof Badge>["variant"]; className: string }
> = {
  critical: {
    variant: "destructive",
    className: "border-destructive/50",
  },
  high: {
    variant: "outline",
    className:
      "border-orange-500/50 text-orange-600 dark:text-orange-400",
  },
  medium: {
    variant: "secondary",
    className:
      "border-yellow-500/30 text-yellow-700 dark:text-yellow-400",
  },
  low: {
    variant: "default",
    className:
      "border-green-500/30 text-green-700 dark:text-green-400",
  },
  info: {
    variant: "ghost",
    className: "text-muted-foreground",
  },
}

export function SeverityBadge({ severity }: { severity: string }) {
  const config = severityConfig[severity] ?? severityConfig.info
  return (
    <Badge variant={config.variant} className={config.className}>
      {severity}
    </Badge>
  )
}
