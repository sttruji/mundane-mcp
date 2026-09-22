"""Declared output schemas must never reject a real response.

FastMCP validates a tool's return value against its declared output schema and
raises if it does not match, so a wrong schema does not degrade a tool -- it
breaks it. The dangerous case is specific: `_request` hands back
`{"error": True, "status": <int>, "detail": ...}` verbatim on any 4xx/5xx, so
*every* tool can return that instead of its documented shape.

That bit once already. `status` is a task-status string on success and an HTTP
status int in the error envelope, and `error` is a message string on
get_version_info but a bool in the envelope. Both collisions made the error
path raise a ValidationError instead of surfacing the error to the agent.
"""
import asyncio

import pytest

from mcp_server import server as srv

ERROR_ENVELOPE = {
    "error": True,
    "status": 401,
    "detail": {"type": "about:blank", "code": "unauthorized",
               "detail": "Invalid API key"},
}


def _tools_with_schema():
    return [t.name for t in asyncio.run(srv.mcp.list_tools()) if t.outputSchema]


def test_some_tools_actually_declare_an_output_schema():
    """Guards the guard: if nothing declares a schema the rest is vacuous."""
    assert len(_tools_with_schema()) >= 10


@pytest.mark.parametrize("name", _tools_with_schema())
def test_the_error_envelope_survives_every_declared_schema(name):
    tool = srv.mcp._tool_manager.get_tool(name)
    # Raises rather than returns if the schema rejects it.
    tool.fn_metadata.convert_result(dict(ERROR_ENVELOPE))


@pytest.mark.parametrize("name", _tools_with_schema())
def test_every_declared_field_tolerates_null(name):
    """Real responses carry nulls -- a task with no offer yet, a worker who is
    not live. A field typed without `| None` would reject its own API."""
    tool = srv.mcp._tool_manager.get_tool(name)
    schema = tool.output_schema or {}
    all_null = {key: None for key in (schema.get("properties") or {})}
    tool.fn_metadata.convert_result(all_null)
