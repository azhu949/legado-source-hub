/** 书源列表表格。 */

import { useState, useCallback } from "react"
import { useNavigate } from "react-router-dom"
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table"
import { Pencil, Trash2, FlaskConical, ArrowUpDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { SourceStatusBadge } from "./SourceStatusBadge"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import type { BookSource } from "@/types/source"
import { toggleSource, deleteSource } from "@/api/sources"
import { toast } from "sonner"

interface SourceTableProps {
  data: BookSource[]
  onRefresh: () => void
}

export function SourceTable({ data, onRefresh }: SourceTableProps) {
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([])
  const [deleteTarget, setDeleteTarget] = useState<BookSource | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)

  const handleToggle = useCallback(async (id: string, enabled: boolean) => {
    setTogglingId(id)
    try {
      await toggleSource(id, !enabled)
      toast.success(enabled ? "已禁用书源" : "已启用书源")
      onRefresh()
    } catch {
      toast.error("操作失败")
    } finally {
      setTogglingId(null)
    }
  }, [onRefresh])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteSource(deleteTarget.id)
      toast.success("书源已删除")
      onRefresh()
    } catch {
      toast.error("删除失败")
    }
    setDeleteTarget(null)
  }, [deleteTarget, onRefresh])

  const columns: ColumnDef<BookSource>[] = [
    {
      accessorKey: "bookSourceName",
      header: ({ column }) => (
        <Button variant="ghost" size="sm" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}>
          名称 <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => (
        <div className="font-medium">{row.original.bookSourceName}</div>
      ),
    },
    {
      accessorKey: "bookSourceUrl",
      header: "URL",
      cell: ({ row }) => (
        <div className="max-w-[200px] truncate text-xs text-muted-foreground" title={row.original.bookSourceUrl}>
          {row.original.bookSourceUrl}
        </div>
      ),
    },
    {
      accessorKey: "weight",
      header: ({ column }) => (
        <Button variant="ghost" size="sm" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}>
          权重 <ArrowUpDown className="ml-1 h-3 w-3" />
        </Button>
      ),
      cell: ({ row }) => <span className="tabular-nums">{row.original.weight}</span>,
    },
    {
      accessorKey: "enabled",
      header: "状态",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <Switch
            checked={row.original.enabled}
            onCheckedChange={() => handleToggle(row.original.id, row.original.enabled)}
            disabled={togglingId === row.original.id}
          />
          <SourceStatusBadge enabled={row.original.enabled} />
        </div>
      ),
    },
    {
      accessorKey: "bookSourceGroup",
      header: "分组",
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{row.original.bookSourceGroup}</span>,
    },
    {
      id: "actions",
      header: "操作",
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate(`/admin/sources/${row.original.id}/edit`)}
            title="编辑"
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() =>
              navigate(`/admin/rules/test?sourceId=${row.original.id}`)
            }
            title="测试"
          >
            <FlaskConical className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDeleteTarget(row.original)}
            title="删除"
          >
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      ),
    },
  ]

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  })

  return (
    <>
      <div className="rounded-md border">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b bg-muted/50">
                {hg.headers.map((header) => (
                  <th key={header.id} className="h-10 px-4 text-left text-sm font-medium text-muted-foreground">
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
       </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b transition-colors hover:bg-muted/50">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-3 text-sm">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between py-4">
        <div className="text-sm text-muted-foreground">
          共 {data.length} 条
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            第 {table.getState().pagination.pageIndex + 1} / {table.getPageCount()} 页
          </span>
          <Button variant="outline" size="sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
            下一页
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title="确认删除"
        description={`确定要删除书源「${deleteTarget?.bookSourceName}」吗？此操作不可撤销。`}
        confirmLabel="删除"
        variant="destructive"
        onConfirm={handleDelete}
      />
    </>
  )
}
