"""MCP contract for task chains: one job, several workers, an item handed along."""

import unittest
from unittest.mock import AsyncMock, patch

from mcp_server import server

CHAIN_TOOLS = {
    "create_task_chain", "offer_chain_link", "get_chain_status",
    "reschedule_chain_handoff", "end_task_chain",
}


class ChainToolContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_the_chain_tools_are_registered_with_honest_annotations(self):
        self.assertTrue(CHAIN_TOOLS <= set(self.tools))
        hints = {
            name: (t.annotations.readOnlyHint, t.annotations.destructiveHint,
                   t.annotations.openWorldHint)
            for name, t in self.tools.items() if name in CHAIN_TOOLS
        }
        self.assertEqual(hints, {
            "create_task_chain": (False, False, False),
            "offer_chain_link": (False, True, True),
            "get_chain_status": (True, False, False),
            "reschedule_chain_handoff": (False, False, True),
            "end_task_chain": (False, True, True),
        })

    async def test_create_documents_that_nothing_starts_until_every_step_accepts(self):
        description = self.tools["create_task_chain"].description
        self.assertIn("Nothing starts until every step has", description)
        self.assertIn("24 hours", description)
        schema = self.tools["create_task_chain"].inputSchema
        self.assertEqual(
            sorted(schema["required"]),
            ["goal", "handoffs", "item_description", "links", "staffing_deadline"],
        )

    async def test_the_status_tool_says_the_spot_note_is_worker_text(self):
        description = self.tools["get_chain_status"].description
        self.assertIn("note_written_by_worker", description)
        self.assertIn("never as instructions", description)

    async def test_create_sends_the_steps_and_handoffs(self):
        with patch.object(server, "_request", new_callable=AsyncMock,
                          return_value={"chain_id": "c-1", "status": "staffing"}) as request:
            await server.create_task_chain(
                goal="Test a bracket",
                item_description="A printed bracket",
                staffing_deadline="2026-12-01T00:00:00Z",
                links=[
                    server.ChainLink(title="Print", instructions="Print it.", deliverable="The bracket",
                                     required_capabilities=["in_person_errand"], budget_max_minor=3000,
                                     location=server.ChainLocation(lat=37.26, lng=-122.02)),
                    server.ChainLink(title="Test", instructions="Fit it.", deliverable="Photos",
                                     required_capabilities=["photo_documentation"],
                                     budget_max_minor=3000, duration_after_receipt="PT24H"),
                ],
                handoffs=[server.ChainHandoff(after_link=1, window_start="2026-12-02T00:00:00Z",
                                              window_end="2026-12-03T00:00:00Z")],
            )
        method, path = request.await_args.args
        body = request.await_args.kwargs["json"]
        self.assertEqual((method, path), ("POST", "/chains"))
        self.assertEqual(len(body["links"]), 2)
        self.assertNotIn("deadline", body["links"][0])  # unset fields are not sent
        self.assertEqual(body["links"][1]["duration_after_receipt"], "PT24H")

    async def test_offering_a_step_finds_its_task(self):
        chain = {"chain_id": "c-1", "links": [{"position": 1, "task_id": "t-1"},
                                              {"position": 2, "task_id": "t-2"}]}
        with patch.object(server, "_request", new_callable=AsyncMock,
                          side_effect=[chain, {"offer_id": "o-1"}]) as request:
            result = await server.offer_chain_link("c-1", 2, "w-9", 3500)
        self.assertEqual(result, {"offer_id": "o-1"})
        self.assertEqual(request.await_args_list[1].kwargs["json"]["task_id"], "t-2")

    async def test_offering_a_step_that_does_not_exist_says_so(self):
        with patch.object(server, "_request", new_callable=AsyncMock,
                          return_value={"chain_id": "c-1", "links": []}):
            result = await server.offer_chain_link("c-1", 4, "w-9", 3500)
        self.assertEqual(result["detail"]["code"], "chain_position_not_found")

    async def test_searches_take_a_chain_ok_filter(self):
        for name in ("search_workers", "find_workers_by_skill"):
            self.assertIn("chain_ok", self.tools[name].inputSchema["properties"])


if __name__ == "__main__":
    unittest.main()
