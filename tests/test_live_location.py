"""MCP contract for task-scoped live worker location."""

import unittest
from unittest.mock import AsyncMock, patch

from mcp_server import server


class LiveLocationToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_post_task_exposes_request_flag_with_safe_default(self):
        schema = self.tools["post_task"].inputSchema
        self.assertEqual(
            schema["properties"]["request_live_location"]["default"], False,
        )
        self.assertNotIn("request_live_location", schema.get("required", []))

    async def test_post_task_documents_the_scope_contract(self):
        description = self.tools["post_task"].description
        self.assertIn("request_live_location", description)
        self.assertIn("accept", description.lower())

    async def test_get_worker_location_registered_and_documented(self):
        self.assertIn("get_worker_location", self.tools)
        schema = self.tools["get_worker_location"].inputSchema
        self.assertEqual(schema.get("required", []), ["task_id"])
        description = self.tools["get_worker_location"].description
        # The privacy contract must be spelled out for the agent.
        self.assertIn("active", description)
        self.assertIn("submi", description)  # submission cutoff
        self.assertIn("history", description)
        for state in ("not_requested", "pending", "awaiting_first_fix",
                      "active", "ended"):
            self.assertIn(state, description)

    async def test_post_task_forwards_request_flag(self):
        with patch.object(
            server, "_request", new_callable=AsyncMock,
            return_value={"task_id": "t", "status": "open"},
        ) as request:
            await server.post_task(
                title="t", instructions="i", lat=37.0, lng=-122.0,
                required_capabilities=["in_person_errand"],
                budget_max_minor=5000, deadline="2026-12-31T00:00:00Z",
                request_live_location=True,
            )
        body = request.await_args.kwargs["json"]
        self.assertIs(body["request_live_location"], True)

    async def test_get_worker_location_calls_endpoint(self):
        with patch.object(
            server, "_request", new_callable=AsyncMock,
            return_value={"task_id": "abc", "sharing": "active"},
        ) as request:
            result = await server.get_worker_location("abc")
        self.assertEqual(result["sharing"], "active")
        request.assert_awaited_once_with("GET", "/tasks/abc/live-location")


if __name__ == "__main__":
    unittest.main()
