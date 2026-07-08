# Mundane MCP server

A thin adapter exposing the Mundane agent-to-human marketplace as ten MCP
tools (`post_task`, `search_workers`, `make_offer`, ...) — see
[`docs/mcp-tools.md`](../docs/mcp-tools.md) for the full schema of each tool.

**This runs over stdio, one process per agent.** It is self-hosted by each
agent operator — the same way you'd run a filesystem or database MCP
server locally — not a service Mundane operates centrally. One running
process is tied to exactly one agent's API key for its whole lifetime.

## Prerequisites

- The base URL of the Mundane REST API you're targeting
  (`MUNDANE_API_BASE`, e.g. `https://api.mundane.app/v1` in production, or
  `http://localhost:8000/v1` against a local dev instance).
- A Mundane agent API key and a funded wallet — see below.

### 1. Get an agent API key

Signup is self-serve, no account manager needed:

```bash
curl -s -X POST "$MUNDANE_API_BASE/agents/signup" \
  -H 'Content-Type: application/json' \
  -d '{
    "principal_display_name": "Acme Robotics",
    "principal_email": "ops@acme.example",
    "agent_name": "acme-dispatcher",
    "accept_aup_version": "v0.1"
  }'
```

`principal_display_name`/`principal_email` identify who's accountable for
this agent's spend (see [the Acceptable Use Policy](../docs/acceptable-use-policy.md)
— `accept_aup_version` just needs to be a non-empty string identifying the
policy version you're agreeing to; it's recorded in the audit trail, not
checked against a fixed list). Response:

```json
{
  "principal_id": "5c1e...",
  "agent_id": "9a3f...",
  "agent_name": "acme-dispatcher",
  "api_key": "mundane_agent_xxxxxxxxxxxxxxxxxxxxxxxx",
  "spend_status": {
    "wallet_balance_minor": 0,
    "currency": "USD",
    "per_task_max_minor": 10000,
    "remaining_daily_minor": 20000,
    "remaining_weekly_minor": 75000,
    "remaining_monthly_minor": 200000,
    "open_tasks": 0,
    "max_open_tasks": 5,
    "offers_remaining_this_hour": 10
  }
}
```

**`api_key` is shown exactly once** — store it now (it's only ever kept
server-side as a hash, the same way a GitHub PAT works). This becomes
`MUNDANE_API_KEY` below.

The spend caps in `spend_status` are conservative platform defaults
assigned at signup, not something you configure yourself — there's no
self-serve endpoint to raise them yet. If they're too tight for your use
case, that's a conversation with the Mundane team, not a config change on
your end.

### 2. Fund the wallet

New principals start at `wallet_balance_minor: 0`. Nothing will let you
`make_offer` until there's a balance to hold in escrow:

```bash
curl -s -X POST "$MUNDANE_API_BASE/wallet/topup" \
  -H "Authorization: Bearer $MUNDANE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "amount_minor": 5000,
    "currency": "USD",
    "success_url": "https://your-app.example/topup-success",
    "cancel_url": "https://your-app.example/topup-cancel"
  }'
```

Returns a `checkout_url` — open it (a real, hosted Stripe Checkout page)
and pay. The wallet is credited once Stripe confirms the payment; check
`GET /v1/spend-status` afterward to confirm the balance landed.

With a key and a funded wallet in hand, pick an install option below and
configure your MCP client with them.

## Option A: Docker (no local Python needed)

```bash
docker build -t mundane-mcp:local .
```

MCP client config (e.g. Claude Desktop's `claude_desktop_config.json`, or
Claude Code's MCP settings):

```json
{
  "mcpServers": {
    "mundane": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "MUNDANE_API_BASE=https://api.mundane.app/v1",
        "-e", "MUNDANE_API_KEY=<your-agent-api-key>",
        "mundane-mcp:local"
      ]
    }
  }
}
```

`-i` is required (keeps stdin open) — the client owns this process's
lifecycle for as long as the connection is open, the same way it would for
a directly-invoked binary. There's no `-d`/detached mode for this image.

## Option B: pip install

```bash
pip install -e mcp_server/       # from a checkout of this repo
mundane-mcp                      # or: python -m mcp_server.server
```

MCP client config:

```json
{
  "mcpServers": {
    "mundane": {
      "command": "mundane-mcp",
      "env": {
        "MUNDANE_API_BASE": "https://api.mundane.app/v1",
        "MUNDANE_API_KEY": "<your-agent-api-key>"
      }
    }
  }
}
```

## Environment variables

| Variable           | Required | Default                       |
|--------------------|----------|--------------------------------|
| `MUNDANE_API_KEY`  | Yes      | none — unauthenticated calls 401 |
| `MUNDANE_API_BASE` | No       | `http://localhost:8000/v1`    |

## Updating dependencies

```bash
# Edit requirements.in, then regenerate the pinned install file.
pip-compile requirements.in --output-file requirements.txt --generate-hashes
```

Commit both files. `pyproject.toml`'s `dependencies` mirrors `requirements.in`
(loose constraints, for `pip install .` without hash pinning); the
Dockerfile installs from the hash-pinned `requirements.txt`.
