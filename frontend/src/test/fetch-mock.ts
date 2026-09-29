import { vi } from 'vitest'

type Handler = (init?: RequestInit) => Response | Promise<Response>

export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** Streams SSE frames in the given chunks, so tests can split a frame across reads. */
export function sse(chunks: string[]) {
  const encoder = new TextEncoder()
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

export function frames(...events: unknown[]) {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
}

export function mockFetch(routes: Record<string, Handler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const handler = routes[`${method} ${url}`]
    if (!handler) throw new Error(`Unexpected request: ${method} ${url}`)
    return handler(init)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}
