import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { InventoryTab } from '@/components/inventory/inventory-tab'
import type { Summary } from '@/lib/api'
import { json, mockFetch } from '@/test/fetch-mock'
import { renderWithClient } from '@/test/render'

const summary: Summary = {
  last_sync: { id: 3, status: 'succeeded', started_at: new Date().toISOString(), finished_at: new Date().toISOString(), error: null },
  counts: { assets: 9, in_docker: 8, with_edr: 7, identities: 5, active_without_mfa: 1 },
  gaps: { missing_edr: 2, vulnerable_software: 2, orphaned_owner: 1, ghost_assets: 1 },
}

const routes = {
  'GET /api/summary': () => json(summary),
  'GET /api/assets': () => json([{ hostname: 'web-01', sources: ['docker', 'edr'], docker_state: 'running' }]),
  'GET /api/gaps/missing_edr': () => json([{ hostname: 'jump-01', environment: 'prod', owner: 'dave' }]),
  'GET /api/gaps/vulnerable_software': () =>
    json([{ hostname: 'cache-01', software: 'redis', software_version: '6.0.20', cve_count: 16, max_cvss: 9.9, top_cves: ['CVE-2025-49844'] }]),
  'GET /api/gaps/orphaned_owner': () => json([{ hostname: 'jump-01', owner: 'dave', owner_status: 'disabled', reason: 'Owner account is disabled' }]),
  'GET /api/gaps/ghost_assets': () => json([]),
}

beforeEach(() => {
  mockFetch(routes)
})
afterEach(() => vi.unstubAllGlobals())

it('shows totals and every gap', async () => {
  renderWithClient(<InventoryTab claudeReady />)

  expect(await screen.findByText('75%')).toBeInTheDocument() // 6 of 8 running servers have EDR
  expect(screen.getByText(/Last sync/)).toBeInTheDocument()
  expect(await screen.findByRole('cell', { name: 'cache-01' })).toBeInTheDocument()
  expect(screen.getByText('9.9')).toBeInTheDocument()
  expect(screen.getByText('Owner account is disabled')).toBeInTheDocument()
  expect(screen.getByText('No gaps found')).toBeInTheDocument()
})

it('runs a sync and refreshes the data', async () => {
  const fetch = mockFetch({
    ...routes,
    'POST /api/sync': () => json({ run_id: 4, observations: { docker: 9, edr: 7 }, identities: 5, vulnerability_sources: {}, seconds: 0.4 }),
  })
  renderWithClient(<InventoryTab claudeReady />)
  await screen.findByText('75%')

  await userEvent.click(screen.getByRole('button', { name: /Sync now/ }))

  expect(await screen.findByText('Sync #4 finished in 0.4s')).toBeInTheDocument()
  const summaryCalls = () => fetch.mock.calls.filter(([url]) => url === '/api/summary').length
  await vi.waitFor(() => expect(summaryCalls()).toBe(2))
})

it('reports a failed sync', async () => {
  mockFetch({ ...routes, 'POST /api/sync': () => json({ detail: "Couldn't reach Docker" }, 502) })
  renderWithClient(<InventoryTab claudeReady />)
  await userEvent.click(await screen.findByRole('button', { name: /Sync now/ }))
  expect(await screen.findByText("Couldn't reach Docker")).toBeInTheDocument()
})

it('renders the risk report from Claude', async () => {
  mockFetch({
    ...routes,
    'POST /api/risk-summary': () =>
      json({
        overall_risk: 'high',
        headline: 'Critical Redis CVE in prod.',
        findings: [{ title: 'Patch Redis', severity: 'critical', hostnames: ['cache-01'], why_it_matters: 'RCE.', recommended_action: 'Upgrade Redis.' }],
      }),
  })
  renderWithClient(<InventoryTab claudeReady />)
  await userEvent.click(await screen.findByRole('button', { name: /Generate/ }))

  const finding = (await screen.findByText('Patch Redis')).closest('li')!
  expect(within(finding).getByText('Upgrade Redis.')).toBeInTheDocument()
  expect(screen.getByText('high risk')).toBeInTheDocument()
})

it('disables the risk summary without Claude', async () => {
  renderWithClient(<InventoryTab claudeReady={false} />)
  expect(await screen.findByRole('button', { name: /Generate/ })).toBeDisabled()
})
