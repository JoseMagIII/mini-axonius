import type { ReactNode } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Row } from '@/lib/api'
import { formatCell, formatLabel } from '@/lib/format'
import { cn } from '@/lib/utils'

type Props = {
  rows: Row[]
  columns?: string[]
  empty?: string
  render?: Partial<Record<string, (value: unknown, row: Row) => ReactNode>>
  className?: string
}

const MONO_COLUMNS = new Set(['hostname', 'ip_address', 'software_version', 'top_cves', 'cve_id'])

export function DataTable({ rows, columns, empty = 'No rows', render = {}, className }: Props) {
  const keys = columns ?? Object.keys(rows[0] ?? {})
  if (rows.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>
  }
  return (
    <div className={cn('overflow-x-auto', className)}>
      <Table>
        <TableHeader>
          <TableRow>
            {keys.map((key) => (
              <TableHead key={key} className="text-xs whitespace-nowrap">
                {formatLabel(key)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={String(row.hostname ?? index)}>
              {keys.map((key) => (
                <TableCell key={key} className={cn('text-sm', MONO_COLUMNS.has(key) && 'font-mono text-xs')}>
                  {render[key]?.(row[key], row) ?? formatCell(row[key])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
