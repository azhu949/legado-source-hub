/** 规则测试 API。 */

import apiClient from "./client"
import type { ApiResponse } from "@/types/api"

export interface RuleTestRequest {
  testUrl?: string
  rules: Record<string, Record<string, string>>
  isJson?: boolean
  sourceId?: string
}

export interface RuleTestResult {
  http: {
    status: number
    headers: Record<string, string>
    elapsed_ms: number
    url: string
  }
  raw: string
  extracted: Record<string, unknown>
  isJson: boolean
}

export async function testRule(req: RuleTestRequest): Promise<ApiResponse<RuleTestResult>> {
  return apiClient.post("/rules/test", req)
}
