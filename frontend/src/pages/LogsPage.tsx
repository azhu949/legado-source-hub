/** 操作日志页。 */

import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { getLogs, getLogExportUrl, type LogEntry } from "@/api/logs"
import { Badge } from "@/components/ui/badge"
import { formatDate } from "@/lib/utils"
import { Download } from "lucide-react"

const opTypes = [
  { value: "all", label: "全部类型" },
  { value: "create", label: "新增" },
  { value: "update", label: "编辑" },
  { value: "delete", label: "删除" },
  { value: "import", label: "导入" },
  { value: "toggle", label: "启禁用" },
]

const opTypeColors: Record<string, string> = {
  create: "success",
  update: "default",
  delete: "danger",
  import: "warning",
  toggle: "secondary",
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [type, setType] = useState("all")
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")

  const fetchData = useCallback(async () => {
    try {
      const res = await getLogs({
        type: type === "all" ? undefined : type,
        start: start || undefined,
        end: end || undefined,
        page,
        pageSize: 20,
      })
      if (res.success && res.data) {
        setLogs(res.data.items as LogEntry[])
        setTotal(res.data.total)
      }
    } catch {
      // ignore
    }
  }, [type, start, end, page])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">操作日志</h1>
        <Button variant="outline" size="sm" asChild>
          <a href={getLogExportUrl()} download>
            <Download className="mr-2 h-4 w-4" />
            导出 CSV
          </a>
        </Button>
      </div>

      {/* 筛选 */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={type} onValueChange={(v) => { setType(v); setPage(1); }}>
          <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            {opTypes.map((t) => (
              <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input type="date" className="w-40" value={start} onChange={(e) => { setStart(e.target.value); setPage(1); }} placeholder="开始日期" />
        <Input type="date" className="w-40" value={end} onChange={(e) => { setEnd(e.target.value); setPage(1); }} placeholder="结束日期" />
      </div>

      {/* 表格 */}
      <Card>
        <CardContent className="pt-6">
          {logs.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">暂无日志记录</p>
          ) : (
            <>
              <div className="space-y-2">
                <div className="grid grid-cols-[160px_80px_1fr_1fr_120px_100px] gap-2 border-b pb-2 text-xs font-medium text-muted-foreground">
                  <span>时间</span><span>操作类型</span><span>目标书源</span><span>详情</span><span>IP</span><span>操作人</span>
                </div>
                {logs.map((log) => (
                  <div key={log.id} className="grid grid-cols-[160px_80px_1fr_1fr_120px_100px] gap-2 py-2 text-sm border-b last:border-0">
                    <span className="text-xs text-muted-foreground">{formatDate(log.timestamp)}</span>
                    <span>
                      <Badge variant={(opTypeColors[log.op_type] as any) || "outline"}>
                        {log.op_type}
                      </Badge>
                    </span>
                    <span className="truncate">{log.target_source || "-"}</span>
                    <span className="truncate text-muted-foreground">{log.detail || "-"}</span>
                    <span className="text-xs text-muted-foreground">{log.ip || "-"}</span>
                    <span className="text-xs">{log.operator}</span>
                  </div>
                ))}
              </div>

              <div className="mt-4 flex items-center justify-between">
                <span className="text-sm text-muted-foreground">共 {total} 条</span>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                    上一页
                  </Button>
                  <span className="text-sm text-muted-foreground">第 {page} 页</span>
                  <Button variant="outline" size="sm" disabled={page * 20 >= total} onClick={() => setPage((p) => p + 1)}>
                    下一页
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
