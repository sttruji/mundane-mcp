"""Published dependency constraints stay compatible with what we actually test.

Two files describe this package's dependencies and only one of them reaches
end users:

  - requirements.txt pins exact versions, and builds the Docker image.
  - pyproject.toml's `dependencies` are what `pip install mundane-mcp` resolves.

Because pyproject declared an unbounded `mcp>=1.2`, the MCP SDK's 2.0.0 release
(which removed `mcp.server.fastmcp`) broke every fresh pip install from 0.1.7
onward with a ModuleNotFoundError on import. Docker users saw nothing, the test
suite ran against the pinned SDK and stayed green, and the failure only appeared
in a clean-room install — which is how it went unnoticed through a release.

These tests make the two files disagree loudly instead.
"""

import re
import tomllib
import unittest
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = MCP_ROOT / "pyproject.toml"
REQUIREMENTS = MCP_ROOT / "requirements.txt"

# Anything whose next major version can move the imports server.py performs.
# Pillow is intentionally absent: it is used through a narrow, stable surface.
MUST_BE_CAPPED = {"mcp", "httpx"}


def _parse_requirement(spec: str) -> tuple[str, str]:
    """'mcp>=1.2,<2' -> ('mcp', '>=1.2,<2')"""
    match = re.match(r"^([A-Za-z0-9._-]+)\s*(.*)$", spec.strip())
    assert match, f"unparseable requirement: {spec!r}"
    return match.group(1).lower(), match.group(2).strip()


def _pinned_versions() -> dict[str, str]:
    """Exact pins from the hash-locked requirements file."""
    pins: dict[str, str] = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9._-]+)==([0-9][^\s\\;]*)", line)
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


class DependencyBoundsTests(unittest.TestCase):
    def setUp(self):
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        self.declared = dict(
            _parse_requirement(spec) for spec in data["project"]["dependencies"]
        )
        self.pinned = _pinned_versions()

    def test_import_critical_dependencies_have_an_upper_bound(self):
        for name in MUST_BE_CAPPED:
            self.assertIn(name, self.declared, f"{name} is no longer a dependency")
            constraint = self.declared[name]
            self.assertIn(
                "<",
                constraint,
                f"'{name}{constraint}' is unbounded — the next major release can "
                f"break `pip install mundane-mcp` while Docker and CI stay green",
            )

    def test_pinned_version_satisfies_the_published_constraint(self):
        # A cap tighter than what we build and test against is just as broken as
        # no cap: users would resolve a version the suite never exercised.
        for name, constraint in self.declared.items():
            pinned = self.pinned.get(name)
            if pinned is None:
                continue
            upper = re.search(r"<\s*([0-9][^\s,]*)", constraint)
            if not upper:
                continue
            pinned_major = int(pinned.split(".")[0])
            upper_major = int(upper.group(1).split(".")[0])
            self.assertLess(
                pinned_major,
                upper_major,
                f"requirements.txt pins {name}=={pinned} but pyproject caps it at "
                f"<{upper.group(1)}; the tested version is outside what users get",
            )

    def test_mcp_cap_excludes_the_sdk_major_that_removed_fastmcp(self):
        # Specific regression: server.py imports mcp.server.fastmcp, gone in 2.0.0.
        self.assertRegex(self.declared["mcp"], r"<\s*2(\.|$|,)")


if __name__ == "__main__":
    unittest.main()
