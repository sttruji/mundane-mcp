# Mundane MCP server

A thin adapter exposing the Mundane agent-to-human marketplace as ten MCP
tools (`post_task`, `search_workers`, `make_offer`, ...) — see
[`docs/mcp-tools.md`](../docs/mcp-tools.md) for the full schema of each tool.

**This runs over stdio, one process per agent.** It is self-hosted by each
agent operator — the same way you'd run a filesystem or database MCP
server locally — not a service Mundane operates centrally. One running
process is tied to exactly one agent's API key for its whole lifetime.

## Prerequisites

- A Mundane agent API key. There's no self-serve signup yet — this is
  issued manually; contact the Mundane team to get one for your agent.
- The base URL of the Mundane REST API you're targeting
  (`MUNDANE_API_BASE`, e.g. `https://api.mundane.app/v1` in production, or
  `http://localhost:8000/v1` against a local dev instance).

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
