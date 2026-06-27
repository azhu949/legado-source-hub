/** 认证状态管理。 */

import { create } from "zustand"
import { persist } from "zustand/middleware"
import { login as apiLogin, getMe } from "@/api/auth"

interface AuthState {
  token: string | null
  username: string | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  checkAuth: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      username: null,
      isAuthenticated: false,

      login: async (username: string, password: string) => {
        const res = await apiLogin(username, password)
        if (res.success && res.data) {
          set({
            token: res.data.access_token,
            username: res.data.username,
            isAuthenticated: true,
          })
        } else {
          throw new Error(res.error?.message || "登录失败")
        }
      },

      logout: () => {
        set({
          token: null,
          username: null,
          isAuthenticated: false,
        })
      },

      checkAuth: () => {
        const { token } = get()
        if (!token) return false
        // 简单检查 token 格式（JWT 有三个部分）
        const parts = token.split(".")
        if (parts.length !== 3) {
          get().logout()
          return false
        }
        try {
          const payload = JSON.parse(atob(parts[1]))
          if (payload.exp && payload.exp * 1000 < Date.now()) {
            get().logout()
            return false
          }
        } catch {
          get().logout()
          return false
        }
        return true
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        token: state.token,
        username: state.username,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
)
