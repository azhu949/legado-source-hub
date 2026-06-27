/** 健康检查 & 统计 API。 */

import apiClient from "./client"
import type { ApiResponse, PaginatedData } from "@/types/api"
import type { HealthOverview, HealthRecord, HealthTrendPoint } from "@/types/health"

export async function getHealthOverview(): Promise<ApiResponse<HealthOverview>> {
  return apiClient.get("/health/overview")
}

export async function getHealthRecords(params: {
  sourceId?: string
  page?: number
  pageSize?: number
}): Promise<ApiResponse<PaginatedData<HealthRecord>>> {
  return apiClient.get("/health/records", { params })
}

export async function getHealthTrend(): Promise<ApiResponse<HealthTrendPoint[]>> {
  return apiClient.get("/health/trend")
}

export async function triggerHealthCheck(): Promise<ApiResponse<unknown>> {
  return apiClient.post("/health/check-now")
}
