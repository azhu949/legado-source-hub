/** 规则测试页。 */

import { useState, useEffect, useCallback } from "react"
import { useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { testRule, type RuleTestResult } from "@/api/rules"
import { getSource, getSources } from "@/api/sources"
import type { BookSource } from "@/types/source"
import { Send, Code, Table2, Info } from "lucide-react"
import { toast } from "sonner"

const DEFAULT_TEST_KEYWORD = "斗破苍穹"

function getSourceRules(source: BookSource) {
  return {
    ruleSearch: source.ruleSearch,
    ruleBookInfo: source.ruleBookInfo,
    ruleToc: source.ruleToc,
    ruleContent: source.ruleContent,
  }
}

function resolveTestUrl(url: string, baseUrl: string) {
  if (!url) return baseUrl

  try {
    return new URL(url).toString()
  } catch {
    // relative URLs need the source base URL; fall back to the raw template result if base is invalid.
  }

  try {
    return new URL(url, baseUrl).toString()
  } catch {
    if (!baseUrl) return url
    return `${baseUrl.replace(/\/+$/, "")}/${url.replace(/^\/+/, "")}`
  }
}

function buildSourceTestUrl(source: BookSource) {
  const searchTemplate = source.searchUrl?.trim()
  if (!searchTemplate) return source.bookSourceUrl
  if (searchTemplate.startsWith("@js:")) return ""

  const encodedKeyword = encodeURIComponent(DEFAULT_TEST_KEYWORD)
  const url = searchTemplate
    .replace(/\{\{\s*(?:java\.)?encodeURIComponent\(key\)\s*\}\}/g, encodedKeyword)
    .replace(/\{\{\s*(?:java\.)?encodeURI\(key\)\s*\}\}/g, encodeURI(DEFAULT_TEST_KEYWORD))
    .replace(/\{\{key\}\}/g, DEFAULT_TEST_KEYWORD)
    .replace(/\{key\}/g, DEFAULT_TEST_KEYWORD)
    .replace(/\{\{page\}\}/g, "1")
    .replace(/\{page\}/g, "1")

  return resolveTestUrl(url, source.bookSourceUrl)
}

export default function RuleTestPage() {
  const [searchParams] = useSearchParams()
  const preSourceId = searchParams.get("sourceId")

  const [sources, setSources] = useState<BookSource[]>([])
  const [selectedSourceId, setSelectedSourceId] = useState(preSourceId || "")
  const [testUrl, setTestUrl] = useState("")
  const [rules, setRules] = useState("{}")
  const [isJson, setIsJson] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<RuleTestResult | null>(null)
  const [activeTab, setActiveTab] = useState("raw")

  const fillFromSource = useCallback((source: BookSource) => {
    setSelectedSourceId(source.id)
    setTestUrl(buildSourceTestUrl(source))
    setRules(JSON.stringify(getSourceRules(source), null, 2))
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadSources() {
      try {
        const res = await getSources({ pageSize: 100 })
        const loadedSources = res.success && res.data ? (res.data.items as BookSource[]) : []

        if (!cancelled) {
          setSources(loadedSources)
        }

        if (!preSourceId) {
          if (!cancelled) setSelectedSourceId("")
          return
        }

        const sourceFromList = loadedSources.find((source) => source.id === preSourceId)
        if (sourceFromList) {
          if (!cancelled) fillFromSource(sourceFromList)
          return
        }

        const detailRes = await getSource(preSourceId)
        if (cancelled || !detailRes.success || !detailRes.data) return

        const source = detailRes.data as BookSource
        setSources((current) =>
          current.some((item) => item.id === source.id) ? current : [source, ...current],
        )
        fillFromSource(source)
      } catch {
        if (!cancelled) toast.error("加载书源失败，无法自动预填测试信息")
      }
    }

    loadSources()

    return () => {
      cancelled = true
    }
  }, [preSourceId, fillFromSource])

  const handleTest = async () => {
    if (!testUrl.trim() && !selectedSourceId) {
 toast.error("请输入测试URL")
      return
    }
    setLoading(true)
    try {
      let parsedRules = {}
      try {
        parsedRules = JSON.parse(rules)
      } catch {
        toast.error("规则 JSON 格式无效")
        setLoading(false)
        return
      }
      const res = await testRule({
        testUrl: testUrl.trim() || undefined,
        rules: parsedRules,
        isJson,
        sourceId: selectedSourceId || undefined,
      })
      if (res.success && res.data) {
        setResult(res.data)
        setIsJson(res.data.isJson)
        toast.success("规则测试完成")
      } else {
        toast.error(res.error?.message || "测试失败")
      }
    } catch {
      toast.error("请求失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">规则测试</h1>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 左栏 - 配置区 */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">测试配置</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>测试URL</Label>
                <Input
                  placeholder={selectedSourceId ? "选中书源时可留空" : "https://example.com/search?q=斗破苍穹"}
                  value={testUrl}
                  onChange={(e) => setTestUrl(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label>选择书源（可选，自动填充规则）</Label>
                <Select
                  value={selectedSourceId}
                  onValueChange={(v) => {
                    setSelectedSourceId(v)
                    const src = sources.find((s) => s.id === v)
                    if (src) {
                      fillFromSource(src)
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="手动填写规则" />
                  </SelectTrigger>
                  <SelectContent>
                    {sources.map((src) => (
                      <SelectItem key={src.id} value={src.id}>
                        {src.bookSourceName}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>规则定义 (JSON)</Label>
                <Textarea
                  className="min-h-[300px] font-mono text-xs"
                  value={rules}
                  onChange={(e) => setRules(e.target.value)}
                  placeholder='{"ruleSearch": {"bookList": "...", "name": "..."}}'
                />
              </div>

              <div className="flex items-center gap-4">
                <Button onClick={handleTest} disabled={loading}>
                  <Send className="mr-2 h-4 w-4" />
                  {loading ? "测试中..." : "发起测试"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 右栏 - 结果区 */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">测试结果</CardTitle></CardHeader>
            <CardContent>
              {!result ? (
                <p className="text-sm text-muted-foreground">点击「发起测试」查看结果</p>
              ) : (
                <Tabs value={activeTab} onValueChange={setActiveTab}>
                  <TabsList>
                    <TabsTrigger value="raw"><Code className="mr-1 h-3 w-3" />原始响应</TabsTrigger>
                    <TabsTrigger value="extracted"><Table2 className="mr-1 h-3 w-3" />提取结果</TabsTrigger>
                    <TabsTrigger value="http"><Info className="mr-1 h-3 w-3" />HTTP信息</TabsTrigger>
                  </TabsList>

                  <TabsContent value="raw">
                    <pre className="max-h-[500px] overflow-auto rounded-md bg-muted p-3 text-xs">
                      {result.raw?.substring(0, 20000) || "(空)"}
                    </pre>
                  </TabsContent>

                  <TabsContent value="extracted">
                    <pre className="max-h-[500px] overflow-auto rounded-md bg-muted p-3 text-xs">
                      {JSON.stringify(result.extracted, null, 2)}
                    </pre>
          </TabsContent>

                  <TabsContent value="http">
                    <div className="space-y-2 text-sm">
                      <div><strong>状态码:</strong> {result.http?.status}</div>
                      <div><strong>耗时:</strong> {result.http?.elapsed_ms} ms</div>
                      <div><strong>最终URL:</strong> {result.http?.url}</div>
                      <div><strong>内容类型:</strong> {result.isJson ? "JSON" : "HTML/Text"}</div>
                      {result.http?.headers && (
                        <div>
                          <strong>响应头:</strong>
                          <pre className="mt-1 rounded bg-muted p-2 text-xs">
                            {JSON.stringify(result.http.headers, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  </TabsContent>
                </Tabs>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
