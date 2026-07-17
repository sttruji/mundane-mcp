"""MCP contract for bounded task-status long polling."""

import unittest
from unittest.mock import patch

import httpx

from mcp_server import server


API_BASE = "https://mundane.test/v1"


class AwaitTaskUpdateToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_wait_timeout_and_returns_task_payload(self):
        requests: list[httpx.Request] = []
        expected = {
            "task_id": "task-123",
            "status": "submitted",
            "offer": None,
            "worker": None,
            "completion": {"proof": []},
            "timeline": [],
            "changed": True,
        }

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=expected)

        transport = httpx.MockTransport(handler)

        def client_factory() -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url=API_BASE,
                headers={"Authorization": "Bearer agent-secret"},
                transport=transport,
                timeout=30,
            )

        with patch.object(server, "_client", side_effect=client_factory):
            result = await server.await_task_update("task-123", timeout_seconds=12)

        self.assertEqual(result, expected)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.path, "/v1/tasks/task-123")
        self.assertEqual(requests[0].url.params["wait_for_change"], "12")
        self.assertEqual(requests[0].headers["authorization"], "Bearer agent-secret")
        self.assertGreaterEqual(requests[0].extensions["timeout"]["read"], 17)

    async def test_caps_wait_and_http_timeout_below_proxy_ceiling(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"task_id": "task-123", "status": "open", "changed": False},
            )

        transport = httpx.MockTransport(handler)

        def client_factory() -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url=API_BASE,
                headers={"Authorization": "Bearer agent-secret"},
                transport=transport,
                timeout=30,
            )

        with patch.object(server, "_client", side_effect=client_factory):
            result = await server.await_task_update("task-123", timeout_seconds=999)

        self.assertFalse(result["changed"])
        self.assertEqual(requests[0].url.params["wait_for_change"], "55.0")
        self.assertEqual(requests[0].extensions["timeout"]["read"], 60.0)

    async def test_tool_is_registered_with_expected_inputs(self):
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}

        self.assertIn("await_task_update", tools)
        schema = tools["await_task_update"].inputSchema
        self.assertEqual(set(schema["properties"]), {"task_id", "timeout_seconds"})
        self.assertEqual(schema["required"], ["task_id"])


if __name__ == "__main__":
    unittest.main()
