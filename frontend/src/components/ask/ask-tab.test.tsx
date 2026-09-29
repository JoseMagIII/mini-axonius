import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AskTab } from '@/components/ask/ask-tab'
import { frames, mockFetch, sse } from '@/test/fetch-mock'
import { renderWithClient } from '@/test/render'

afterEach(() => vi.unstubAllGlobals())

it('streams the agent steps and the answer', async () => {
  mockFetch({
    'POST /api/chat': () =>
      sse([
        frames(
          { type: 'tool_call', label: 'Running SQL', sql: 'SELECT hostname FROM gap_missing_edr LIMIT 200' },
          { type: 'result', summary: 'Returned 2 rows', columns: ['hostname'], rows: [{ hostname: 'api-02' }, { hostname: 'jump-01' }] },
          { type: 'answer', text: '**api-02** and **jump-01** have no EDR.' },
          { type: 'done' },
        ),
      ]),
  })
  renderWithClient(<AskTab claudeReady />)

  await userEvent.click(screen.getByRole('button', { name: 'Which production servers have no EDR agent?' }))

  expect(await screen.findByText('Returned 2 rows')).toBeInTheDocument()
  expect(screen.getByText('SELECT hostname FROM gap_missing_edr LIMIT 200')).toBeInTheDocument()
  expect(screen.getByRole('cell', { name: 'jump-01' })).toBeInTheDocument()
  expect(screen.getByText('api-02', { selector: 'strong' })).toBeInTheDocument()
  expect(screen.getByText('Agent steps (2)')).toBeInTheDocument()
})

it('shows guardrail blocks', async () => {
  mockFetch({
    'POST /api/chat': () =>
      sse([
        frames(
          { type: 'tool_call', label: 'Running SQL', sql: 'DELETE FROM identities' },
          { type: 'blocked', sql: 'DELETE FROM identities', reason: 'Only SELECT queries are allowed.' },
          { type: 'answer', text: 'I can only read data.' },
          { type: 'done' },
        ),
      ]),
  })
  renderWithClient(<AskTab claudeReady />)

  await userEvent.type(screen.getByLabelText('Question'), 'Delete everyone{Enter}')

  expect(await screen.findByText(/Blocked by the guardrail/)).toHaveTextContent('Only SELECT queries are allowed.')
  expect(screen.getByText('Delete everyone')).toBeInTheDocument()
})

it('keeps one thread id across questions and starts a new one on reset', async () => {
  const fetch = mockFetch({ 'POST /api/chat': () => sse([frames({ type: 'answer', text: 'ok' }, { type: 'done' })]) })
  renderWithClient(<AskTab claudeReady />)
  const input = screen.getByLabelText('Question')

  await userEvent.type(input, 'first{Enter}')
  await screen.findByText('ok')
  await userEvent.type(input, 'second{Enter}')
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  await userEvent.click(screen.getByRole('button', { name: 'New chat' }))
  await userEvent.type(input, 'third{Enter}')
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))

  const threads = fetch.mock.calls.map((call) => JSON.parse(String(call[1]?.body)).thread_id)
  expect(threads[0]).toBe(threads[1])
  expect(threads[2]).not.toBe(threads[0])
})

it('shows a network failure in the conversation', async () => {
  mockFetch({ 'POST /api/chat': () => Promise.reject(new Error('Failed to fetch')) })
  renderWithClient(<AskTab claudeReady />)
  await userEvent.type(screen.getByLabelText('Question'), 'hello{Enter}')
  expect(await screen.findByText('Failed to fetch')).toBeInTheDocument()
})

it('explains how to connect Claude', () => {
  renderWithClient(<AskTab claudeReady={false} />)
  const alert = screen.getByRole('alert')
  expect(within(alert).getByText(/ANTHROPIC_API_KEY/)).toBeInTheDocument()
})
