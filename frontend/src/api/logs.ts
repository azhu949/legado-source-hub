/** 操作日志 API。 */

import apiClient from "./client"
import type { ApiResponse, PaginatedData } from "@/types/api"

export interface LogEntry {
  id: number
  timestamp: string
  op_type: string
  target_source: string | null
  detail: string | null
  ip: string | null
  operator: string
}

export interface DashboardStats {
  totalSources: number
  enabledSources: number
  disabledSources: number
  todaySearchCount: number
  unhealthySources: number
  avgLatencyMs: number
  lastCheck: string | null
}

export async function getStats(): Promise<ApiResponse<DashboardStats>> {
  return apiClient.get("/stats")
}

export async function getLogs(params: {
  type?: string
  start?: string
  end?: string
  page?: number
  pageSize?: number
}): Promise<ApiResponse<PaginatedData<LogEntry>>> {
  return apiClient.get("/logs", { params })
}

export async function getRecentLogs(limit = 20): Promise<ApiResponse<LogEntry[]>> {
  return apiClient.get("/recent-logs", { params: { limit } })
}

export function getLogExportUrl(): string {
  const base = import.meta.env.VITE_API_BASE || "/api/admin"
  return `${base}/logs/export`
}
