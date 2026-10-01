import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ResetDemoButton } from '@/components/reset-demo-button'
import { json, mockFetch } from '@/test/fetch-mock'
import { renderWithClient } from '@/test/render'

afterEach(() => vi.unstubAllGlobals())

const sync = { run_id: 1, observations: {}, identities: 5, vulnerability_sources: {}, seconds: 0.2 }

it('resets the demo and reports what changed', async () => {
  mockFetch({ 'POST /api/demo/reset': () => json({ started: ['web-02'], removed: ['rogue-01'], missing: [], sync }) })
  const onReset = vi.fn()
  renderWithClient(<ResetDemoButton onReset={onReset} />)

  await userEvent.click(screen.getByRole('button', { name: 'Reset demo' }))

  expect(await screen.findByText('Fleet started web-02; removed rogue-01.')).toBeInTheDocument()
  expect(onReset).toHaveBeenCalledOnce()
})

it('says when nothing needed fixing', async () => {
  mockFetch({ 'POST /api/demo/reset': () => json({ started: [], removed: [], missing: [], sync }) })
  renderWithClient(<ResetDemoButton onReset={() => {}} />)
  await userEvent.click(screen.getByRole('button', { name: 'Reset demo' }))
  expect(await screen.findByText('Fleet was already in its starting state.')).toBeInTheDocument()
})

it('reports a failed reset', async () => {
  mockFetch({ 'POST /api/demo/reset': () => json({ detail: "Couldn't reach Docker" }, 502) })
  const onReset = vi.fn()
  renderWithClient(<ResetDemoButton onReset={onReset} />)
  await userEvent.click(screen.getByRole('button', { name: 'Reset demo' }))
  expect(await screen.findByText("Couldn't reach Docker")).toBeInTheDocument()
  expect(onReset).not.toHaveBeenCalled()
})
