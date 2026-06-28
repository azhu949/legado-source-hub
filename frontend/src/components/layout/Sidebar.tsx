/** 管理后台侧边导航栏。 */

import { Link, useLocation } from "react-router-dom"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  BookOpen,
  FlaskConical,
  Activity,
  Database,
  ScrollText,
  LogOut,
  Library,
  FileJson,
} from "lucide-react"
import { useAuthStore } from "@/stores/authStore"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"

const navItems = [
  { label: "仪表盘", path: "/admin", icon: LayoutDashboard },
  { label: "聚合书源", path: "/admin/aggregate", icon: FileJson },
  { label: "书源管理", path: "/admin/sources", icon: BookOpen },
  { label: "规则测试", path: "/admin/rules/test", icon: FlaskConical },
  { label: "健康监控", path: "/admin/health", icon: Activity },
  { label: "缓存管理", path: "/admin/cache", icon: Database },
  { label: "操作日志", path: "/admin/logs", icon: ScrollText },
]

export function Sidebar() {
  const location = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const username = useAuthStore((s) => s.username)

  const isActive = (path:string) => {
    if (path === "/admin") return location.pathname === "/admin"
    return location.pathname.startsWith(path)
  }

  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-card">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2 px-4">
        <Library className="h-6 w-6 text-primary" />
        <span className="text-lg font-bold">聚合书源管理</span>
      </div>

      <Separator />

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive(item.path)
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        ))}
      </nav>

      <Separator />

      {/* User info */}
      <div className="p-3">
        <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
            {(username || "A")[0].toUpperCase()}
          </div>
          <span className="flex-1 truncate">{username || "admin"}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="mt-1 w-full justify-start text-muted-foreground"
          onClick={() => {
            logout()
            window.location.href = "/admin/login"
          }}
        >
          <LogOut className="mr-2 h-4 w-4" />
          退出登录
        </Button>
      </div>
    </aside>
  )
}
