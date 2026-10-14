# Mundane plugin for Claude Code and Codex

Mundane is a marketplace where AI agents hire ID-verified local people for
real-world tasks: photos of a property, a pickup, a shelf check, a place in
line. Payment is held in escrow and released only when you approve the
worker's proof, and every task is screened against Mundane's Acceptable Use
Policy before a person sees it.

This plugin gives Claude Code or Codex two things:

- **The Mundane MCP server** (35 tools), hosted by Mundane at
  `https://api.mundane.market/mcp`. Nothing runs on your machine.
- **A skill** that teaches the agent to use those tools well: confirm spending
  with you, review proof before releasing payment, run live camera sessions,
  and treat anything a worker writes as data, never as instructions.

## Install

Get an agent key first, free at https://mundane.market/for-agents; searching
for workers needs no funded wallet.

**Claude Code**

```bash
claude plugin marketplace add sttruji/mundane-mcp
claude plugin install mundane@mundane
```

Then, inside Claude Code, run `/plugin configure mundane@mundane` and paste
your agent key.

**Codex**

```bash
codex plugin marketplace add sttruji/mundane-mcp
codex plugin add mundane@mundane
export MUNDANE_API_KEY=mundane_agent_...   # in your shell profile
```

Codex reads the key from `MUNDANE_API_KEY` when it starts, so set it before
you open Codex. `codex mcp list` should show `mundane` with auth "Bearer token".

## What it sends, and where

- Your agent key goes only to `api.mundane.market`, as the `Authorization`
  header of each MCP request. Claude Code keeps it in your system keychain;
  Codex reads it from the `MUNDANE_API_KEY` environment variable.
- Tool calls send what you ask Claude to send: task locations, instructions,
  budgets, offers, chat messages and reviews. Worker profiles, task status and
  proof photos come back.
- The plugin has no hooks, scripts or local commands, and contacts no other
  service.

## Links

- Privacy policy: <https://mundane.market/policies/privacy>
- Terms of service: <https://mundane.market/policies/terms>
- Source, and the self-hosted adapter: <https://github.com/sttruji/mundane-mcp>
