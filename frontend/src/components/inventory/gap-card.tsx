import { useQuery } from '@tanstack/react-query'
import { type CellRenderers, DataTable } from '@/components/data-table'
import { SeverityBadge } from '@/components/severity-badge'
import { Badge } from '@/components/ui/badge'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { formatLabel, severityFromScore, timeAgo } from '@/lib/format'

type GapSpec = {
  title: string
  description: string
  columns?: string[]
  render?: CellRenderers
}

// Display text for the gaps the API reports; a new gap still renders with its raw columns.
const GAPS: Record<string, GapSpec> = {
  missing_edr: {
    title: 'Missing EDR agent',
    description: 'Running servers the EDR has never reported.',
    columns: ['hostname', 'environment', 'owner', 'software', 'ip_address'],
  },
  vulnerable_software: {
    title: 'Vulnerable software',
    description: 'Servers whose image version has CVEs in the NVD.',
    columns: ['hostname', 'software', 'software_version', 'cve_count', 'max_cvss', 'top_cves'],
    render: {
      max_cvss: (value) => <SeverityBadge severity={severityFromScore(Number(value))} label={String(value)} />,
      top_cves: (value) => <span className="whitespace-normal">{(value as string[]).slice(0, 2).join(', ')}</span>,
    },
  },
  orphaned_owner: {
    title: 'Orphaned owner',
    description: 'Servers owned by a disabled or unknown account.',
    columns: ['hostname', 'owner', 'owner_status', 'reason'],
  },
  ghost_assets: {
    title: 'Ghost assets',
    description: 'The EDR still reports these, but nothing is running.',
    columns: ['hostname', 'reason', 'edr_status', 'edr_last_checkin'],
    render: { edr_last_checkin: (value) => (value ? timeAgo(String(value)) : '-') },
  },
}

export function GapCard({ name, count }: { name: string; count: number }) {
  const spec = GAPS[name] ?? { title: formatLabel(name), description: '' }
  const { data, isPending, isError } = useQuery({ queryKey: ['gap', name], queryFn: () => api.gap(name) })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{spec.title}</CardTitle>
        <CardDescription>{spec.description}</CardDescription>
        <CardAction>
          <Badge variant={count ? 'default' : 'secondary'} aria-label={`${count} ${spec.title}`}>
            {count}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent>
        {isPending && <Skeleton className="h-24 w-full" />}
        {isError && <p className="text-sm text-destructive">Couldn't load this gap.</p>}
        {data && <DataTable rows={data} columns={spec.columns} render={spec.render} empty="No gaps found" />}
      </CardContent>
    </Card>
  )
}
