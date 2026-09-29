import type { Severity } from '@/lib/api'

export function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const ACRONYMS: Record<string, string> = { ip: 'IP', cve: 'CVE', cves: 'CVEs', cvss: 'CVSS', edr: 'EDR', mfa: 'MFA' }

export function formatLabel(column: string): string {
  const label = column
    .split('_')
    .map((word) => ACRONYMS[word] ?? word)
    .join(' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

export function severityFromScore(score: number): Severity {
  if (score >= 9) return 'critical'
  if (score >= 7) return 'high'
  if (score >= 4) return 'medium'
  return 'low'
}
