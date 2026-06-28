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
  bookUrl?: string
  tocUrl?: string
  wordCount?: string
  [key: string]: unknown
}

export interface RuleBookInfo {
  name: string
  author: string
  kind?: string
  lastChapter?: string
  wordCount?: string
  intro?: string
  coverUrl?: string
  tocUrl: string
  [key: string]: unknown
}

export interface RuleToc {
  chapterList: string
  chapterName: string
  chapterUrl: string
  nextTocUrl?: string
  [key: string]: unknown
}

export interface RuleContent {
  content: string
  contentFilter?: unknown
  prevContentUrl?: string
  nextContentUrl?: string
  [key: string]: unknown
}

export interface RuleExplore {
  bookList: string
  name: string
  author: string
  kind?: string
  lastChapter?: string
  intro?: string
  coverUrl?: string
  noteUrl?: string
  bookUrl?: string
  tocUrl?: string
  wordCount?: string
  nextUrl?: string
  [key: string]: unknown
}

export interface BookSource {
  id: string
  bookSourceName: string
  bookSourceGroup: string
  bookSourceComment?: string
  bookSourceUrl: string
  bookSourceType?: number
  bookUrlPattern?: string
  customOrder?: number
  enabled: boolean
  enabledExplore?: boolean
  enabledSearch?: boolean
  weight: number
  searchUrl: string
  exploreUrl?: unknown
  ruleSearch: RuleSearch
  ruleBookInfo: RuleBookInfo
  ruleToc: RuleToc
  ruleContent: RuleContent
  ruleExplore?: RuleExplore
  headers?: Record<string, string> | null
  createdAt: string
  updatedAt: string
  [key: string]: unknown
}

export interface BookSourceCreateInput {
  bookSourceName: string
  bookSourceGroup?: string
  bookSourceComment?: string
  bookSourceUrl: string
  bookSourceType?: number
  bookUrlPattern?: string
  customOrder?: number
  enabled?: boolean
  enabledExplore?: boolean
  enabledSearch?: boolean
  weight?: number
  searchUrl?: string
  exploreUrl?: unknown
  ruleSearch?: Partial<RuleSearch>
  ruleBookInfo?: Partial<RuleBookInfo>
  ruleToc?: Partial<RuleToc>
  ruleContent?: Partial<RuleContent>
  ruleExplore?: Partial<RuleExplore>
  headers?: Record<string, string> | null
  [key: string]: unknown
}

export type BookSourceUpdateInput = BookSourceCreateInput

export interface ImportResult {
  success: number
  skipped: number
  failed: number
  errors: string[]
}

export type ConflictStrategy = "skip" | "overwrite" | "new"
