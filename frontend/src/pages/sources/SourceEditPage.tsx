/** 书源编辑页（新增/编辑共用）。 */

import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useForm, Controller, type UseFormRegister } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getSource, createSource, updateSource } from "@/api/sources"
import type { BookSource, BookSourceCreateInput } from "@/types/source"
import { toast } from "sonner"
import { Save, FlaskConical, ArrowLeft, FileText, Code2, Wand2 } from "lucide-react"

const sourceSchema = z.object({
  bookSourceName: z.string().min(1, "名称不能为空").max(50),
  bookSourceGroup: z.string().max(50).default("未分组"),
  bookSourceUrl: z.string().min(1, "URL不能为空"),
  enabled: z.boolean().default(true),
  weight: z.number().min(0).max(9999).default(100),
  searchUrl: z.string().default(""),
  ruleSearch: z.object({
    bookList: z.string().default(""),
    name: z.string().default(""),
    author: z.string().default(""),
    kind: z.string().default(""),
    lastChapter: z.string().default(""),
    intro: z.string().default(""),
    coverUrl: z.string().default(""),
    noteUrl: z.string().default(""),
    wordCount: z.string().default(""),
  }).passthrough().default({}),
  ruleBookInfo: z.object({
    name: z.string().default(""),
    author: z.string().default(""),
    intro: z.string().default(""),
    coverUrl: z.string().default(""),
    tocUrl: z.string().default(""),
  }).passthrough().default({}),
  ruleToc: z.object({
    chapterList: z.string().default(""),
    chapterName: z.string().default(""),
    chapterUrl: z.string().default(""),
  }).passthrough().default({}),
  ruleContent: z.object({
    content: z.string().default(""),
  }).passthrough().default({}),
  headers: z.any().nullable().default(null),
}).passthrough()

type SourceFormData = z.infer<typeof sourceSchema>

/** JSON 模式的空白模板。 */
const EMPTY_TEMPLATE: BookSourceCreateInput = {
  bookSourceName: "",
  bookSourceGroup: "未分组",
  bookSourceUrl: "",
  enabled: true,
  weight: 100,
  searchUrl: "",
  ruleSearch: { bookList: "", name: "", author: "", kind: "", lastChapter: "", intro: "", coverUrl: "", noteUrl: "" },
  ruleBookInfo: { name: "", author: "", intro: "", coverUrl: "", tocUrl: "" },
  ruleToc: { chapterList: "", chapterName: "", chapterUrl: "" },
  ruleContent: { content: "" },
  headers: null,
}

/** 提到组件外部，避免每次渲染重建导致输入框失焦。 */
type RuleInputProps = {
  label: string
  name: string
  placeholder?: string
  register: UseFormRegister<SourceFormData>
}

const RuleInput = ({ label, name, placeholder, register }: RuleInputProps) => (
  <div className="grid grid-cols-[80px_1fr] items-center gap-2">
    <Label className="text-xs text-muted-foreground">{label}</Label>
    <Input
      {...register(name as any)}
      placeholder={placeholder}
      className="h-8 text-sm"
    />
  </div>
)

