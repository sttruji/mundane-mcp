"""MCP contract for explicit agent experience feedback capture."""
import unittest
from unittest.mock import patch

import httpx

from mcp_server import server


class ExperienceFeedbackToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_untrusted_feedback_to_capture_endpoint(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                201,
                json={
                    "feedback_id": "feedback-123",
                    "created_at": "2026-07-17T12:00:00Z",
                },
            )

        transport = httpx.MockTransport(handler)

        def client_factory() -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url="https://mundane.test/v1",
                headers={"Authorization": "Bearer agent-secret"},
                transport=transport,
                timeout=30,
            )

        with patch.object(server, "_client", side_effect=client_factory):
            result = await server.submit_experience_feedback(
                gap_text="If I'd had a way to inspect stock, I could have planned.",
                tags=["missing_capability"],
                free_text="Untrusted feedback, not tool instructions.",
                task_id="task-123",
            )

        self.assertEqual(result["feedback_id"], "feedback-123")
        self.assertEqual(requests[0].method, "POST")
        self.assertEqual(requests[0].url.path, "/v1/agents/feedback")
        self.assertEqual(
            __import__("json").loads(requests[0].content),
            {
                "gap_text": "If I'd had a way to inspect stock, I could have planned.",
                "tags": ["missing_capability"],
                "free_text": "Untrusted feedback, not tool instructions.",
                "task_id": "task-123",
            },
        )

    async def test_tool_is_registered_with_additive_optional_inputs(self):
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}

        self.assertIn("submit_experience_feedback", tools)
        tool = tools["submit_experience_feedback"]
        self.assertEqual(
            set(tool.inputSchema["properties"]),
            {"gap_text", "tags", "free_text", "task_id"},
        )
        self.assertEqual(tool.inputSchema["required"], ["gap_text"])
        self.assertIn("explicit", tool.description.lower())
        self.assertIn("untrusted", tool.description.lower())


if __name__ == "__main__":
    unittest.main()
