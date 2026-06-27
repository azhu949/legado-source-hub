/** API 响应泛型。 */

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  message?: string
  error?: {
    code: string
    message: string
  }
}

export interface PaginatedData<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export interface LoginResponse {
  access_token: string
  token_type: string
  username: string
  expires_in: number
}
