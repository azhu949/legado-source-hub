/** 书源列表页。 */

import { useEffect, useState, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { SourceTable } from "@/components/sources/SourceTable"
import { EmptyState } from "@/components/common/EmptyState"
import { getLatestHealthRecords } from "@/api/health"
import { getSources } from "@/api/sources"
import { useSourceStore } from "@/stores/sourceStore"
import type { HealthRecord } from "@/types/health"
import type { BookSource } from "@/types/source"
import { Plus, Upload, Search as SearchIcon } from "lucide-react"

export default function SourceListPage() {
  const navigate = useNavigate()
  const { sources, totalCount, isLoading, filters, setSources, setLoading, setFilters } = useSourceStore()
  const [healthBySource, setHealthBySource] = useState<Record<string, HealthRecord>>({})

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [res, healthRes] = await Promise.all([
        getSources({
          search: filters.search || undefined,
          status: filters.status || undefined,
          page: filters.page,
          pageSize: filters.pageSize,
        }),
        getLatestHealthRecords(),
      ])
      if (res.success && res.data) {
        setSources(res.data.items as BookSource[], res.data.total)
      }
      if (healthRes.success && healthRes.data) {
        setHealthBySource(
          Object.fromEntries(healthRes.data.map((record) => [record.source_id, record])),
        )
      }
    } catch {
      // ignore
    }
  }, [filters, setSources, setLoading])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">书源管理</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate("/admin/sources/import")}>
            <Upload className="mr-2 h-4 w-4" />
            批量导入
          </Button>
          <Button onClick={() => navigate("/admin/sources/new")}>
            <Plus className="mr-2 h-4 w-4" />
            新增书源
          </Button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索书源名称或URL..."
            className="pl-9"
            value={filters.search}
            onChange={(e) => {
              setFilters({ search: e.target.value, page: 1 })
            }}
          />
        </div>
        <Select
          value={filters.status || "all"}
          onValueChange={(v) => setFilters({ status: v === "all" ? "" : v, page: 1 })}
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="状态筛选" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="enabled">启用</SelectItem>
            <SelectItem value="disabled">禁用</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="py-16 text-center text-muted-foreground">加载中...</div>
      ) : sources.length === 0 ? (
        <EmptyState
          title="暂无书源"
          description="点击上方「新增书源」按钮添加第一个书源"
        />
      ) : (
        <SourceTable data={sources} healthBySource={healthBySource} onRefresh={fetchData} />
      )}
    </div>
  )
}
