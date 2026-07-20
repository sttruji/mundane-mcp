"""MCP contract for immediate-execution worker discovery."""

import unittest
from unittest.mock import AsyncMock, patch

from mcp_server import server


class WorkerPresenceToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_search_workers_exposes_live_now_with_safe_default(self):
        schema = self.tools["search_workers"].inputSchema
        self.assertEqual(schema["properties"]["live_now"]["default"], False)
        self.assertNotIn("live_now", schema.get("required", []))

    async def test_worker_tools_explain_presence_fields_and_urgency(self):
        search = self.tools["search_workers"].description
        detail = self.tools["get_worker"].description
        self.assertIn("immediate execution", search)
        self.assertIn("live_now=true", search)
        for description in (search, detail):
            self.assertIn("live_now", description)
            self.assertIn("live_until", description)

    async def test_search_workers_forwards_live_filter(self):
        with patch.object(
            server, "_request", new_callable=AsyncMock, return_value=[]
        ) as request:
            result = await server.search_workers(37.2, -122.1, live_now=True)

        self.assertEqual(result, [])
        request.assert_awaited_once()
        self.assertEqual(request.await_args.args, ("GET", "/workers"))
        self.assertIs(request.await_args.kwargs["params"]["live_now"], True)


if __name__ == "__main__":
    unittest.main()
