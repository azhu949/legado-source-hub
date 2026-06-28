export interface AccessUser {
  id: string
  name: string
  access_key: string
  enabled: boolean
  note: string | null
  request_count: number
  last_used_at: string | null
  created_at: string
  updated_at: string
}

export interface AccessUserInput {
  name: string
  note?: string
}
