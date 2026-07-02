// ── Usuario / Autenticación ──────────────────────────────────────────────

export interface User {
  id: string
  username: string
  role: "admin" | "analyst"
  active?: boolean
  created_at?: string
}

// ── Eventos ──────────────────────────────────────────────────────────────

export interface Event {
  id: string
  event_timestamp: string
  event_type: string
  severity: string
  source: string
  description: string
  raw_data: string
  collected_at: string
}

export interface EventsResponse {
  eventos: Event[]
  total: number
}

export interface EventStats {
  timeline: Array<{ hora: string; total: number }>
  por_severidad: Record<string, number>
}

// ── Alertas ──────────────────────────────────────────────────────────────

export interface Alert {
  id: string
  rule_id: string
  title: string
  severity: string
  status: string
  event_count: number
  description: string | null
  created_at: string
  resolved_at: string | null
}

export interface AlertsResponse {
  alertas: Alert[]
  total: number
}

export interface AlertStats {
  por_severidad: Record<string, number>
  por_estado: Record<string, number>
}

// ── Reglas ───────────────────────────────────────────────────────────────

export interface Rule {
  id: string
  title: string
  description: string
  author: string | null
  severity: string
  status: string
  conditions: Record<string, unknown>
  correlation_window: number | null
  alert_title: string
  alert_severity: string
  tags: string[]
  created_at: string
}

export interface RulesResponse {
  reglas: Rule[]
  total: number
}

export interface ToggleRuleResponse {
  status: string
}

export interface CreateRulePayload {
  title: string
  description: string
  severity: string
  alert_title: string
  alert_severity: string
  author?: string
  status?: string
  conditions: Record<string, unknown>
  correlation_window?: number
  tags?: string[]
  references?: string[]
  false_positives?: string
}

export interface CreateRuleResponse {
  id: string
  title: string
  severity: string
  status: string
  created_at: string
}

// ── Usuarios ─────────────────────────────────────────────────────────────

export interface UsersResponse {
  usuarios: User[]
  total: number
}

export interface CreateUserPayload {
  username: string
  password: string
  role: string
}
