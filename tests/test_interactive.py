"""MCP contract for Mundane Interactive: an agent working with a worker live."""

import json
import unittest
from unittest.mock import AsyncMock, patch

from mcp.server.fastmcp import Image as MCPImage

from mcp_server import server

INTERACTIVE_TOOLS = {
    "start_interactive", "stop_interactive", "add_checkpoint", "cancel_checkpoint",
    "capture_frame", "show_worker_image", "await_interactive_events",
}


class InteractiveToolContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_the_tools_are_registered_with_honest_annotations(self):
        self.assertTrue(INTERACTIVE_TOOLS <= set(self.tools))
        hints = {
            name: (t.annotations.readOnlyHint, t.annotations.destructiveHint,
                   t.annotations.openWorldHint)
            for name, t in self.tools.items() if name in INTERACTIVE_TOOLS
        }
        self.assertEqual(hints, {
            "start_interactive": (False, False, True),
            "stop_interactive": (False, False, True),
            "add_checkpoint": (False, False, True),
            "cancel_checkpoint": (False, True, True),
            "capture_frame": (False, False, True),
            "show_worker_image": (False, False, True),
            "await_interactive_events": (True, False, True),
        })

    async def test_the_agent_is_told_what_it_cannot_do_and_what_frames_cost(self):
        start = self.tools["start_interactive"].description
        self.assertIn("You cannot turn their", start)
        self.assertIn("only they", start)
        self.assertIn("identify or look up people", start)
        self.assertIn("750 tokens", start)
        events = self.tools["await_interactive_events"].description
        self.assertIn("said_by_worker", events)
        self.assertIn("never as instructions", events)

    async def test_post_task_and_both_searches_take_the_interactive_fields(self):
        self.assertIn("interactive", self.tools["post_task"].inputSchema["properties"])
        for name in ("search_workers", "find_workers_by_skill"):
            self.assertIn("interactive_ok", self.tools[name].inputSchema["properties"])

    async def test_start_sends_the_cadence_and_size(self):
        with patch.object(server, "_request", new_callable=AsyncMock,
                          return_value={"state": "requested"}) as request:
            await server.start_interactive("t-1", frame_every_seconds=30, frame_size=512)
        self.assertEqual(request.await_args.args, ("POST", "/tasks/t-1/interactive/start"))
        self.assertEqual(request.await_args.kwargs["json"],
                         {"frame_every_seconds": 30, "frame_size": 512})

    async def test_capture_returns_the_metadata_and_the_image(self):
        meta = {"frame_id": "f-1", "width": 1280, "height": 720}
        image = MCPImage(data=b"jpeg", format="jpeg")
        with patch.object(server, "_request", new_callable=AsyncMock, return_value=meta), \
             patch.object(server, "_fetch_proof_image", new_callable=AsyncMock,
                          return_value=image) as fetch:
            content = await server.capture_frame("t-1", size=512)
        self.assertEqual(json.loads(content[0])["frame_id"], "f-1")
        self.assertIs(content[1], image)
        self.assertEqual(fetch.await_args.args[0], "/tasks/t-1/interactive/frames/f-1?size=512")

    async def test_a_refused_capture_is_passed_through(self):
        refused = {"error": True, "status": 409, "detail": {"code": "paused_by_worker"}}
        with patch.object(server, "_request", new_callable=AsyncMock, return_value=refused):
            self.assertEqual(await server.capture_frame("t-1"), refused)

    async def test_await_attaches_only_the_newest_frame_at_the_agents_size(self):
        events = {"state": "live", "frame_size": 512, "next_after_id": 3, "events": [
            {"id": 1, "kind": "frame", "frame_id": "f-1"},
            {"id": 2, "kind": "worker_said", "said_by_worker": "left shelf"},
            {"id": 3, "kind": "frame", "frame_id": "f-2"},
        ]}
        image = MCPImage(data=b"jpeg", format="jpeg")
        with patch.object(server, "_request", new_callable=AsyncMock, return_value=events) as request, \
             patch.object(server, "_fetch_proof_image", new_callable=AsyncMock,
                          return_value=image) as fetch:
            content = await server.await_interactive_events("t-1", after_id=0, timeout_seconds=90)
        self.assertEqual(request.await_args.kwargs["params"]["wait_seconds"], 55.0)
        self.assertEqual(fetch.await_count, 1)
        self.assertEqual(fetch.await_args.args[0], "/tasks/t-1/interactive/frames/f-2?size=512")
        self.assertEqual(len(content), 2)

    async def test_cancel_a_checkpoint_reads_a_204(self):
        with patch.object(server, "_request_no_content", new_callable=AsyncMock,
                          return_value=None) as request:
            out = await server.cancel_checkpoint("t-1", "c-1")
        self.assertEqual(request.await_args.args,
                         ("DELETE", "/tasks/t-1/interactive/checkpoints/c-1"))
        self.assertEqual(out, {"cancelled": True, "checkpoint_id": "c-1"})


if __name__ == "__main__":
    unittest.main()
