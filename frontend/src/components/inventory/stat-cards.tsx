import { Card, CardContent } from '@/components/ui/card'
import type { Summary } from '@/lib/api'
import { cn } from '@/lib/utils'

type Stat = { label: string; value: string; detail: string; tone?: 'alert' }

function stats({ counts, gaps }: Summary): Stat[] {
  const openGaps = Object.values(gaps).reduce((total, n) => total + n, 0)
  const coverage = counts.in_docker ? Math.round(((counts.in_docker - gaps.missing_edr) / counts.in_docker) * 100) : 0
  return [
    { label: 'Assets', value: String(counts.assets), detail: `${counts.in_docker} running in Docker, ${counts.with_edr} with EDR` },
    { label: 'EDR coverage', value: `${coverage}%`, detail: `${gaps.missing_edr} running servers unprotected`, tone: gaps.missing_edr ? 'alert' : undefined },
    { label: 'Identities', value: String(counts.identities), detail: `${counts.active_without_mfa} active without MFA` },
    { label: 'Open gaps', value: String(openGaps), detail: `Across ${Object.keys(gaps).length} checks`, tone: openGaps ? 'alert' : undefined },
  ]
}

export function StatCards({ summary }: { summary: Summary }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {stats(summary).map((stat) => (
        <Card key={stat.label} size="sm">
          <CardContent>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{stat.label}</p>
            <p className={cn('mt-1 text-3xl font-semibold', stat.tone === 'alert' && 'text-primary')}>
              {stat.value}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{stat.detail}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
