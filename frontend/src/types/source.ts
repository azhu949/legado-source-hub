/** 书源类型定义（与后端 JSON schema 一致）。 */

export interface RuleSearch {
  bookList: string
  name: string
  author: string
  kind?: string
  lastChapter?: string
  intro?: string
  coverUrl?: string
  noteUrl?: string
  wordCount?: string
}

export interface RuleBookInfo {
  name: string
  author: string
  intro?: string
  coverUrl?: string
  tocUrl: string
}

export interface RuleToc {
  chapterList: string
  chapterName: string
  chapterUrl: string
}

export interface RuleContent {
  content: string
}

export interface BookSource {
  id: string
  bookSourceName: string
  bookSourceGroup: string
  bookSourceUrl: string
  enabled: boolean
  weight: number
  searchUrl: string
  ruleSearch: RuleSearch
  ruleBookInfo: RuleBookInfo
  ruleToc: RuleToc
  ruleContent: RuleContent
  headers?: Record<string, string> | null
  createdAt: string
  updatedAt: string
}

export interface BookSourceCreateInput {
  bookSourceName: string
  bookSourceGroup?: string
  bookSourceUrl: string
  enabled?: boolean
  weight?: number
  searchUrl?: string
  ruleSearch?: Partial<RuleSearch>
  ruleBookInfo?: Partial<RuleBookInfo>
  ruleToc?: Partial<RuleToc>
  ruleContent?: Partial<RuleContent>
  headers?: Record<string, string> | null
}

export type BookSourceUpdateInput = BookSourceCreateInput

export interface ImportResult {
  success: number
  skipped: number
  failed: number
  errors: string[]
}

export type ConflictStrategy = "skip" | "overwrite" | "new"
