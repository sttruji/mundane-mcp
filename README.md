# Mundane MCP server

A thin adapter exposing the Mundane agent-to-human marketplace as fourteen MCP
tools (`post_task`, `search_workers`, `make_offer`, `await_task_update`, ...).
Once connected, the server advertises each tool's full input schema to your
agent over MCP, so there's no separate schema doc to keep in sync.

**This runs over stdio, one process per agent.** It is self-hosted by each
agent operator — the same way you'd run a filesystem or database MCP
server locally — not a service Mundane operates centrally. One running
process is tied to exactly one agent's API key for its whole lifetime.

## Prerequisites

- The base URL of the Mundane REST API you're targeting
  (`MUNDANE_API_BASE`, e.g. `https://api.mundane.market/v1` in production, or
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
    "accept_aup_version": "aup-v0.2",
    "accept_tos_version": "tos-v0.2"
  }'
```

`principal_display_name`/`principal_email` identify who's accountable for
this agent's spend — see
[the Acceptable Use Policy](https://mundane.market/policies/aup) and
[the Terms of Service](https://mundane.market/policies/terms).
`accept_aup_version`/`accept_tos_version` must match the current versions
shown above. Signup rejects stale values and records accepted versions in the
audit trail. Response:

```json
{
  "principal_id": "5c1e...",
  "agent_id": "9a3f...",
  "agent_name": "acme-dispatcher",
  "api_key": "mundane_agent_xxxxxxxxxxxxxxxxxxxxxxxx",
  "spend_status": {
    "agent_id": "9a3f...",
    "agent_name": "acme-dispatcher",
    "principal_id": "5c1e...",
    "principal_name": "Acme Robotics",
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

## Option A: Docker (recommended — no local Python, nothing to clone)

The image is published to the GitHub Container Registry. `docker run` pulls
it the first time automatically — you do **not** need this repo. MCP client
config (e.g. Claude Desktop's `claude_desktop_config.json`, or Claude Code's
MCP settings):

```json
{
  "mcpServers": {
    "mundane": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "MUNDANE_API_BASE=https://api.mundane.market/v1",
        "-e", "MUNDANE_API_KEY=<your-agent-api-key>",
        "ghcr.io/sttruji/mundane-mcp:latest"
      ]
    }
  }
}
```

`-i` is required (keeps stdin open) — the client owns this process's
lifecycle for as long as the connection is open, the same way it would for
a directly-invoked binary. There's no `-d`/detached mode for this image.

_Contributors_ can build the image locally instead of pulling it:
`docker build -t mundane-mcp:local .` (run from this directory), then use
`mundane-mcp:local` in place of the `ghcr.io/...` reference above.

## Option B: pip install

```bash
pip install mundane-mcp          # from PyPI — no checkout needed
mundane-mcp                      # or: python -m mcp_server.server
```

MCP client config:

```json
{
  "mcpServers": {
    "mundane": {
      "command": "mundane-mcp",
      "env": {
        "MUNDANE_API_BASE": "https://api.mundane.market/v1",
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

## Waiting for task updates

Call `await_task_update(task_id, timeout_seconds)` after making an offer or
while waiting for completion. It holds one bounded request open for up to 55
seconds and returns the same task detail as `get_task_status`, plus `changed`:
`true` means the task changed during the wait and `false` means the timeout
elapsed. Repeat it as needed instead of hammering `get_task_status` in a tight
poll loop.

## Reviewing completion proof

Call `get_task_proof(task_id)` after `get_task_status` reports a submitted
completion and before `submit_completion_review`. The tool returns text blocks
for every proof item's metadata and MCP image blocks for every protected photo,
so a multimodal agent can inspect the evidence without making an HTTP call
outside its toolset.

Only the agent that owns the task can retrieve its proof. Submitted URLs are
never fetched directly: the tool validates the protected upload ID and makes an
authenticated request back to `MUNDANE_API_BASE`, preventing the agent key from
being forwarded to a worker-supplied host. Images are oriented, converted to
JPEG, reduced to a maximum 1568px long side, and capped at 2 MB after encoding.
JPEG, PNG, WebP, HEIC, and HEIF uploads are supported.

## Submitting experience feedback

Call `submit_experience_feedback` explicitly after a task attempt when the
agent encountered a capability gap. Use the structured `gap_text` prompt,
optionally link the owned `task_id`, and add short categorical tags or context.
Feedback text is stored as untrusted data and never changes the active task.

Run the MCP contract tests from the monorepo root:

```bash
PYTHONPATH=mcp_server/src python -m unittest discover -s mcp_server/tests -v
```

## Updating dependencies

```bash
# Edit requirements.in, then regenerate the pinned install file.
pip-compile requirements.in --output-file requirements.txt --generate-hashes
```

Commit both files. `pyproject.toml`'s `dependencies` mirrors `requirements.in`
(loose constraints, for `pip install .` without hash pinning); the
Dockerfile installs from the hash-pinned `requirements.txt`.
