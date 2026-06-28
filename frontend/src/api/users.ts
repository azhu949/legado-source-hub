/** 访问用户 API。 */

import apiClient from "./client"
import type { ApiResponse } from "@/types/api"
import type { AccessUser, AccessUserInput } from "@/types/user"

export async function getUsers(): Promise<ApiResponse<AccessUser[]>> {
  return apiClient.get("/users")
}

export async function createUser(data: AccessUserInput): Promise<ApiResponse<AccessUser>> {
  return apiClient.post("/users", data)
}

export async function updateUser(
  id: string,
  data: Partial<AccessUserInput> & { enabled?: boolean },
): Promise<ApiResponse<AccessUser>> {
  return apiClient.patch(`/users/${id}`, data)
}

export async function rotateUserKey(id: string): Promise<ApiResponse<AccessUser>> {
  return apiClient.post(`/users/${id}/rotate-key`)
}

export async function deleteUser(id: string): Promise<ApiResponse<null>> {
  return apiClient.delete(`/users/${id}`)
}
