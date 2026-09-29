import { execSync } from 'node:child_process'
import { expect, type Page, test } from '@playwright/test'

const docker = (args: string) => execSync(`docker ${args}`, { stdio: 'pipe' }).toString()

function gapCard(page: Page, title: string) {
  return page.locator('[data-slot="card"]').filter({ has: page.getByText(title, { exact: true }) })
}

async function syncNow(page: Page) {
  await page.getByRole('button', { name: 'Sync now' }).click()
  await expect(page.getByText(/Sync #\d+ finished/)).toBeVisible()
}

test.afterAll(() => {
  docker('start acme-web-02')
  execSync('docker rm -f acme-rogue-01 || true', { stdio: 'pipe' })
})

test('inventory shows the planted gaps from the live containers', async ({ page }) => {
  await page.goto('/')
  await syncNow(page)

  await expect(gapCard(page, 'Missing EDR agent').getByRole('cell', { name: 'jump-01' })).toBeVisible()
  await expect(gapCard(page, 'Missing EDR agent').getByRole('cell', { name: 'api-02' })).toBeVisible()
  await expect(gapCard(page, 'Vulnerable software').getByRole('cell', { name: 'cache-01' })).toBeVisible()
  await expect(gapCard(page, 'Orphaned owner').getByText('Owner account is disabled')).toBeVisible()
  await expect(gapCard(page, 'Ghost assets').getByRole('cell', { name: 'legacy-ftp-01' })).toBeVisible()
  await page.screenshot({ path: 'test-results/inventory-dark.png', fullPage: true })
})

test('stopping a server turns it into a ghost after a sync', async ({ page }) => {
  await page.goto('/')
  docker('stop acme-web-02')
  await syncNow(page)
  const ghosts = gapCard(page, 'Ghost assets')
  await expect(ghosts.getByRole('cell', { name: 'web-02' })).toBeVisible()
  await expect(ghosts.getByText('Container is exited')).toBeVisible()

  docker('start acme-web-02')
  await syncNow(page)
  await expect(ghosts.getByRole('cell', { name: 'web-02' })).toHaveCount(0)
})

test('a rogue server shows up as unprotected and unowned', async ({ page }) => {
  await page.goto('/')
  docker(
    'run -d --name acme-rogue-01 --hostname rogue-01 --label acme.managed=true --label acme.owner=mallory --label acme.env=prod alpine:3.22 sleep infinity',
  )
  await syncNow(page)
  await expect(gapCard(page, 'Missing EDR agent').getByRole('cell', { name: 'rogue-01' })).toBeVisible()
  await expect(gapCard(page, 'Orphaned owner').getByText('Owner not in identity provider')).toBeVisible()

  docker('rm -f acme-rogue-01')
  await syncNow(page)
  await expect(gapCard(page, 'Missing EDR agent').getByRole('cell', { name: 'rogue-01' })).toHaveCount(0)
})

test('ask tab explains how to connect Claude when no key is set', async ({ page, request }) => {
  const health = await (await request.get('/api/health')).json()
  test.skip(health.claude, 'Claude is connected; this checks the no-key path')

  await page.goto('/')
  await page.getByRole('tab', { name: 'Ask' }).click()
  await expect(page.getByText('Claude isn’t connected')).toBeVisible()
  await page.getByRole('button', { name: 'Which production servers have no EDR agent?' }).click()
  await expect(page.getByText('Add ANTHROPIC_API_KEY to .env to chat with the agent.')).toBeVisible()
  await page.screenshot({ path: 'test-results/ask-no-key.png', fullPage: true })
})

test('theme toggle switches to light and remembers it', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Toggle theme' }).click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await page.reload()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await expect(page.getByText(/Last sync/)).toBeVisible()
  await page.screenshot({ path: 'test-results/inventory-light.png', fullPage: true })
})

test('fits a phone screen without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByText('Missing EDR agent')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(0)
  await page.screenshot({ path: 'test-results/inventory-phone.png', fullPage: true })
})
