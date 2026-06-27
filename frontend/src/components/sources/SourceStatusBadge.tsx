/** 书源状态徽标。 */

import { Badge } from "@/components/ui/badge"

interface SourceStatusBadgeProps {
  enabled: boolean
  healthStatus?: "healthy" | "unhealthy" | "unknown"
}

export function SourceStatusBadge({ enabled, healthStatus = "unknown" }: SourceStatusBadgeProps) {
  if (!enabled) {
    return <Badge variant="secondary">禁用</Badge>
  }

  switch (healthStatus) {
    case "healthy":
      return <Badge variant="success">正常</Badge>
    case "unhealthy":
      return <Badge variant="danger">异常</Badge>
    default:
      return <Badge variant="outline">未知</Badge>
  }
}
