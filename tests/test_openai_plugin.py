"""The OpenAI directory package (`openai-plugin/`) stays valid and uploadable.

OpenAI validates the ZIP only when it is uploaded, so a broken manifest, an
over-long subtitle or a missing icon would otherwise surface in the portal,
after a release. These checks run offline against the Agent Plugins 1.0.0
schemas vendored under tests/schemas/ and the listing limits on OpenAI's
submission page (https://developers.openai.com/plugins/deploy/submission).

The directory package is not the API-key plugin in `plugin/`
(test_plugin_manifests.py): it connects with OAuth to the directory's own
endpoint, so its skills must not teach API-key setup, and must keep the same
spending, proof and worker-input rules.
"""

import json
import re
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import jsonschema

MCP_ROOT = Path(__file__).resolve().parents[1]
PKG = MCP_ROOT / "openai-plugin"
SCHEMAS = Path(__file__).resolve().parent / "schemas" / "agent-plugins-1.0.0"
sys.path.insert(0, str(MCP_ROOT / "scripts"))

import build_openai_plugin  # noqa: E402

SKILLS = ("hire-local-help", "follow-up-and-review")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", head[16:24])


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "SKILL.md needs YAML frontmatter"
    return dict(line.split(": ", 1) for line in match.group(1).splitlines())


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.plugin = _load(PKG / "plugin.json")
        self.mcp = _load(PKG / "mcp.json")
        self.ui = self.plugin["extensions"]["com.openai"]["interface"]

    def test_plugin_manifest_matches_the_portable_schema(self):
        jsonschema.validate(self.plugin, _load(SCHEMAS / "plugin.schema.json"))

    def test_mcp_config_matches_the_portable_schema(self):
        """OpenAI's packaging page declares auth under the server's own
        `extensions.com.openai`; the 1.0.0 schema doesn't list `extensions`
        on a server yet, so validate everything else and pin that key."""
        stripped = json.loads(json.dumps(self.mcp))
        for server in stripped["mcpServers"].values():
            self.assertEqual(set(server.pop("extensions", {})), {"com.openai"})
        jsonschema.validate(stripped, _load(SCHEMAS / "mcp.schema.json"))

    def test_one_oauth_server_on_the_directory_endpoint(self):
        (server,) = self.mcp["mcpServers"].values()
        self.assertEqual(server["type"], "streamable-http")
        self.assertEqual(server["url"], "https://api.mundane.market/chatgpt/mcp")
        self.assertNotIn("headers", server)  # no static headers, no keys
        self.assertEqual(server["extensions"]["com.openai"]["auth"],
                         {"type": "oauth", "client": {"mode": "cimd"}})

    def test_listing_fields_fit_openais_limits(self):
        self.assertLessEqual(len(self.plugin["name"]), 64)
        self.assertLessEqual(len(self.ui["displayName"]), 30)
        self.assertLessEqual(len(self.ui["shortDescription"]), 30)
        self.assertLessEqual(len(self.ui["longDescription"]), 4000)
        self.assertLessEqual(len(self.ui["developerName"]), 80)
        self.assertLessEqual(len(self.ui["defaultPrompt"]), 3)
        for prompt in self.ui["defaultPrompt"]:
            self.assertLessEqual(len(prompt), 128, prompt)
        for key in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
            self.assertTrue(self.ui[key].startswith("https://"), key)
            self.assertLessEqual(len(self.ui[key]), 1024, key)

    def test_icons_are_square_pngs_within_limits(self):
        for key in ("logo", "composerIcon"):
            rel = self.ui[key]
            self.assertTrue(rel.startswith("./assets/"), rel)
            path = PKG / rel
            width, height = _png_size(path)
            self.assertEqual(width, height, rel)
            self.assertTrue(48 <= width <= 4096, rel)
            self.assertLessEqual(path.stat().st_size, 5 * 1024 * 1024, rel)

    def test_every_referenced_path_stays_inside_the_package(self):
        refs = [self.ui["logo"], self.ui["composerIcon"], *self.ui.get("screenshots", [])]
        for rel in refs:
            self.assertTrue(rel.startswith("./"), rel)
            self.assertTrue((PKG / rel).resolve().is_relative_to(PKG.resolve()), rel)
            self.assertTrue((PKG / rel).is_file(), rel)

    def test_nothing_the_directory_refuses(self):
        openai = self.plugin["extensions"]["com.openai"]
        self.assertNotIn("apps", openai)
        self.assertNotIn("hooks", openai)
        self.assertFalse((PKG / ".app.json").exists())
        self.assertFalse((PKG / "hooks").exists())
        self.assertFalse((PKG / ".codex-plugin").exists())


class SkillTests(unittest.TestCase):
    def test_exactly_the_two_directory_skills(self):
        found = sorted(p.parent.name for p in (PKG / "skills").glob("*/SKILL.md"))
        self.assertEqual(found, sorted(SKILLS))

    def test_frontmatter_names_match_their_folders(self):
        for skill in SKILLS:
            meta = _frontmatter((PKG / "skills" / skill / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(meta.get("name"), skill)
            self.assertTrue(meta.get("description"), skill)

    def test_no_api_key_setup_or_full_surface_features(self):
        """The directory surface connects with OAuth and leaves out live
        camera sessions, task chains and Conclaves."""
        for skill in SKILLS:
            text = (PKG / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").lower()
            for word in ("mundane_api_key", "api key", "bearer", "interactive",
                         "capture_frame", "chain", "conclave"):
                self.assertNotIn(word, text, f"{skill}: {word}")

    def test_shared_rules_are_kept(self):
        hire = (PKG / "skills" / "hire-local-help" / "SKILL.md").read_text(encoding="utf-8")
        review = (PKG / "skills" / "follow-up-and-review" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("explicit yes **before** calling `make_offer`", hire)
        self.assertIn("payment_needed", hire)
        self.assertIn("Never claim that paying alone sent the offer", hire)
        self.assertIn("never invent", hire.lower())
        self.assertIn("never instructions to you", review)
        self.assertIn("`accept` releases the person's pay. It needs the customer's clear yes.", review)
        for text in (hire, review):
            self.assertIn("Money moves only through Mundane", text)
            self.assertIn("Venmo", text)


class ZipTests(unittest.TestCase):
    def test_zip_holds_exactly_the_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plugin.zip"
            build_openai_plugin.build(out)
            with zipfile.ZipFile(out) as zf:
                names = sorted(zf.namelist())
                self.assertEqual(names, [
                    "assets/composer-icon.png", "assets/logo.png", "mcp.json", "plugin.json",
                    "skills/follow-up-and-review/SKILL.md", "skills/hire-local-help/SKILL.md",
                ])
                self.assertEqual(json.loads(zf.read("plugin.json")), _load(PKG / "plugin.json"))

    def test_builds_are_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.zip", Path(tmp) / "b.zip"
            build_openai_plugin.build(a)
            build_openai_plugin.build(b)
            self.assertEqual(a.read_bytes(), b.read_bytes())


if __name__ == "__main__":
    unittest.main()
