import { ChevronRight, Database, ShieldAlert, TableProperties, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { DataTable } from '@/components/data-table'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { AgentEvent } from '@/lib/api'
import { cn } from '@/lib/utils'

type StepEvent = Exclude<AgentEvent, { type: 'answer' } | { type: 'done' }>

function SqlBlock({ sql }: { sql: string }) {
  return (
    <pre className="mt-1.5 overflow-x-auto rounded-md bg-muted px-3 py-2 font-mono text-xs leading-relaxed whitespace-pre-wrap">
      {sql}
    </pre>
  )
}

const TONES = { danger: 'text-critical', warn: 'text-medium' }

function Step({ icon, children, tone }: { icon: ReactNode; children: ReactNode; tone?: keyof typeof TONES }) {
  return (
    <li className="flex gap-2.5">
      <span className={cn('mt-0.5 text-muted-foreground', tone && TONES[tone])}>{icon}</span>
      <div className="min-w-0 flex-1 text-sm">{children}</div>
    </li>
  )
}

function StepView({ event }: { event: StepEvent }) {
  switch (event.type) {
    case 'thought':
      return <Step icon={<ChevronRight className="size-4" />}><p className="text-muted-foreground">{event.text}</p></Step>
    case 'tool_call':
      return (
        <Step icon={<Database className="size-4" />}>
          <p>{event.label}</p>
          {event.sql && <SqlBlock sql={event.sql} />}
        </Step>
      )
    case 'result':
      return (
        <Step icon={<TableProperties className="size-4" />}>
          <p className="text-muted-foreground">{event.summary}</p>
          {event.rows && event.rows.length > 0 && (
            <div className="mt-1.5 max-h-72 overflow-auto rounded-md border">
              <DataTable rows={event.rows} columns={event.columns} />
            </div>
          )}
        </Step>
      )
    case 'blocked':
      return (
        <Step icon={<ShieldAlert className="size-4" />} tone="danger">
          <p className="font-medium text-critical">Blocked by the guardrail: {event.reason}</p>
          <SqlBlock sql={event.sql} />
        </Step>
      )
    case 'error':
      return (
        <Step icon={<TriangleAlert className="size-4" />} tone="warn">
          <p className="text-medium">{event.message}</p>
          {event.sql && <SqlBlock sql={event.sql} />}
        </Step>
      )
  }
}

export function AgentSteps({ events, streaming }: { events: AgentEvent[]; streaming: boolean }) {
  const steps = events.filter((e): e is StepEvent => e.type !== 'answer' && e.type !== 'done')
  if (steps.length === 0) return null
  return (
    <Collapsible defaultOpen className="rounded-lg border bg-card/50">
      <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-muted-foreground">
        <ChevronRight className="size-3.5 transition-transform group-data-[state=open]:rotate-90" />
        {streaming ? 'Working' : 'Agent steps'} ({steps.length})
        {streaming && <span className="ml-1 size-1.5 animate-pulse rounded-full bg-primary" />}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="space-y-3 px-3 pb-3">
          {steps.map((event, index) => (
            <StepView key={index} event={event} />
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  )
}
