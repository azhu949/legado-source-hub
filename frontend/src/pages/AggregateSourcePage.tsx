/** 聚合书源与访问用户管理页。 */

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import {
  Copy,
  FileJson,
  KeyRound,
  Link as LinkIcon,
  Pencil,
  Plus,
  QrCode,
  RefreshCw,
  RotateCcw,
  Trash2,
  Users,
} from "lucide-react"
import { QRCodeSVG } from "qrcode.react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { ConfirmDialog } from "@/components/common/ConfirmDialog"
import { EmptyState } from "@/components/common/EmptyState"
import { copyText } from "@/lib/aggregateSource"
import { createUser, deleteUser, getUsers, rotateUserKey, updateUser } from "@/api/users"
import type { AccessUser } from "@/types/user"

type JsonStatus = "idle" | "loading" | "ready" | "error"

function formatDate(value: string | null) {
  if (!value) return "-"
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value)
}

function importUrlFor(user: AccessUser) {
  return `${window.location.origin}/api/aggregate_source.json?accessKey=${encodeURIComponent(user.access_key)}`
}

export default function AggregateSourcePage() {
  const [users, setUsers] = useState<AccessUser[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<AccessUser | null>(null)
  const [form, setForm] = useState({ name: "", note: "" })
  const [deleteTarget, setDeleteTarget] = useState<AccessUser | null>(null)
  const [rotateTarget, setRotateTarget] = useState<AccessUser | null>(null)
  const [jsonTarget, setJsonTarget] = useState<AccessUser | null>(null)
  const [jsonText, setJsonText] = useState("")
  const [jsonStatus, setJsonStatus] = useState<JsonStatus>("idle")
  const [qrTarget, setQrTarget] = useState<AccessUser | null>(null)

  const enabledCount = useMemo(() => users.filter((user) => user.enabled).length, [users])
  const totalRequests = useMemo(() => users.reduce((sum, user) => sum + user.request_count, 0), [users])

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getUsers()
      if (res.success && res.data) {
        setUsers(res.data)
      } else {
        toast.error(res.error?.message || "访问用户加载失败")
      }
    } catch {
      toast.error("访问用户加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadUsers()
  }, [loadUsers])

  const openCreate = () => {
    setEditingUser(null)
    setForm({ name: "", note: "" })
    setDialogOpen(true)
  }

  const openEdit = (user: AccessUser) => {
    setEditingUser(user)
    setForm({ name: user.name, note: user.note || "" })
    setDialogOpen(true)
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("请输入用户名称")
      return
    }
    setSaving(true)
    try {
      const res = editingUser
        ? await updateUser(editingUser.id, { name: form.name.trim(), note: form.note.trim() })
        : await createUser({ name: form.name.trim(), note: form.note.trim() })
      if (res.success && res.data) {
        toast.success(editingUser ? "访问用户已更新" : "访问用户已创建")
        setDialogOpen(false)
        await loadUsers()
      } else {
        toast.error(res.error?.message || "保存失败")
      }
    } catch {
      toast.error("保存失败")
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (user: AccessUser, enabled: boolean) => {
    try {
      const res = await updateUser(user.id, { enabled })
      if (res.success && res.data) {
        setUsers((current) => current.map((item) => (item.id === user.id ? res.data! : item)))
        toast.success(enabled ? "访问用户已启用" : "访问用户已禁用")
      } else {
        toast.error(res.error?.message || "状态更新失败")
      }
    } catch {
      toast.error("状态更新失败")
    }
  }

  const handleRotate = async () => {
    if (!rotateTarget) return
    try {
      const res = await rotateUserKey(rotateTarget.id)
      if (res.success && res.data) {
        setUsers((current) => current.map((item) => (item.id === rotateTarget.id ? res.data! : item)))
        toast.success("访问口令已重置")
      } else {
        toast.error(res.error?.message || "重置失败")
      }
    } catch {
      toast.error("重置失败")
    } finally {
      setRotateTarget(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      const res = await deleteUser(deleteTarget.id)
      if (res.success) {
        setUsers((current) => current.filter((item) => item.id !== deleteTarget.id))
        toast.success("访问用户已删除")
      } else {
        toast.error(res.error?.message || "删除失败")
      }
    } catch {
      toast.error("删除失败")
    } finally {
      setDeleteTarget(null)
    }
  }

  const handleCopy = async (value: string, message: string) => {
    try {
      await copyText(value)
      toast.success(message)
    } catch {
      toast.error("复制失败")
    }
  }

  const openJson = async (user: AccessUser) => {
    setJsonTarget(user)
    setJsonText("")
    setJsonStatus("loading")
    try {
      const response = await fetch(importUrlFor(user), { cache: "no-store" })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setJsonText(JSON.stringify(data, null, 2))
      setJsonStatus("ready")
    } catch {
      setJsonStatus("error")
      toast.error("聚合书源 JSON 加载失败")
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">聚合书源</h1>
          <p className="mt-1 text-sm text-muted-foreground">先创建访问用户，再复制该用户专属导入地址</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={loadUsers} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4" />
            新增用户
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">访问用户</CardTitle>
            <Users className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatNumber(users.length)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">启用中</CardTitle>
            <KeyRound className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatNumber(enabledCount)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">总请求</CardTitle>
            <LinkIcon className="h-5 w-5 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatNumber(totalRequests)}</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">访问用户与导入地址</CardTitle>
            <p className="text-sm text-muted-foreground">每个用户都有独立口令；禁用、删除或重置后，旧地址立即失效。</p>
          </div>
          <Badge variant="outline" className="w-fit">{enabledCount > 0 ? "可用用户" : "无启用用户"}</Badge>
        </CardHeader>
        <CardContent>
          {users.length === 0 && !loading ? (
            <EmptyState
              icon={<FileJson className="h-12 w-12" />}
              title="先创建一个访问用户"
              description="创建后即可复制阅读 APP 导入地址，也可以查看该用户对应的聚合书源 JSON。"
              action={
                <Button size="sm" onClick={openCreate}>
                  <Plus className="h-4 w-4" />
                  新增用户
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1020px] text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="h-10 px-3 font-medium">用户</th>
                    <th className="h-10 px-3 font-medium">导入地址</th>
                    <th className="h-10 px-3 font-medium">状态</th>
                    <th className="h-10 px-3 font-medium">请求数</th>
                    <th className="h-10 px-3 font-medium">最后使用</th>
                    <th className="h-10 px-3 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => {
                    const importUrl = importUrlFor(user)
                    return (
                      <tr key={user.id} className="border-b last:border-0">
                        <td className="px-3 py-3">
                          <div className="font-medium">{user.name}</div>
                          {user.note && <div className="mt-1 max-w-[220px] truncate text-xs text-muted-foreground">{user.note}</div>}
                        </td>
                        <td className="px-3 py-3">
                          <div className="max-w-[380px] truncate rounded-md border bg-muted/40 px-2 py-1 font-mono text-xs">
                            {importUrl}
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-2">
                            <Switch checked={user.enabled} onCheckedChange={(enabled) => handleToggle(user, enabled)} />
                            <span className="text-xs text-muted-foreground">{user.enabled ? "启用" : "禁用"}</span>
                          </div>
                        </td>
                        <td className="px-3 py-3">{formatNumber(user.request_count)}</td>
                        <td className="px-3 py-3 text-muted-foreground">{formatDate(user.last_used_at)}</td>
                        <td className="px-3 py-3">
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" size="icon" title="复制导入地址" onClick={() => handleCopy(importUrl, "导入地址已复制")}>
                              <LinkIcon className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" title="查看 JSON" onClick={() => openJson(user)}>
                              <FileJson className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" title="二维码" onClick={() => setQrTarget(user)}>
                              <QrCode className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" title="复制访问口令" onClick={() => handleCopy(user.access_key, "访问口令已复制")}>
                              <Copy className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" title="编辑" onClick={() => openEdit(user)}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" title="重置访问口令" onClick={() => setRotateTarget(user)}>
                              <RotateCcw className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="icon" title="删除" onClick={() => setDeleteTarget(user)}>
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingUser ? "编辑访问用户" : "新增访问用户"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="user-name">用户名称</Label>
              <Input
                id="user-name"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="如：我的手机"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="user-note">备注</Label>
              <Textarea
                id="user-note"
                value={form.note}
                onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
                placeholder="可填写设备、用途或到期说明"
                className="min-h-24"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
              取消
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "保存中..." : "保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(jsonTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setJsonTarget(null)
            setJsonStatus("idle")
            setJsonText("")
          }
        }}
      >
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>聚合书源 JSON</DialogTitle>
            <DialogDescription>{jsonTarget ? `用户：${jsonTarget.name}` : ""}</DialogDescription>
          </DialogHeader>
          {jsonStatus === "error" ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-6 text-sm text-destructive">
              无法加载聚合书源 JSON，请检查该用户是否启用。
            </div>
          ) : (
            <Textarea
              readOnly
              value={jsonStatus === "loading" ? "加载中..." : jsonText}
              className="min-h-[480px] resize-y bg-muted/20 font-mono text-xs leading-relaxed"
            />
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => jsonTarget && handleCopy(importUrlFor(jsonTarget), "导入地址已复制")}
              disabled={!jsonTarget}
            >
              <LinkIcon className="h-4 w-4" />
              复制地址
            </Button>
            <Button onClick={() => handleCopy(jsonText, "聚合书源 JSON 已复制")} disabled={jsonStatus !== "ready" || !jsonText}>
              <Copy className="h-4 w-4" />
              复制 JSON
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(qrTarget)}
        onOpenChange={(open) => {
          if (!open) setQrTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>聚合书源二维码</DialogTitle>
            <DialogDescription>{qrTarget ? `用户：${qrTarget.name}` : ""}</DialogDescription>
          </DialogHeader>
          {qrTarget && (
            <div className="flex flex-col items-center gap-4">
              <div className="rounded-md border bg-white p-4 shadow-sm">
                <QRCodeSVG value={importUrlFor(qrTarget)} size={240} level="M" includeMargin />
              </div>
              <div className="w-full rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs break-all">
                {importUrlFor(qrTarget)}
              </div>
              <Button size="sm" onClick={() => handleCopy(importUrlFor(qrTarget), "导入地址已复制")} className="w-full sm:w-auto">
                <Copy className="h-4 w-4" />
                复制地址
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(rotateTarget)}
        onOpenChange={(open) => {
          if (!open) setRotateTarget(null)
        }}
        title="重置访问口令"
        description={`将为「${rotateTarget?.name || ""}」生成新的访问口令，旧导入地址会立即失效。`}
        confirmLabel="重置"
        onConfirm={handleRotate}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title="删除访问用户"
        description={`确定删除「${deleteTarget?.name || ""}」吗？对应导入地址会立即失效。`}
        confirmLabel="删除"
        variant="destructive"
        onConfirm={handleDelete}
      />
    </div>
  )
}
