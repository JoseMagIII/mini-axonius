import { useMutation, useQueryClient } from '@tanstack/react-query'
import { RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { api, type ResetResult } from '@/lib/api'

function describe({ started, removed, missing }: ResetResult): string {
  const parts = [
    started.length && `started ${started.join(', ')}`,
    removed.length && `removed ${removed.join(', ')}`,
    missing.length && `missing ${missing.join(', ')}, run make infra`,
  ].filter(Boolean)
  return parts.length ? `Fleet ${parts.join('; ')}.` : 'Fleet was already in its starting state.'
}

export function ResetDemoButton({ onReset }: { onReset: () => void }) {
  const queryClient = useQueryClient()
  const reset = useMutation({
    mutationFn: api.resetDemo,
    onSuccess: (result) => {
      toast.success('Demo reset', { description: describe(result) })
      onReset()
      return queryClient.invalidateQueries()
    },
    onError: (error) => toast.error("Couldn't reset the demo", { description: error.message }),
  })

  return (
    <Button variant="outline" size="sm" onClick={() => reset.mutate()} disabled={reset.isPending}>
      <RotateCcw className={reset.isPending ? 'animate-spin' : undefined} />
      {reset.isPending ? 'Resetting...' : 'Reset demo'}
    </Button>
  )
}
