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
  group_key: string | null
  group_name: string | null
  risk_score: number | null
}

export interface AlertGroupItem {
  group_key: string
  group_name: string
  alert_count: number
  max_severity: string
  risk_score: number | null
  alerts: Array<{
    id: string
    title: string
    severity: string
    status: string
    event_count: number
    created_at: string
  }>
}

export interface AlertGroupsResponse {
  groups: AlertGroupItem[]
  total: number
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

// ── Agents ─────────────────────────────────────────────────────────────

export interface Agent {
  id: number
  name: string
  hostname: string
  last_seen: string | null
  active: boolean
  version?: string
  created_at: string
}

export interface AgentsResponse {
  agents: Agent[]
  total: number
  page: number
  per_page: number
}

export interface CreateAgentPayload {
  name: string
  hostname: string
}

export interface CreateAgentResponse {
  id: number
  name: string
  api_key: string
}

export interface DeactivateAgentResponse {
  mensaje: string
}

// ── Análisis / IA (Slice 1) ──────────────────────────────────────────────

export interface AnalysisAlert {
  id: string
  source: string
  collector_type: string
  event_type: string
  severity: string
  description: string | null
  source_ip: string | null
  destination_ip: string | null
  source_port: number | null
  destination_port: number | null
  user_name: string | null
  event_timestamp: string
  analysis_data: {
    zscores?: Record<string, number>
    ml_score?: number
  } | null
}

export interface RiskScore {
  entity_key: string
  risk_score: number
  updated_at: string | null
}

export interface AnomaliesResponse {
  anomalies: AnalysisAlert[]
  total: number
}

export interface RisksResponse {
  risks: RiskScore[]
  total: number
}
