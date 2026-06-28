/** 缓存管理页。 */

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import {
  BookOpen,
  Database,
  ListOrdered,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import {
  clearAllCache,
  getCacheStatus,
  type CacheClearResult,
  type CacheGroup,
  type CacheStatus,
} from "@/api/cache"

const groupIcons: Record<string, typeof Search> = {
  search: Search,
  book: BookOpen,
  toc: ListOrdered,
}

function formatNumber(value: number | undefined) {
  return new Intl.NumberFormat("zh-CN").format(value ?? 0)
}

export default function CachePage() {
  const [status, setStatus] = useState<CacheStatus | null>(null)
  const [lastClear, setLastClear] = useState<CacheClearResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const groups = useMemo<CacheGroup[]>(() => status?.groups ?? [], [status])

  const loadStatus = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getCacheStatus()
      if (res.success && res.data) {
        setStatus(res.data)
      } else {
        toast.error(res.error?.message || "缓存状态获取失败")
      }
    } catch {
      toast.error("缓存状态获取失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  const handleClear = async () => {
    setClearing(true)
    try {
      const res = await clearAllCache()
      if (res.success && res.data) {
        setLastClear(res.data)
        toast.success(`已清除 ${formatNumber(res.data.totalCleared)} 条缓存`)
        await loadStatus()
      } else {
        toast.error(res.error?.message || "清除缓存失败")
      }
    } catch {
      toast.error("清除缓存失败")
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">缓存管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            搜索、详情和目录缓存状态
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={loadStatus} disabled={loading || clearing}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
          <Button variant="destructive" size="sm" onClick={() => setConfirmOpen(true)} disabled={clearing}>
            <Trash2 className="h-4 w-4" />
            清除全部缓存
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Database className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-base">Redis 缓存</CardTitle>
              <p className="text-sm text-muted-foreground">当前业务缓存键总量</p>
            </div>
          </div>
          <Badge variant={status?.available ? "success" : "danger"}>
            {status?.available ? "已连接" : "未连接"}
          </Badge>
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold tracking-tight">
            {loading && !status ? "..." : formatNumber(status?.total)}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            清除缓存不会删除书源配置、操作日志或健康检查记录
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {groups.map((group) => {
          const Icon = groupIcons[group.key] || Database
          const cleared = lastClear?.groups.find((item) => item.key === group.key)?.cleared
          return (
            <Card key={group.key}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {group.label}
                </CardTitle>
                <Icon className="h-5 w-5 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{formatNumber(group.count)}</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {group.pattern}
                </p>
                {cleared !== undefined && (
                  <p className="mt-3 text-xs text-muted-foreground">
                    上次清除 {formatNumber(cleared)} 条
                  </p>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="清除全部缓存"
        description="将清除搜索、详情和目录缓存。下一次阅读 APP 请求会重新访问源站并重建缓存。"
        confirmLabel={clearing ? "清除中..." : "清除缓存"}
        variant="destructive"
        onConfirm={handleClear}
      />
    </div>
  )
}
