import { useQuery } from '@tanstack/react-query'
import { Moon, Radar, Sun } from 'lucide-react'
import { AskTab } from '@/components/ask/ask-tab'
import { InventoryTab } from '@/components/inventory/inventory-tab'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Toaster } from '@/components/ui/sonner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useTheme } from '@/hooks/use-theme'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

function StatusDot({ label, ok }: { label: string; ok: boolean | undefined }) {
  return (
    <Badge variant="outline" className="gap-1.5 font-normal">
      <span className={cn('size-1.5 rounded-full', ok === undefined ? 'bg-muted-foreground' : ok ? 'bg-healthy' : 'bg-critical')} />
      {label}
    </Badge>
  )
}

export default function App() {
  const { theme, toggle } = useTheme()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15_000 })
  const claudeReady = health.data?.claude ?? false

  return (
    <div className="min-h-svh">
      <header className="border-b bg-card/40 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
              <Radar className="size-4.5" />
            </span>
            <div>
              <p className="leading-tight font-semibold">Acme asset inventory</p>
              <p className="text-xs text-muted-foreground">Docker, EDR, identity, and NVD data merged</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusDot label="Database" ok={health.data?.database} />
            <StatusDot label="Docker" ok={health.data?.docker} />
            <StatusDot label="Claude" ok={health.data ? claudeReady : undefined} />
            <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Tabs defaultValue="inventory">
          <TabsList className="mb-4">
            <TabsTrigger value="inventory">Inventory</TabsTrigger>
            <TabsTrigger value="ask">Ask</TabsTrigger>
          </TabsList>
          <TabsContent value="inventory">
            <InventoryTab claudeReady={claudeReady} />
          </TabsContent>
          <TabsContent value="ask">
            <AskTab claudeReady={claudeReady} />
          </TabsContent>
        </Tabs>
      </main>
      <Toaster theme={theme} position="bottom-right" />
    </div>
  )
}
