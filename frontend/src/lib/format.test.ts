import { describe, expect, it } from 'vitest'
import { formatCell, formatLabel, severityFromScore, timeAgo } from '@/lib/format'

describe('formatCell', () => {
  it.each([
    [null, '-'],
    ['', '-'],
    [['docker', 'edr'], 'docker, edr'],
    [true, 'yes'],
    [7.5, '7.5'],
    [{ a: 1 }, '{"a":1}'],
  ])('formats %j as %s', (value, expected) => {
    expect(formatCell(value)).toBe(expected)
  })
})

it('turns column names into labels', () => {
  expect(formatLabel('software_version')).toBe('Software version')
  expect(formatLabel('max_cvss')).toBe('Max CVSS')
  expect(formatLabel('edr_last_checkin')).toBe('EDR last checkin')
})

it('describes how long ago something happened', () => {
  const now = Date.parse('2026-09-30T12:00:00Z')
  expect(timeAgo('2026-09-30T11:59:30Z', now)).toBe('just now')
  expect(timeAgo('2026-09-30T11:55:00Z', now)).toBe('5 min ago')
  expect(timeAgo('2026-09-30T09:00:00Z', now)).toBe('3 h ago')
  expect(timeAgo('2026-09-27T12:00:00Z', now)).toBe('3 d ago')
})

it('maps CVSS scores to severities', () => {
  expect([9.8, 7.5, 5, 2].map(severityFromScore)).toEqual(['critical', 'high', 'medium', 'low'])
})
