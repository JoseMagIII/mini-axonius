import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { DataTable } from '@/components/data-table'
import { GapCard } from '@/components/inventory/gap-card'
import { RiskSummary } from '@/components/inventory/risk-summary'
import { StatCards } from '@/components/inventory/stat-cards'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { timeAgo } from '@/lib/format'

const ASSET_COLUMNS = ['hostname', 'sources', 'docker_state', 'environment', 'owner', 'software', 'software_version', 'ip_address']

export function InventoryTab({ claudeReady }: { claudeReady: boolean }) {
  const queryClient = useQueryClient()
  const summary = useQuery({ queryKey: ['summary'], queryFn: api.summary })
  const assets = useQuery({ queryKey: ['assets'], queryFn: api.assets })

  const sync = useMutation({
    mutationFn: api.sync,
    onSuccess: (result) => {
      const found = Object.entries(result.observations).map(([source, n]) => `${n} from ${source}`).join(', ')
      toast.success(`Sync #${result.run_id} finished in ${result.seconds}s`, { description: found })
      return queryClient.invalidateQueries()
    },
    onError: (error) => toast.error('Sync failed', { description: error.message }),
  })

  const lastSync = summary.data?.last_sync

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          {lastSync ? (
            <>
              Last sync <span className="text-foreground">#{lastSync.id}</span>{' '}
              {timeAgo(lastSync.finished_at ?? lastSync.started_at)}
              {lastSync.status === 'failed' && <Badge variant="destructive" className="ml-2">failed</Badge>}
            </>
          ) : summary.isSuccess ? (
            'No sync yet. Run one to build the inventory.'
          ) : null}
        </div>
        <Button onClick={() => sync.mutate()} disabled={sync.isPending}>
          <RefreshCw className={sync.isPending ? 'animate-spin' : undefined} />
          {sync.isPending ? 'Syncing...' : 'Sync now'}
        </Button>
      </div>

      {summary.data ? <StatCards summary={summary.data} /> : <Skeleton className="h-24 w-full" />}

      <div className="grid gap-4 xl:grid-cols-2">
        {Object.entries(summary.data?.gaps ?? {}).map(([name, count]) => (
          <GapCard key={name} name={name} count={count} />
        ))}
      </div>

      <RiskSummary claudeReady={claudeReady} />

      <Card>
        <CardHeader>
          <CardTitle>All assets</CardTitle>
          <CardDescription>One row per asset, merged from Docker and the EDR by normalized hostname.</CardDescription>
        </CardHeader>
        <CardContent>
          {assets.data ? (
            <DataTable
              rows={assets.data}
              columns={ASSET_COLUMNS}
              render={{
                sources: (value) => (
                  <div className="flex gap-1">
                    {(value as string[]).map((source) => (
                      <Badge key={source} variant="secondary">{source}</Badge>
                    ))}
                  </div>
                ),
              }}
            />
          ) : (
            <Skeleton className="h-40 w-full" />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
