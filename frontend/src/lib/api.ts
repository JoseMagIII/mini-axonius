export type Row = Record<string, unknown>

export type Health = { database: boolean; docker: boolean; claude: boolean }

export type Summary = {
  last_sync: { id: number; status: string; started_at: string; finished_at: string | null; error: string | null } | null
  counts: { assets: number; in_docker: number; with_edr: number; identities: number; active_without_mfa: number }
  /** Open findings per gap check, keyed by the gap's name. */
  gaps: Record<string, number>
}

export type SyncResult = {
  run_id: number
  observations: Record<string, number>
  identities: number
  vulnerability_sources: Record<string, string>
  seconds: number
}

export type ResetResult = { started: string[]; removed: string[]; missing: string[]; sync: SyncResult }

export type Severity = 'critical' | 'high' | 'medium' | 'low'

export type RiskReport = {
  overall_risk: Severity
  headline: string
  findings: {
    title: string
    severity: Severity
    hostnames: string[]
    why_it_matters: string
    recommended_action: string
  }[]
}

export type AgentEvent =
  | { type: 'thought'; text: string }
  | { type: 'tool_call'; label: string; sql?: string | null }
  | { type: 'result'; summary: string; sql?: string; columns?: string[]; rows?: Row[] }
  | { type: 'blocked'; sql: string; reason: string }
  | { type: 'error'; message: string; sql?: string | null }
  | { type: 'answer'; text: string }
  | { type: 'done' }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : response.statusText
    throw new ApiError(response.status, detail || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/api/health'),
  summary: () => request<Summary>('/api/summary'),
  assets: () => request<Row[]>('/api/assets'),
  gap: (name: string) => request<Row[]>(`/api/gaps/${name}`),
  sync: () => request<SyncResult>('/api/sync', { method: 'POST' }),
  riskSummary: () => request<RiskReport>('/api/risk-summary', { method: 'POST' }),
  resetDemo: () => request<ResetResult>('/api/demo/reset', { method: 'POST' }),
}

/** Reads the agent's server-sent events and hands each one to `onEvent` as it arrives. */
export async function streamChat(
  message: string,
  threadId: string,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, `Chat request failed (${response.status})`)
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (data) onEvent(JSON.parse(data) as AgentEvent)
    }
  }
}
