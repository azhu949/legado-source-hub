/** 批量导入页。 */

import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { importSources, importFromUrl } from "@/api/sources"
import type { ImportResult, ConflictStrategy } from "@/types/source"
import { Upload, Link as LinkIcon, ClipboardPaste } from "lucide-react"
import { toast } from "sonner"

export default function SourceImportPage() {
  const navigate = useNavigate()
  const [jsonText, setJsonText] = useState("")
  const [remoteUrl, setRemoteUrl] = useState("")
  const [strategy, setStrategy] = useState<ConflictStrategy>("skip")
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)

  const handleImport = async (sources: Record<string, unknown>[]) => {
    if (sources.length === 0) {
      toast.error("未找到可导入的书源数据")
      return
    }
    setImporting(true)
    try {
      const res = await importSources(sources, strategy)
      if (res.success && res.data) {
        setResult(res.data)
        toast.success("导入完成")
      }
    } catch {
      toast.error("导入失败")
    } finally {
      setImporting(false)
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string)
        const arr = Array.isArray(data) ? data : [data]
        handleImport(arr)
      } catch {
        toast.error("文件解析失败，请确认是有效的 JSON")
      }
    }
    reader.readAsText(file)
  }

  const handleTextImport = () => {
    try {
      const data = JSON.parse(jsonText)
      const arr = Array.isArray(data) ? data : [data]
      handleImport(arr)
    } catch {
      toast.error("JSON 格式无效")
    }
  }

  const handleUrlImport = async () => {
    if (!remoteUrl.trim()) {
      toast.error("请输入URL")
      return
    }
    setImporting(true)
    try {
      const res = await importFromUrl(remoteUrl.trim(), strategy)
      if (res.success && res.data) {
        setResult(res.data)
        toast.success("导入完成")
      }
    } catch {
      toast.error("远程导入失败")
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">批量导入书源</h1>
        <Button variant="outline" onClick={() => navigate("/admin/sources")}>
          返回列表
        </Button>
      </div>

      {/* 冲突策略 */}
      <div className="flex items-center gap-3">
        <Label className="shrink-0">冲突策略</Label>
        <Select value={strategy} onValueChange={(v) => setStrategy(v as ConflictStrategy)}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="skip">跳过同名</SelectItem>
            <SelectItem value="overwrite">覆盖同名</SelectItem>
            <SelectItem value="new">始终新建</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Tabs defaultValue="paste">
        <TabsList>
          <TabsTrigger value="paste"><ClipboardPaste className="mr-2 h-4 w-4" />粘贴JSON</TabsTrigger>
          <TabsTrigger value="file"><Upload className="mr-2 h-4 w-4" />上传文件</TabsTrigger>
          <TabsTrigger value="url"><LinkIcon className="mr-2 h-4 w-4" />从URL导入</TabsTrigger>
        </TabsList>

        <TabsContent value="paste">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <Textarea
                placeholder='粘贴 Legado 书源 JSON（支持单个或数组格式）'
                className="min-h-[200px] font-mono text-sm"
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
              />
              <Button onClick={handleTextImport} disabled={importing || !jsonText.trim()}>
                {importing ? "导入中..." : "开始导入"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="file">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <Input type="file" accept=".json" onChange={handleFileUpload} disabled={importing} />
                <span className="text-sm text-muted-foreground">支持 .json 文件（单个或数组）</span>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="url">
          <Card>
            <CardContent className="pt-6 space-y-4">
              <Input
                placeholder="https://example.com/sources.json"
                value={remoteUrl}
                onChange={(e) => setRemoteUrl(e.target.value)}
              />
              <Button onClick={handleUrlImport} disabled={importing || !remoteUrl.trim()}>
                {importing ? "导入中..." : "从URL导入"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* 导入结果 */}
      {result && (
        <Card>
          <CardHeader><CardTitle className="text-base">导入结果</CardTitle></CardHeader>
          <CardContent>
            <div className="flex gap-6 text-sm">
              <span className="text-green-600 font-medium">成功: {result.success}</span>
              <span className="text-amber-600 font-medium">跳过: {result.skipped}</span>
              <span className="text-red-600 font-medium">失败: {result.failed}</span>
            </div>
            {result.errors.length > 0 && (
              <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                {result.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
   )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
