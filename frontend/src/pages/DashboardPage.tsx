/** 仪表盘首页。 */

import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { getStats, getRecentLogs } from "@/api/logs"
import { triggerHealthCheck } from "@/api/health"
import type { DashboardStats, LogEntry } from "@/api/logs"
import { copyText, getAggregateSourceUrl } from "@/lib/aggregateSource"
import { formatDate } from "@/lib/utils"
import {
  BookOpen,
  Search,
  AlertTriangle,
  Clock,
  RefreshCw,
  Copy,
  ExternalLink,
  FileJson,
  ArrowRight,
} from "lucide-react"
import { toast } from "sonner"

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [checking, setChecking] = useState(false)
  const aggregateSourceUrl = getAggregateSourceUrl()

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [statsRes, logsRes] = await Promise.all([getStats(), getRecentLogs(20)])
      if (statsRes.success && statsRes.data) setStats(statsRes.data)
      if (logsRes.success && logsRes.data) setLogs(logsRes.data as unknown as LogEntry[])
    } catch {
      // 静默处理
    }
  }

  const handleCheckNow = async () => {
    setChecking(true)
    try {
      await triggerHealthCheck()
      toast.success("健康检查已触发")
      setTimeout(loadData, 5000)
    } catch {
      toast.error("触发检查失败")
    } finally {
      setChecking(false)
    }
  }

  const handleCopyAggregateUrl = async () => {
    try {
      await copyText(aggregateSourceUrl)
      toast.success("聚合书源地址已复制")
    } catch {
      toast.error("复制失败，请手动复制地址")
    }
  }

  const statCards = [
    {
      title: "书源总数",
      value: stats ? `${stats.totalSources} / ${stats.enabledSources}` : "-",
      description: `${stats?.disabledSources ?? 0} 个已禁用`,
      icon: BookOpen,
      color: "text-blue-600",
    },
    {
      title: "今日搜索量",
      value: stats?.todaySearchCount ?? 0,
      description: "搜索 API 调用次数",
      icon: Search,
      color: "text-green-600",
    },
    {
      title: "异常书源",
      value: stats?.unhealthySources ?? 0,
      description: "健康检查连续失败",
      icon: AlertTriangle,
      color: "text-red-600",
    },
    {
      title: "平均响应延迟",
      value: stats ? `${stats.avgLatencyMs} ms` : "-",
      description: stats?.lastCheck ? `上次检查: ${formatDate(stats.lastCheck)}` : "",
      icon: Clock,
      color: "text-amber-600",
    },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">仪表盘</h1>
        <Button variant="outline" size="sm" onClick={handleCheckNow} disabled={checking}>
          <RefreshCw className={`mr-2 h-4 w-4 ${checking ? "animate-spin" : ""}`} />
          {checking ? "检查中..." : "立即健康检查"}
        </Button>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <FileJson className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-base">聚合书源</CardTitle>
              <p className="text-sm text-muted-foreground">阅读 APP 导入地址</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={handleCopyAggregateUrl}>
              <Copy className="h-4 w-4" />
              复制
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/admin/aggregate">
                <ArrowRight className="h-4 w-4" />
                详情
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(aggregateSourceUrl, "_blank", "noopener,noreferrer")}
            >
              <ExternalLink className="h-4 w-4" />
              打开 JSON
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border bg-muted/40 px-3 py-2 font-mono text-sm text-foreground break-all">
            {aggregateSourceUrl}
          </div>
        </CardContent>
      </Card>

      {/* Stat cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => (
          <Card key={card.title}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
              <card.icon className={`h-5 w-5 ${card.color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{card.value}</div>
              {card.description && (
                <p className="text-xs text-muted-foreground">{card.description}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent logs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近操作</CardTitle>
        </CardHeader>
        <CardContent>
          {logs.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无操作日志</p>
          ) : (
            <div className="space-y-2">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                >
                  <div className="flex items-center gap-3">
                    <span className="rounded bg-muted px-2 py-0.5 text-xs font-medium">
                      {log.op_type}
                    </span>
                    <span className="text-foreground">
                      {log.target_source || log.detail || "-"}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(log.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
