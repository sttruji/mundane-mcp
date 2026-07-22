"""MCP contract for the version / update-check meta tool."""

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from mcp_server import server


class VersionToolContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_tool_registered_with_no_required_arguments(self):
        self.assertIn("get_version_info", self.tools)
        schema = self.tools["get_version_info"].inputSchema
        self.assertEqual(schema.get("required", []), [])

    async def test_docstring_explains_fields_and_degraded_cases(self):
        description = self.tools["get_version_info"].description
        self.assertIn("installed_version", description)
        self.assertIn("latest_version", description)
        self.assertIn("update_available", description)
        self.assertIn("null", description)


class ReleaseTupleTests(unittest.TestCase):
    def test_parses_plain_releases(self):
        self.assertEqual(server._release_tuple("0.1.7"), (0, 1, 7))
        self.assertEqual(server._release_tuple("1.0"), (1, 0))

    def test_unparseable_versions_return_none(self):
        self.assertIsNone(server._release_tuple("0.2.0rc1"))
        self.assertIsNone(server._release_tuple(""))
        self.assertIsNone(server._release_tuple(None))

    def test_shorter_tuples_compare_correctly_when_padded(self):
        # 0.2 > 0.1.7 must hold once both sides are padded to equal length.
        older = server._release_tuple("0.1.7")
        newer = server._release_tuple("0.2")
        width = max(len(older), len(newer))
        pad = lambda t: t + (0,) * (width - len(t))  # noqa: E731
        self.assertGreater(pad(newer), pad(older))


class VersionInfoBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def _info(self, installed, latest, latest_error=None):
        with (
            patch.object(
                server, "_installed_mcp_version", return_value=installed,
            ),
            patch.object(
                server,
                "_fetch_latest_pypi_version",
                new_callable=AsyncMock,
                return_value=(latest, latest_error),
            ),
        ):
            return await server.get_version_info()

    async def test_update_available_when_pypi_is_ahead(self):
        info = await self._info("0.1.7", "0.2.0")
        self.assertEqual(info["installed_version"], "0.1.7")
        self.assertEqual(info["latest_version"], "0.2.0")
        self.assertIs(info["update_available"], True)
        self.assertIn("pip install --upgrade mundane-mcp", info["install_hint"])

    async def test_up_to_date_when_versions_match(self):
        info = await self._info("0.1.7", "0.1.7")
        self.assertIs(info["update_available"], False)
        self.assertNotIn("install_hint", info)

    async def test_dev_build_ahead_of_pypi_is_not_an_update(self):
        info = await self._info("0.2.0", "0.1.7")
        self.assertIs(info["update_available"], False)

    async def test_pypi_failure_degrades_to_null_with_error(self):
        info = await self._info("0.1.7", None, latest_error="PyPI check failed: timeout")
        self.assertEqual(info["installed_version"], "0.1.7")
        self.assertIsNone(info["latest_version"])
        self.assertIsNone(info["update_available"])
        self.assertIn("PyPI check failed", info["error"])

    async def test_missing_package_metadata_degrades_to_null_with_note(self):
        info = await self._info(None, "0.1.7")
        self.assertIsNone(info["installed_version"])
        self.assertIsNone(info["update_available"])
        self.assertIn("source", info["note"])

    async def test_unparseable_versions_never_guess(self):
        info = await self._info("0.2.0rc1", "0.1.7")
        self.assertIsNone(info["update_available"])


class PyPIFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_parses_info_version_and_sends_no_auth(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"info": {"version": "0.9.9"}})

        transport = httpx.MockTransport(handler)
        with (
            patch.object(server, "API_KEY", "super-secret-agent-key"),
            patch.object(server.httpx, "AsyncClient", _client_factory(transport)),
        ):
            latest, error = await server._fetch_latest_pypi_version()

        self.assertEqual(latest, "0.9.9")
        self.assertIsNone(error)
        self.assertEqual(seen["url"], "https://pypi.org/pypi/mundane-mcp/json")
        self.assertIsNone(seen["auth"])

    async def test_fetch_reports_http_error_status(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(503, text="unavailable")
        )
        with patch.object(server.httpx, "AsyncClient", _client_factory(transport)):
            latest, error = await server._fetch_latest_pypi_version()
        self.assertIsNone(latest)
        self.assertIn("503", error)

    async def test_fetch_reports_transport_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns failure")

        with patch.object(
            server.httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)),
        ):
            latest, error = await server._fetch_latest_pypi_version()
        self.assertIsNone(latest)
        self.assertIn("PyPI check failed", error)

    async def test_fetch_reports_malformed_body(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"unexpected": True})
        )
        with patch.object(server.httpx, "AsyncClient", _client_factory(transport)):
            latest, error = await server._fetch_latest_pypi_version()
        self.assertIsNone(latest)
        self.assertIn("malformed", error)


# Captured before any patching: server.httpx is this same module object, so
# the factory must not resolve AsyncClient through it while it is patched.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(transport: httpx.MockTransport):
    """AsyncClient stand-in that keeps caller kwargs but forces the transport."""

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    return factory


if __name__ == "__main__":
    unittest.main()
