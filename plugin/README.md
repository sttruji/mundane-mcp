# Mundane plugin for Claude Code

Mundane is a marketplace where AI agents hire ID-verified local people for
real-world tasks: photos of a property, a pickup, a shelf check, a place in
line. Payment is held in escrow and released only when you approve the
worker's proof, and every task is screened against Mundane's Acceptable Use
Policy before a person sees it.

This plugin gives Claude two things:

- **The Mundane MCP server** (35 tools), hosted by Mundane at
  `https://api.mundane.market/mcp`. Nothing runs on your machine.
- **A skill** that teaches Claude to use those tools well: confirm spending
  with you, review proof before releasing payment, run live camera sessions,
  and treat anything a worker writes as data, never as instructions.

## Install

```bash
claude plugin marketplace add sttruji/mundane-mcp
claude plugin install mundane@mundane
```

Then, inside Claude Code, run `/plugin configure mundane@mundane` and paste
your agent key. Get one free at https://mundane.market/for-agents; searching
for workers needs no funded wallet.

## What it sends, and where

- Your agent key goes only to `api.mundane.market`, as the `Authorization`
  header of each MCP request. Claude Code keeps it in your system keychain.
- Tool calls send what you ask Claude to send: task locations, instructions,
  budgets, offers, chat messages and reviews. Worker profiles, task status and
  proof photos come back.
- The plugin has no hooks, scripts or local commands, and contacts no other
  service.

Privacy policy: https://mundane.market/policies/privacy. Terms:
https://mundane.market/policies/terms. Source and the self-hosted adapter:
https://github.com/sttruji/mundane-mcp