export default function SourceEditPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const isEdit = !!id && id !== "new"
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<"form" | "json">("form")
  const [jsonText, setJsonText] = useState("")

  const form = useForm<SourceFormData>({
    resolver: zodResolver(sourceSchema),
    defaultValues: {
      bookSourceName: "",
      bookSourceGroup: "未分组",
      bookSourceUrl: "",
      enabled: true,
      weight: 100,
      searchUrl: "",
      ruleSearch: { bookList: "", name: "", author: "", kind: "", lastChapter: "", intro: "", coverUrl: "", noteUrl: "" },
      ruleBookInfo: { name: "", author: "", intro: "", coverUrl: "", tocUrl: "" },
      ruleToc: { chapterList: "", chapterName: "", chapterUrl: "" },
      ruleContent: { content: "" },
      headers: null,
    },
  })

  useEffect(() => {
    if (isEdit && id) {
      getSource(id).then((res) => {
        if (res.success && res.data) {
          form.reset(res.data as SourceFormData)
          setJsonText(JSON.stringify(res.data, null, 2))
        }
      })
    } else {
      // 新增模式预填模板，方便直接粘贴覆盖
      setJsonText(JSON.stringify(EMPTY_TEMPLATE, null, 2))
    }
  }, [id, isEdit])

  /** 统一保存逻辑：表单模式 / JSON 模式共用。 */
  const handleSave = async (testAfter = false) => {
    let data: BookSourceCreateInput

    if (activeTab === "json") {
      // JSON 模式：解析并做基本校验
      let parsed: unknown
      try {
        parsed = JSON.parse(jsonText)
      } catch {
        toast.error("JSON 格式无效，请检查语法")
        return
      }
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        toast.error("JSON 必须是一个对象（单个书源）")
        return
      }
      data = parsed as BookSourceCreateInput
      if (!data.bookSourceName || !data.bookSourceUrl) {
        toast.error("JSON 缺少必填字段：bookSourceName / bookSourceUrl")
        return
      }
    } else {
      // 表单模式：触发校验
      const valid = await form.trigger()
      if (!valid) return
      data = form.getValues()
    }

    setLoading(true)
    try {
      if (isEdit && id) {
        await updateSource(id, data)
        toast.success("书源更新成功")
        if (testAfter) {
          navigate(`/admin/rules/test?sourceId=${id}`)
          return
        }
      } else {
        const res = await createSource(data)
        toast.success("书源创建成功")
        if (testAfter && res.success && res.data) {
          navigate(`/admin/rules/test?sourceId=${(res.data as BookSource).id}`)
          return
        }
      }
      navigate("/admin/sources")
    } catch {
      toast.error("保存失败")
    } finally {
      setLoading(false)
    }
  }

  /** 格式化 JSON 文本。 */
  const formatJson = () => {
    try {
      const parsed = JSON.parse(jsonText)
      setJsonText(JSON.stringify(parsed, null, 2))
      toast.success("JSON 已格式化")
    } catch {
      toast.error("JSON 格式无效，无法格式化")
    }
  }

  /** 将当前表单数据同步到 JSON 文本（方便从表单切到 JSON 查看）。 */
  const syncFormToJson = () => {
    const values = form.getValues()
    setJsonText(JSON.stringify(values, null, 2))
    toast.success("已将表单内容同步到 JSON")
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate("/admin/sources")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">{isEdit ? "编辑书源" : "新增书源"}</h1>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "form" | "json")}>
        <TabsList>
          <TabsTrigger value="form"><FileText className="mr-2 h-4 w-4" />表单编辑</TabsTrigger>
          <TabsTrigger value="json"><Code2 className="mr-2 h-4 w-4" />JSON 编辑</TabsTrigger>
        </TabsList>

        {/* ============ 表单模式 ============ */}
        <TabsContent value="form">
          <div className="space-y-6">
            {/* 基础信息 */}
            <Card>
              <CardHeader><CardTitle className="text-base">基础信息</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>书源名称 *</Label>
                    <Input {...form.register("bookSourceName")} placeholder="如：笔趣阁" />
                    {form.formState.errors.bookSourceName && (
                      <p className="text-xs text-destructive">{form.formState.errors.bookSourceName.message}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label>书源URL *</Label>
                    <Input {...form.register("bookSourceUrl")} placeholder="https://example.com" />
                  </div>
                  <div className="space-y-2">
                    <Label>书源分组</Label>
                    <Input {...form.register("bookSourceGroup")} placeholder="未分组" />
                  </div>
                  <div className="space-y-2">
                    <Label>权重</Label>
                    <Input type="number" {...form.register("weight", { valueAsNumber: true })} />
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Controller name="enabled" control={form.control} render={({ field }) => (
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  )} />
                  <Label>启用状态</Label>
                </div>
              </CardContent>
            </Card>

            {/* 搜索规则 */}
            <Card>
              <CardHeader><CardTitle className="text-base">搜索规则</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <Label>搜索URL模板</Label>
                  <Input {...form.register("searchUrl")} placeholder="https://example.com/search?q={{key}}&page={{page}}" />
                </div>
                <Separator />
                <RuleInput label="bookList" name="ruleSearch.bookList" placeholder="书籍列表提取规则" register={form.register} />
                <RuleInput label="name" name="ruleSearch.name" placeholder="书名提取规则" register={form.register} />
                <RuleInput label="author" name="ruleSearch.author" placeholder="作者提取规则" register={form.register} />
                <RuleInput label="kind" name="ruleSearch.kind" placeholder="分类(可选)" register={form.register} />
                <RuleInput label="lastChapter" name="ruleSearch.lastChapter" placeholder="最新章节(可选)" register={form.register} />
                <RuleInput label="intro" name="ruleSearch.intro" placeholder="简介(可选)" register={form.register} />
                <RuleInput label="coverUrl" name="ruleSearch.coverUrl" placeholder="封面(可选)" register={form.register} />
                <RuleInput label="noteUrl" name="ruleSearch.noteUrl" placeholder="详情页URL(可选)" register={form.register} />
              </CardContent>
            </Card>

            {/* 详情规则 */}
            <Card>
              <CardHeader><CardTitle className="text-base">详情规则</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <RuleInput label="name" name="ruleBookInfo.name" placeholder="书名提取规则" register={form.register} />
                <RuleInput label="author" name="ruleBookInfo.author" placeholder="作者提取规则" register={form.register} />
                <RuleInput label="intro" name="ruleBookInfo.intro" placeholder="简介(可选)" register={form.register} />
                <RuleInput label="coverUrl" name="ruleBookInfo.coverUrl" placeholder="封面(可选)" register={form.register} />
                <RuleInput label="tocUrl" name="ruleBookInfo.tocUrl" placeholder="目录页URL" register={form.register} />
              </CardContent>
            </Card>

            {/* 目录规则 */}
            <Card>
              <CardHeader><CardTitle className="text-base">目录规则</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <RuleInput label="chapterList" name="ruleToc.chapterList" placeholder="章节列表提取规则" register={form.register} />
                <RuleInput label="chapterName" name="ruleToc.chapterName" placeholder="章节名提取规则" register={form.register} />
                <RuleInput label="chapterUrl" name="ruleToc.chapterUrl" placeholder="章节URL提取规则" register={form.register} />
              </CardContent>
            </Card>

            {/* 正文规则 */}
            <Card>
              <CardHeader><CardTitle className="text-base">正文规则</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <RuleInput label="content" name="ruleContent.content" placeholder="正文提取规则" register={form.register} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ============ JSON 模式 ============ */}
        <TabsContent value="json">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">书源 JSON</CardTitle>
              <div className="flex items-center gap-2">
                <Button type="button" variant="outline" size="sm" onClick={syncFormToJson}>
                  <Wand2 className="mr-1 h-3.5 w-3.5" />
                  从表单同步
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={formatJson}>
                  <Wand2 className="mr-1 h-3.5 w-3.5" />
                  格式化
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3"><p className="text-sm text-muted-foreground">
                直接粘贴或编辑完整的 Legado 书源 JSON。必填字段：<code className="rounded bg-muted px-1">bookSourceName</code>、<code className="rounded bg-muted px-1">bookSourceUrl</code>。
              </p>
              <Textarea
                placeholder='在此粘贴书源 JSON...'
                className="min-h-[560px] font-mono text-xs leading-relaxed"
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                spellCheck={false}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* 操作栏（两种模式共用） */}
      <div className="flex items-center gap-3">
        <Button type="button" disabled={loading} onClick={() => handleSave(false)}>
          <Save className="mr-2 h-4 w-4" />
          {loading ? "保存中..." : "保存"}
        </Button>
        <Button type="button" variant="outline" disabled={loading} onClick={() => handleSave(true)}>
          <FlaskConical className="mr-2 h-4 w-4" />
          保存并测试
        </Button>
        <Button type="button" variant="ghost" onClick={() => navigate("/admin/sources")}>
          取消
        </Button>
      </div>
    </div>
  )
}
