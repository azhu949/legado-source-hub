/** 书源 CRUD API。 */

import apiClient from "./client"
import type { ApiResponse, PaginatedData } from "@/types/api"
import type { BookSource, BookSourceCreateInput, ImportResult, ConflictStrategy } from "@/types/source"

export async function getSources(params: {
  search?: string
  status?: string
  page?: number
  pageSize?: number
}): Promise<ApiResponse<PaginatedData<BookSource>>> {
  return apiClient.get("/sources", { params })
}

export async function getSource(id: string): Promise<ApiResponse<BookSource>> {
  return apiClient.get(`/sources/${id}`)
}

export async function createSource(data: BookSourceCreateInput): Promise<ApiResponse<BookSource>> {
  return apiClient.post("/sources", data)
}

export async function updateSource(id: string, data: BookSourceCreateInput): Promise<ApiResponse<BookSource>> {
  return apiClient.put(`/sources/${id}`, data)
}

export async function deleteSource(id: string): Promise<ApiResponse<null>> {
  return apiClient.delete(`/sources/${id}`)
}

export async function toggleSource(id: string, enabled: boolean): Promise<ApiResponse<BookSource>> {
  return apiClient.patch(`/sources/${id}/toggle`, { enabled })
}

export async function importSources(sources: Record<string, unknown>[], strategy: ConflictStrategy = "skip"): Promise<ApiResponse<ImportResult>> {
  return apiClient.post("/sources/import", { sources, conflictStrategy: strategy })
}

export async function importFromUrl(url: string, strategy: ConflictStrategy = "skip"): Promise<ApiResponse<ImportResult>> {
  return apiClient.post("/sources/import-url", { url, conflictStrategy: strategy })
}

export async function exportSources(): Promise<ApiResponse<BookSource[]>> {
  return apiClient.get("/sources/export")
}
