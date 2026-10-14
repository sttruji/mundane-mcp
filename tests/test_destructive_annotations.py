"""Every tool whose effect can't be taken back says so.

Clients decide what to confirm with a person from destructiveHint, and
OpenAI's directory review reads it too. Holding money, sending a worker a
message or a picture, approving proof (which releases pay), rating a person
publicly, and overwriting what an offered worker sees are all irreversible;
0.1.20 declared them non-destructive. Additive, private actions (posting a
draft task, creating a chain) stay non-destructive.
"""
import asyncio

from mcp_server import server

DESTRUCTIVE = {
    "make_offer", "offer_chain_link", "send_chat_message", "show_worker_image",
    "attach_task_file", "submit_completion_review", "submit_rating", "update_task",
    "reschedule_chain_handoff", "cancel_task", "end_task_chain", "cancel_checkpoint",
}


def test_irreversible_tools_are_marked_destructive():
    tools = {t.name: t.annotations for t in asyncio.run(server.mcp.list_tools())}
    assert DESTRUCTIVE <= set(tools)
    marked = {name for name, a in tools.items() if a.destructiveHint}
    assert marked == DESTRUCTIVE


def test_a_destructive_tool_is_never_read_only():
    for t in asyncio.run(server.mcp.list_tools()):
        if t.annotations.destructiveHint:
            assert t.annotations.readOnlyHint is False, t.name
