/** 健康监控页。 */

import { useEffect, useState, useRef, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { getHealthOverview, getHealthRecords, getHealthTrend, triggerHealthCheck } from "@/api/health"
import type { HealthOverview as HealthOverviewType, HealthRecord } from "@/types/health"
import { formatDate } from "@/lib/utils"
import { Activity, CheckCircle2, AlertTriangle, Clock, RefreshCw } from "lucide-react"
import { toast } from "sonner"
import { HEALTH_REFRESH_INTERVALS } from "@/lib/constants"

export default function HealthPage() {
  const [overview, setOverview] = useState<HealthOverviewType | null>(null)
  const [records, setRecords] = useState<HealthRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [refreshMs, setRefreshMs] = useState(30000)
  const [checking, setChecking] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [oRes, rRes] = await Promise.all([
        getHealthOverview(),
        getHealthRecords({ page, pageSize: 20 }),
      ])
      if (oRes.success && oRes.data) setOverview(oRes.data)
      if (rRes.success && rRes.data) {
        setRecords(rRes.data.items as HealthRecord[])
        setTotal(rRes.data.total)
      }
    } catch {
      // ignore
    }
  }, [page])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Auto refresh
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (refreshMs > 0) {
      intervalRef.current = setInterval(loadData, refreshMs)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [refreshMs, loadData])

  const handleCheckNow = async () => {
    setChecking(true)
    try {
      await triggerHealthCheck()
      toast.success("健康检查已触发")
      setTimeout(loadData, 5000)
    } catch {
      toast.error("触发失败")
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">健康监控</h1>
        <div className="flex items-center gap-2">
          <Select
            value={String(refreshMs)}
            onValueChange={(v) => setRefreshMs(Number(v))}
          >
            <SelectTrigger className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {HEALTH_REFRESH_INTERVALS.map((opt) => (
                <SelectItem key={opt.value} value={String(opt.value)}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={handleCheckNow} disabled={checking}>
            <RefreshCw className={`mr-2 h-4 w-4 ${checking ? "animate-spin" : ""}`} />
            {checking ? "检查中..." : "立即检查"}
          </Button>
        </div>
      </div>

      {/* Overview cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm text-muted-foreground">总书源数</CardTitle>
            <Activity className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.total ?? "-"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm text-muted-foreground">正常</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{overview?.healthy ?? "-"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm text-muted-foreground">异常</CardTitle>
            <AlertTriangle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{overview?.unhealthy ?? "-"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm text-muted-foreground">平均延迟</CardTitle>
            <Clock className="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{overview?.avg_latency_ms ?? "-"} ms</div>
            {overview?.last_check && (
              <p className="text-xs text-muted-foreground">
                上次检查: {formatDate(overview.last_check)}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Records table */}
      <Card>
        <CardHeader><CardTitle className="text-base">检查记录</CardTitle></CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无检查记录</p>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-[1fr_80px_80px_1fr_160px] gap-2 border-b pb-2 text-xs font-medium text-muted-foreground">
                <span>书源</span><span>状态</span><span>延迟</span><span>消息</span><span>时间</span>
              </div>
              {records.map((r) => (
                <div key={r.id} className="grid grid-cols-[1fr_80px_80px_1fr_160px] gap-2 py-2 text-sm border-b last:border-0">
                  <span className="truncate">{r.source_name}</span>
                  <span>
                    <Badge variant={r.status === "healthy" ? "success" : "danger"}>
                      {r.status === "healthy" ? "正常" : "异常"}
                    </Badge>
                  </span>
                  <span className="tabular-nums">{r.latency_ms ?? "-"} ms</span>
                  <span className="truncate text-muted-foreground">{r.message}</span>
                  <span className="text-xs text-muted-foreground">{formatDate(r.checked_at)}</span>
                </div>
              ))}
            </div>
          )}
          {total > 20 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                上一页
              </Button>
              <span className="text-sm text-muted-foreground">第 {page} 页</span>
              <Button variant="outline" size="sm" disabled={page * 20 >= total} onClick={() => setPage((p) => p + 1)}>
                下一页
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
