import { Badge } from '@/components/ui/badge'
import type { Severity } from '@/lib/api'
import { cn } from '@/lib/utils'

const STYLES: Record<Severity, string> = {
  critical: 'bg-critical/15 text-critical border-critical/30',
  high: 'bg-high/15 text-high border-high/30',
  medium: 'bg-medium/15 text-medium border-medium/30',
  low: 'bg-low/15 text-low border-low/30',
}

export function SeverityBadge({ severity, label }: { severity: Severity; label?: string }) {
  return (
    <Badge variant="outline" className={cn('font-medium capitalize', STYLES[severity])}>
      {label ?? severity}
    </Badge>
  )
}
