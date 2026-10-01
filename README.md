# mini-axonius

A small cyber asset inventory. It collects servers, identities, and vulnerabilities from several sources, merges them in Postgres, flags security gaps, and lets you ask questions in plain English to a Claude agent that writes and runs read-only SQL.

Everything runs on your laptop: Terraform starts a fake company's servers as Docker containers, and the only paid service is the Claude API.

## How it works

```
Terraform (Docker provider)
  ├── Postgres
  └── 8 "Acme" servers from data/fleet.json, labeled with owner and environment
          │
Adapters ─┼── Docker Engine API     running containers and their image versions
          ├── NVD CVE API           vulnerabilities per image version (cached, with offline fallback)
          ├── data/edr_agents.json  EDR vendor export, with messy hostnames
          └── data/identities.json  identity provider export
          │
Postgres: every sync appends rows ─► views merge sources by normalized hostname ─► 4 gap views
          │
FastAPI ──┼── /api/summary, /api/assets, /api/gaps/{name}, /api/sync
          ├── /api/risk-summary     one direct Claude call with structured output
          └── /api/chat             LangGraph agent, streamed over server-sent events
          │
React dashboard: Inventory tab and Ask tab
```

The agent is a LangGraph graph with three nodes. The agent node calls Claude with two tools, `get_schema` and `run_sql`. The guardrail node parses every query with `sqlglot` and rejects anything but a single `SELECT`. The tools node runs approved queries as `agent_reader`, a Postgres role that can only read, so a missed check still can't change data. The graph stops after 8 steps and keeps each chat's history in memory.

## Run it

You need Docker, Terraform, [uv](https://docs.astral.sh/uv/), and pnpm.

```bash
cp .env.example .env      # add ANTHROPIC_API_KEY for chat and the risk summary
make infra                # Postgres and the fake servers
make setup                # Python and Node dependencies
make db sync              # create the schema, then run the first sync
make dev                  # API on :8010, dashboard on http://localhost:5180
```

Without an API key, the inventory, gaps, and sync all work, and the chat explains how to connect Claude.

## The planted gaps

| Gap | Server | Why |
| --- | --- | --- |
| Missing EDR agent | `api-02`, `jump-01` | Running, but the EDR export doesn't list them |
| Vulnerable software | `cache-01`, `web-01` | Redis 6.0.20 and nginx 1.21.6 have CVEs in the NVD |
| Orphaned owner | `jump-01` | Owned by `dave`, whose account is disabled |
| Ghost asset | `legacy-ftp-01` | The EDR still reports it, but it isn't running anywhere |

Two commands change the picture live: `docker stop acme-web-02` turns web-02 into a ghost, and `make rogue` starts an unregistered server with an unknown owner. Click **Sync now** after either one.

## Tests

```bash
make test                        # pytest (unit and Postgres integration) and Vitest
cd frontend && pnpm e2e          # Playwright against the running stack
```

The agent tests replace Claude with a scripted model, so they cover the graph, guardrail, and SQL execution without an API key or cost.

## What I'd build next

- More adapters, such as AWS through `boto3`, with the same observation format
- Scheduled syncs and alerts when a new gap appears
- Automated fixes: open a ticket or quarantine a host from a gap row
- The API and dashboard as containers in the same Terraform run
