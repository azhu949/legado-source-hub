/** 常量定义。 */

export const ROUTES = {
  LOGIN: "/admin/login",
  DASHBOARD: "/admin",
  SOURCES: "/admin/sources",
  SOURCE_NEW: "/admin/sources/new",
  SOURCE_EDIT: "/admin/sources/:id/edit",
  SOURCE_DETAIL: "/admin/sources/:id",
  SOURCE_IMPORT: "/admin/sources/import",
  RULE_TEST: "/admin/rules/test",
  HEALTH: "/admin/health",
  LOGS: "/admin/logs",
} as const

export const DEFAULT_PAGE_SIZE = 20

export const HEALTH_REFRESH_INTERVALS = [
  { label: "10秒", value: 10_000 },
  { label: "30秒", value: 30_000 },
  { label: "60秒", value: 60_000 },
  { label: "关闭", value: 0 },
] as const
