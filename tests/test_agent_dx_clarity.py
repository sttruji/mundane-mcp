"""MCP tool metadata states money/time units and caller identity clearly."""

import unittest

from mcp_server import server


class AgentDxToolDescriptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_worker_tools_define_ask_rate_basis(self):
        phrase = "minimum per-task price in minor units"
        self.assertIn(phrase, self.tools["search_workers"].description)
        self.assertIn(phrase, self.tools["get_worker"].description)

    async def test_worker_tools_explain_advisory_rate_card(self):
        for name in ("search_workers", "get_worker"):
            description = self.tools[name].description
            self.assertIn("rate_card", description)
            self.assertIn("advisory", description)
            self.assertIn("offer at least", description)

    async def test_spend_status_explains_caller_identity(self):
        description = self.tools["get_spend_status"].description
        self.assertIn("authenticated agent", description)
        self.assertIn("principal", description)

    async def test_task_and_offer_tools_define_units(self):
        task = self.tools["post_task"].description
        offer = self.tools["make_offer"].description
        self.assertIn("budget_max_minor", task)
        self.assertIn("minor units", task)
        self.assertIn("ISO 8601", task)
        self.assertIn("amount_minor", offer)
        self.assertIn("minor units", offer)
        self.assertIn("expires_in_seconds", offer)


if __name__ == "__main__":
    unittest.main()
