/** 聚合书源导出页。 */

import { useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { copyText, getAggregateSourceUrl } from "@/lib/aggregateSource"
import { CheckCircle2, Copy, ExternalLink, FileJson, QrCode, RefreshCw } from "lucide-react"
import { QRCodeSVG } from "qrcode.react"
import { toast } from "sonner"

type LoadStatus = "loading" | "ready" | "error"

export default function AggregateSourcePage() {
  const aggregateSourceUrl = useMemo(() => getAggregateSourceUrl(), [])
  const [jsonText, setJsonText] = useState("")
  const [status, setStatus] = useState<LoadStatus>("loading")
  const [qrOpen, setQrOpen] = useState(false)

  const loadAggregateSource = async () => {
    setStatus("loading")
    try {
      const response = await fetch("/api/aggregate_source.json", { cache: "no-store" })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setJsonText(JSON.stringify(data, null, 2))
      setStatus("ready")
    } catch {
      setJsonText("")
      setStatus("error")
      toast.error("加载聚合书源 JSON 失败")
    }
  }

  useEffect(() => {
    void loadAggregateSource()
  }, [])

  const handleCopyUrl = async () => {
    try {
      await copyText(aggregateSourceUrl)
      toast.success("聚合书源地址已复制")
    } catch {
      toast.error("复制失败，请手动复制地址")
    }
  }

  const handleCopyJson = async () => {
    try {
      await copyText(jsonText)
      toast.success("聚合书源 JSON 已复制")
    } catch {
      toast.error("复制失败，请手动复制 JSON")
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">聚合书源</h1>
          <p className="mt-1 text-sm text-muted-foreground">阅读 APP 可直接导入的书源地址与 JSON</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadAggregateSource} disabled={status === "loading"}>
          <RefreshCw className={`h-4 w-4 ${status === "loading" ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <FileJson className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-base">导入地址</CardTitle>
              <p className="text-sm text-muted-foreground">当前前端访问域名生成</p>
            </div>
          </div>
          <Badge variant="outline" className="w-fit">Legado JSON</Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md border bg-muted/40 px-3 py-2 font-mono text-sm break-all">
            {aggregateSourceUrl}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={handleCopyUrl}>
              <Copy className="h-4 w-4" />
              复制地址
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(aggregateSourceUrl, "_blank", "noopener,noreferrer")}
            >
              <ExternalLink className="h-4 w-4" />
              打开 JSON
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopyJson}
              disabled={status !== "ready" || !jsonText}
            >
              <Copy className="h-4 w-4" />
              复制 JSON
            </Button>
            <Button variant="outline" size="sm" onClick={() => setQrOpen(true)}>
              <QrCode className="h-4 w-4" />
              打开二维码
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">生成结果</CardTitle>
            <p className="text-sm text-muted-foreground">后端实时返回的聚合书源 JSON</p>
          </div>
          {status === "ready" && (
            <Badge variant="success" className="w-fit">
              <CheckCircle2 className="mr-1 h-3 w-3" />
              已加载
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {status === "error" ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-6 text-sm text-destructive">
              无法加载聚合书源 JSON，请检查后端容器和 `/api/aggregate_source.json` 是否可访问。
            </div>
          ) : (
            <Textarea
              readOnly
              value={status === "loading" ? "加载中..." : jsonText}
              className="min-h-[420px] resize-y bg-muted/20 font-mono text-xs leading-relaxed"
            />
          )}
        </CardContent>
      </Card>

      <Dialog open={qrOpen} onOpenChange={setQrOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>聚合书源二维码</DialogTitle>
            <DialogDescription>使用阅读 APP 扫描后导入当前聚合书源地址</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col items-center gap-4">
            <div className="rounded-md border bg-white p-4 shadow-sm">
              <QRCodeSVG value={aggregateSourceUrl} size={240} level="M" includeMargin />
            </div>
            <div className="w-full rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs break-all">
              {aggregateSourceUrl}
            </div>
            <Button size="sm" onClick={handleCopyUrl} className="w-full sm:w-auto">
              <Copy className="h-4 w-4" />
              复制地址
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
