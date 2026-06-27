/** 认证 API。 */

import apiClient from "./client"
import type { ApiResponse, LoginResponse } from "@/types/api"

export async function login(username: string, password: string): Promise<ApiResponse<LoginResponse>> {
  return apiClient.post("/auth/login", { username, password })
}

export async function getMe(): Promise<ApiResponse<{ username: string }>> {
  return apiClient.get("/auth/me")
}
