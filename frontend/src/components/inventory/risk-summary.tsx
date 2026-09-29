import { useMutation } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { SeverityBadge } from '@/components/severity-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'

export function RiskSummary({ claudeReady }: { claudeReady: boolean }) {
  const summary = useMutation({ mutationFn: api.riskSummary })
  const report = summary.data

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk summary</CardTitle>
        <CardDescription>Claude ranks the current gaps and recommends what to fix first.</CardDescription>
        <CardAction>
          <Button onClick={() => summary.mutate()} disabled={summary.isPending || !claudeReady}>
            <Sparkles />
            {summary.isPending ? 'Generating...' : report ? 'Regenerate' : 'Generate'}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        {!claudeReady && <p className="text-sm text-muted-foreground">Add ANTHROPIC_API_KEY to .env to turn this on.</p>}
        {summary.isPending && <Skeleton className="h-28 w-full" />}
        {summary.isError && (
          <Alert variant="destructive">
            <AlertTitle>Couldn't generate the summary</AlertTitle>
            <AlertDescription>{summary.error.message}</AlertDescription>
          </Alert>
        )}
        {report && !summary.isPending && (
          <>
            <div className="flex items-start gap-3">
              <SeverityBadge severity={report.overall_risk} label={`${report.overall_risk} risk`} />
              <p className="text-sm font-medium">{report.headline}</p>
            </div>
            <ol className="space-y-2">
              {report.findings.map((finding) => (
                <li key={finding.title} className="rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={finding.severity} />
                    <span className="font-medium">{finding.title}</span>
                    <span className="font-mono text-xs text-muted-foreground">{finding.hostnames.join(', ')}</span>
                  </div>
                  <p className="mt-1.5 text-sm text-muted-foreground">{finding.why_it_matters}</p>
                  <p className="mt-1 text-sm">{finding.recommended_action}</p>
                </li>
              ))}
            </ol>
          </>
        )}
      </CardContent>
    </Card>
  )
}
