# Mundane in OpenAI's plugin directory (ChatGPT and Codex)

This folder is the package uploaded to OpenAI's plugin directory, in the
portable [Agent Plugins](https://agent-plugins.org) format. It is **not** the
plugin in [`../plugin/`](../plugin/README.md):

| | `openai-plugin/` (this folder) | `plugin/` |
|---|---|---|
| Installed from | OpenAI's directory, in ChatGPT or Codex | `sttruji/mundane-mcp` marketplace, in Claude Code or Codex |
| Endpoint | `https://api.mundane.market/chatgpt/mcp` | `https://api.mundane.market/mcp` |
| Sign-in | OAuth: the customer connects their Mundane account | an agent API key |
| Tools | the customer-facing subset | all of them |
| Skills | `hire-local-help`, `follow-up-and-review` | `mundane` |

Install one or the other, not both: each one is a separate Mundane connection
with its own tools, and an agent with both sees the shared tools twice.

## Building the upload

```bash
python scripts/build_openai_plugin.py
```

writes `dist/mundane-openai-plugin-<version>.zip` holding only `plugin.json`,
`mcp.json`, the skills and the icons; this README stays out of it.
`tests/test_openai_plugin.py` validates the manifests against the Agent
Plugins 1.0.0 schemas (vendored in `tests/schemas/`) and OpenAI's listing
limits, and checks the ZIP's exact contents.

Never put credentials in this folder. Reviewer credentials go in the
submission form's review details, never in the package.

## The auth declaration

`mcp.json` declares OAuth with a Client ID Metadata Document as OpenAI's
packaging page shows it, under the server's `extensions.com.openai.auth`. The
Agent Plugins 1.0.0 schema doesn't list `extensions` on a server yet, so the
test validates the rest and pins that one key. The portal also discovers the
OAuth server from `/.well-known/oauth-protected-resource` on the endpoint;
after uploading, check that it imported OAuth with CIMD and nothing else.
