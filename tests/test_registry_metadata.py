"""server.json agrees with every other place the registry identity is written.

The official MCP Registry proves you own a package by re-reading the artifact:
for PyPI it greps the published README for `mcp-name: $SERVER_NAME`, and for the
OCI image it reads the `io.modelcontextprotocol.server.name` label. So the same
string is duplicated across server.json, README.md, and the Dockerfile, and the
version is duplicated across server.json and pyproject.toml.

Any drift fails at publish time with an opaque ownership error, after a release
has already gone out — and the fix requires another version bump because neither
PyPI nor the registry lets you overwrite. Cheaper to catch here.
"""

import json
import re
import tomllib
import unittest
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[1]
SERVER_JSON = MCP_ROOT / "server.json"
README = MCP_ROOT / "README.md"
DOCKERFILE = MCP_ROOT / "Dockerfile"
PYPROJECT = MCP_ROOT / "pyproject.toml"


class RegistryMetadataTests(unittest.TestCase):
    def setUp(self):
        self.server = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
        self.name = self.server["name"]
        self.version = self.server["version"]

    def test_server_json_has_required_fields(self):
        for field in ("name", "description", "version"):
            self.assertIn(field, self.server)
        for package in self.server["packages"]:
            for field in ("registryType", "identifier", "transport"):
                self.assertIn(field, package)
            self.assertEqual(package["transport"]["type"], "stdio")

    def test_name_uses_the_dns_namespace_we_verified(self):
        # DNS-authenticated namespaces are the reverse-DNS of the domain, so a
        # rename here silently requires a new TXT record on the apex.
        self.assertEqual(self.name, "market.mundane/mundane")

    def test_readme_carries_the_pypi_ownership_marker(self):
        readme = README.read_text(encoding="utf-8")
        # The registry requires a boundary after the name; a trailing period
        # glued to it defeats the match, so assert the exact comment form.
        self.assertIn(f"<!-- mcp-name: {self.name} -->", readme)

    def test_dockerfile_carries_the_oci_ownership_label(self):
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        match = re.search(
            r'LABEL\s+io\.modelcontextprotocol\.server\.name="([^"]+)"', dockerfile
        )
        self.assertIsNotNone(match, "Dockerfile is missing the registry LABEL")
        self.assertEqual(match.group(1), self.name)

    def test_version_matches_the_package_being_published(self):
        pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["version"], self.version)

    def test_each_package_pins_the_same_version(self):
        by_type = {p["registryType"]: p for p in self.server["packages"]}
        self.assertEqual(set(by_type), {"pypi", "oci"})

        self.assertEqual(by_type["pypi"]["identifier"], "mundane-mcp")
        self.assertEqual(by_type["pypi"]["version"], self.version)

        # An OCI identifier carries its version in the tag rather than a
        # `version` field, so :latest here would publish an entry that silently
        # drifts away from what the registry entry claims.
        self.assertEqual(
            by_type["oci"]["identifier"], f"ghcr.io/sttruji/mundane-mcp:{self.version}"
        )

    def test_api_key_is_declared_required_and_secret(self):
        for package in self.server["packages"]:
            env = {v["name"]: v for v in package["environmentVariables"]}
            self.assertIn("MUNDANE_API_KEY", env)
            self.assertTrue(env["MUNDANE_API_KEY"]["isRequired"])
            self.assertTrue(
                env["MUNDANE_API_KEY"]["isSecret"],
                "clients surface non-secret vars in plain text",
            )


if __name__ == "__main__":
    unittest.main()
