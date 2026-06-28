/** 缓存管理 API。 */

import apiClient from "./client"
import type { ApiResponse } from "@/types/api"

export interface CacheGroup {
  key: string
  label: string
  pattern: string
  count?: number
  cleared?: number
}

export interface CacheStatus {
  available: boolean
  total: number
  groups: CacheGroup[]
}

export interface CacheClearResult {
  available: boolean
  totalCleared: number
  groups: CacheGroup[]
}

export async function getCacheStatus(): Promise<ApiResponse<CacheStatus>> {
  return apiClient.get("/cache")
}

export async function clearAllCache(): Promise<ApiResponse<CacheClearResult>> {
  return apiClient.post("/cache/clear")
}
