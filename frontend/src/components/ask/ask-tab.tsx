import { ArrowUp, MessageSquarePlus } from 'lucide-react'
import { type FormEvent, type KeyboardEvent, memo, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { AgentSteps } from '@/components/ask/agent-steps'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { type Turn, useChat } from '@/hooks/use-chat'

const SUGGESTIONS = [
  'Which production servers have no EDR agent?',
  'Which servers run software with critical CVEs?',
  'Who owns servers but is disabled or unknown to the identity provider?',
  'Which active users don’t have MFA?',
  'Delete the disabled users',
]

// Memoized so each streamed event re-renders only the turn that changed.
const TurnView = memo(function TurnView({ turn }: { turn: Turn }) {
  const answer = turn.events.findLast((e) => e.type === 'answer')
  return (
    <div className="space-y-3">
      <div className="ml-auto w-fit max-w-[85%] rounded-2xl bg-primary px-4 py-2 text-sm text-primary-foreground">
        {turn.question}
      </div>
      <AgentSteps events={turn.events} streaming={turn.status === 'streaming'} />
      {answer?.type === 'answer' && (
        <div className="prose-answer text-sm leading-relaxed">
          <Markdown>{answer.text}</Markdown>
        </div>
      )}
    </div>
  )
})

export function AskTab({ claudeReady }: { claudeReady: boolean }) {
  const { turns, ask, reset, busy } = useChat()
  const [draft, setDraft] = useState('')
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Braces matter: newer browsers return a promise here, and React treats a returned value as cleanup.
    void bottom.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [turns])

  const submit = (question: string) => {
    const text = question.trim()
    if (!text || busy) return
    setDraft('')
    void ask(text)
  }
  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    submit(draft)
  }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit(draft)
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      {!claudeReady && (
        <Alert>
          <AlertTitle>Claude isn’t connected</AlertTitle>
          <AlertDescription>Add ANTHROPIC_API_KEY to .env and restart the API to chat with the agent.</AlertDescription>
        </Alert>
      )}

      {turns.length === 0 ? (
        <div className="rounded-xl border border-dashed p-6">
          <h2 className="font-medium">Ask about Acme’s assets</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The agent reads the schema, writes SQL, and runs it as a read-only user. Try one of these:
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {SUGGESTIONS.map((question) => (
              <Button key={question} variant="outline" size="sm" onClick={() => submit(question)} disabled={busy}>
                {question}
              </Button>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {turns.map((turn) => (
            <TurnView key={turn.id} turn={turn} />
          ))}
        </div>
      )}
      <div ref={bottom} />

      <form onSubmit={onSubmit} className="sticky bottom-4 flex items-end gap-2 rounded-xl border bg-card p-2 shadow-lg">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question about servers, software, CVEs, or people"
          aria-label="Question"
          rows={1}
          className="max-h-40 min-h-9 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
        />
        {turns.length > 0 && (
          <Button type="button" variant="ghost" size="icon" onClick={reset} aria-label="New chat" title="New chat">
            <MessageSquarePlus />
          </Button>
        )}
        <Button type="submit" size="icon" disabled={busy || !draft.trim()} aria-label="Send">
          <ArrowUp />
        </Button>
      </form>
    </div>
  )
}
