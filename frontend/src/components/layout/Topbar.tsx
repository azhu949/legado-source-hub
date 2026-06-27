/** 顶部栏：面包屑 + 用户信息。 */

import { useLocation, Link } from "react-router-dom"
import { ChevronRight, Home } from "lucide-react"

const nameMap: Record<string, string> = {
  admin: "仪表盘",
  aggregate: "聚合书源",
  sources: "书源管理",
  rules: "规则测试",
  health: "健康监控",
  logs: "操作日志",
  new: "新增书源",
  edit: "编辑书源",
  import: "批量导入",
  test: "测试",
}

export function Topbar() {
  const location = useLocation()
  const segments = location.pathname.split("/").filter(Boolean)

  const breadcrumbs = segments.map((seg, i) => ({
    label: nameMap[seg] || seg,
    path: "/" + segments.slice(0, i + 1).join("/"),
    isLast: i === segments.length - 1,
  }))

  return (
    <header className="flex h-14 items-center border-b bg-card px-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1 text-sm text-muted-foreground">
        <Link to="/admin" className="hover:text-foreground">
          <Home className="h-4 w-4" />
        </Link>
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.path} className="flex items-center gap-1">
            <ChevronRight className="h-3 w-3" />
            {crumb.isLast ? (
              <span className="font-medium text-foreground">{crumb.label}</span>
            ) : (
              <Link to={crumb.path} className="hover:text-foreground">
                {crumb.label}
              </Link>
            )}
          </span>
        ))}
      </nav>
    </header>
  )
}
