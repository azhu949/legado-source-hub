/** axios 实例配置。 */

import axios from "axios"
import { useAuthStore } from "@/stores/authStore"

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api/admin",
  timeout: 15_000,
  headers: { "Content-Type": "application/json" },
})

// 请求拦截器：自动附加 token
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一错误处理
apiClient.interceptors.response.use(
  (res) => res.data,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = "/admin/login"
    }
    return Promise.reject(error)
  },
)

export default apiClient
