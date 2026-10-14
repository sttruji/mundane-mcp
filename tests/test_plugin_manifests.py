"""The Claude Code and Codex plugins are one plugin folder with two manifests.

`plugin/` carries `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`
over a shared skill, so the two cannot teach agents different rules. What they
can still do is drift apart in the fields each one duplicates. A version bump
applied to one manifest strands the other's users on a stale skill (both CLIs
keep a user on a version until it changes), and a URL changed in one sends half
of the installs somewhere else. Nothing in either CLI would notice.

The Codex server config deliberately lives in `codex.mcp.json`, not `.mcp.json`:
Claude Code also loads a `.mcp.json` from a plugin's root, and would register a
second, differently-authenticated copy of the server.
"""

import json
import unittest
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[1]
PLUGIN = MCP_ROOT / "plugin"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class PluginManifestTests(unittest.TestCase):
    def setUp(self):
        self.claude = _load(PLUGIN / ".claude-plugin" / "plugin.json")
        self.codex = _load(PLUGIN / ".codex-plugin" / "plugin.json")

    def test_versions_move_together(self):
        self.assertEqual(self.claude["version"], self.codex["version"])

    def test_shared_identity_fields_agree(self):
        for field in ("name", "description", "homepage", "repository", "license"):
            self.assertEqual(self.claude[field], self.codex[field], field)

    def test_both_point_at_the_same_hosted_endpoint(self):
        claude_url = self.claude["mcpServers"]["mundane"]["url"]
        codex = _load(PLUGIN / self.codex["mcpServers"])["mcpServers"]["mundane"]
        self.assertEqual(codex["url"], claude_url)
        self.assertEqual(codex["type"], "http")

    def test_codex_reads_the_key_from_the_environment(self):
        """Codex has no prompt-for-a-secret field like Claude Code's userConfig;
        the key comes from the user's environment and is never in the package."""
        codex = _load(PLUGIN / self.codex["mcpServers"])["mcpServers"]["mundane"]
        self.assertEqual(codex["bearer_token_env_var"], "MUNDANE_API_KEY")
        self.assertNotIn("http_headers", codex)

    def test_codex_server_config_is_not_where_claude_code_looks(self):
        self.assertNotEqual(self.codex["mcpServers"], "./.mcp.json")
        self.assertFalse((PLUGIN / ".mcp.json").exists())

    def test_paths_the_codex_manifest_names_exist(self):
        for rel in (self.codex["skills"], self.codex["mcpServers"],
                    self.codex["interface"]["logo"], self.codex["interface"]["composerIcon"]):
            self.assertTrue((PLUGIN / rel).exists(), rel)

    def test_codex_marketplace_lists_the_shared_folder(self):
        market = _load(MCP_ROOT / ".agents" / "plugins" / "marketplace.json")
        (entry,) = market["plugins"]
        self.assertEqual(entry["name"], self.codex["name"])
        self.assertEqual((MCP_ROOT / entry["source"]["path"]).resolve(), PLUGIN.resolve())
        # Bearer-key auth works in Codex but not in ChatGPT, which offers only
        # OAuth or no auth; the ChatGPT plugin is docs/plans/chatgpt-plugin.md.
        self.assertEqual(entry["policy"]["products"], ["CODEX"])


if __name__ == "__main__":
    unittest.main()
