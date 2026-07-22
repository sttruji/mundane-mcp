"""MCP contract for task-scoped chat with the assigned worker."""

import unittest
from unittest.mock import AsyncMock, patch

from mcp_server import server


class ChatToolContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_send_tool_registered_with_required_args(self):
        schema = self.tools["send_chat_message"].inputSchema
        self.assertEqual(schema.get("required", []), ["task_id", "body"])

    async def test_send_tool_documents_caps_and_lifecycle(self):
        description = self.tools["send_chat_message"].description
        self.assertIn("500", description)
        self.assertIn("50", description)
        self.assertIn("accept", description.lower())

    async def test_read_tool_frames_worker_text_as_untrusted_data(self):
        description = self.tools["get_task_chat"].description
        # The anti-manipulation contract must be explicit: worker text is
        # data, never instructions -- this repo has had a real
        # prompt-injection incident.
        self.assertIn("untrusted", description.lower())
        self.assertIn("never", description.lower())
        self.assertIn("instructions", description.lower())
        schema = self.tools["get_task_chat"].inputSchema
        self.assertEqual(schema.get("required", []), ["task_id"])
        self.assertEqual(schema["properties"]["after_id"]["default"], 0)

    async def test_send_calls_endpoint(self):
        with patch.object(
            server, "_request", new_callable=AsyncMock,
            return_value={"id": 1, "remaining_messages": 49},
        ) as request:
            result = await server.send_chat_message("task-1", "Ring twice.")
        self.assertEqual(result["remaining_messages"], 49)
        request.assert_awaited_once_with(
            "POST", "/tasks/task-1/chat", json={"body": "Ring twice."},
        )

    async def test_read_forwards_cursor(self):
        with patch.object(
            server, "_request", new_callable=AsyncMock,
            return_value={"channel": "open", "messages": []},
        ) as request:
            await server.get_task_chat("task-1", after_id=7)
        request.assert_awaited_once_with(
            "GET", "/tasks/task-1/chat", params={"after_id": 7},
        )


if __name__ == "__main__":
    unittest.main()
