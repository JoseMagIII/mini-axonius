import { afterEach, expect, it, vi } from 'vitest'
import { type AgentEvent, api, ApiError, streamChat } from '@/lib/api'
import { frames, json, mockFetch, sse } from '@/test/fetch-mock'

afterEach(() => vi.unstubAllGlobals())

it('parses SSE frames even when they arrive split across reads', async () => {
  const body = frames({ type: 'tool_call', tool: 'run_sql', sql: 'SELECT 1' }, { type: 'answer', text: 'One.' }, { type: 'done' })
  const fetch = mockFetch({ 'POST /api/chat': () => sse([body.slice(0, 17), body.slice(17, 60), body.slice(60)]) })
  const events: AgentEvent[] = []

  await streamChat('hi', 'thread-1', (event) => events.push(event))

  expect(events.map((e) => e.type)).toEqual(['tool_call', 'answer', 'done'])
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ message: 'hi', thread_id: 'thread-1' })
})

it('raises when the chat request fails', async () => {
  mockFetch({ 'POST /api/chat': () => json({}, 500) })
  await expect(streamChat('hi', 't', () => {})).rejects.toThrow('Chat request failed (500)')
})

it('surfaces the API error detail', async () => {
  mockFetch({ 'POST /api/risk-summary': () => json({ detail: 'Add ANTHROPIC_API_KEY' }, 503) })
  const error = await api.riskSummary().catch((e: unknown) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect((error as ApiError).status).toBe(503)
  expect((error as ApiError).message).toBe('Add ANTHROPIC_API_KEY')
})
