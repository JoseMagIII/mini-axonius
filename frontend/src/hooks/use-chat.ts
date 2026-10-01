import { useCallback, useRef, useState } from 'react'
import { type AgentEvent, streamChat } from '@/lib/api'

export type Turn = {
  id: string
  question: string
  events: AgentEvent[]
  status: 'streaming' | 'done' | 'error'
}

export function useChat() {
  const [threadId, setThreadId] = useState(() => crypto.randomUUID())
  const [turns, setTurns] = useState<Turn[]>([])
  const abort = useRef<AbortController | null>(null)

  const update = (id: string, change: (turn: Turn) => Turn) =>
    setTurns((all) => all.map((turn) => (turn.id === id ? change(turn) : turn)))

  const ask = useCallback(
    async (question: string) => {
      const id = crypto.randomUUID()
      const controller = new AbortController()
      abort.current = controller
      setTurns((all) => [...all, { id, question, events: [], status: 'streaming' }])
      try {
        await streamChat(
          question,
          threadId,
          (event) => {
            if (event.type === 'done') return
            update(id, (turn) => ({ ...turn, events: [...turn.events, event] }))
          },
          controller.signal,
        )
        update(id, (turn) => ({ ...turn, status: 'done' }))
      } catch (error) {
        if (controller.signal.aborted) return
        const message = error instanceof Error ? error.message : 'The request failed'
        update(id, (turn) => ({ ...turn, status: 'error', events: [...turn.events, { type: 'error', message }] }))
      }
    },
    [threadId],
  )

  const reset = useCallback(() => {
    abort.current?.abort()
    setTurns([])
    setThreadId(crypto.randomUUID())
  }, [])

  const busy = turns.at(-1)?.status === 'streaming'
  return { turns, ask, reset, busy }
}
