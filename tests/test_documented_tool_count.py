"""The advertised tool count matches reality, everywhere it is written down.

Both the package README and the public /for-agents page quote a tool count as a
selling point. Both had silently drifted — the README claimed fourteen tools and
the website claimed thirteen while the server actually registered twenty-one.
That page is prerendered and indexed, so a stale number is now a factual error in
the primary demand-side landing page rather than a private docs nit.
"""

import re
import unittest
from pathlib import Path

from mcp_server import server

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "mcp_server" / "README.md"
FOR_AGENTS = REPO_ROOT / "web" / "src" / "pages" / "ForAgents.tsx"
LANDING = REPO_ROOT / "web" / "src" / "pages" / "Landing.tsx"

NUMBER_WORDS = {
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty-one": 21,
    "twenty-two": 22,
    "twenty-three": 23,
    "twenty-four": 24,
    "twenty-five": 25,
}
WORD_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")\s+(?:MCP\s+)?tools\b",
    re.IGNORECASE,
)


class DocumentedToolCountTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.actual = len(await server.mcp.list_tools())

    def _documented(self, path: Path) -> list[int]:
        matches = WORD_PATTERN.findall(path.read_text(encoding="utf-8"))
        self.assertTrue(
            matches,
            f"{path.relative_to(REPO_ROOT)} no longer states a tool count; either "
            "restore the claim or drop this file from the check",
        )
        return [NUMBER_WORDS[m.lower()] for m in matches]

    async def test_registered_tool_count_is_stable(self):
        # Guards against an accidental duplicate or dropped @mcp.tool().
        self.assertEqual(self.actual, 21)

    async def test_readme_states_the_real_count(self):
        for claimed in self._documented(README):
            self.assertEqual(claimed, self.actual)

    async def test_public_pages_state_the_real_count(self):
        for path in (FOR_AGENTS, LANDING):
            for claimed in self._documented(path):
                self.assertEqual(
                    claimed,
                    self.actual,
                    f"{path.relative_to(REPO_ROOT)} advertises {claimed} tools, "
                    f"server registers {self.actual}",
                )


if __name__ == "__main__":
    unittest.main()
