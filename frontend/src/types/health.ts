/** 健康检查类型。 */

export interface HealthOverview {
  total: number
  healthy: number
  unhealthy: number
  avg_latency_ms: number
  last_check: string | null
}

export interface HealthRecord {
  id: number
  source_id: string
  source_name: string
  status: "healthy" | "unhealthy"
  latency_ms: number | null
  message: string
  checked_at: string
}

export interface HealthTrendPoint {
  hour: string
  avg_latency: number
  cnt: number
}
