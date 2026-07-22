"""MCP contract for agent task file attachments."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp_server import server


class AttachmentToolContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    async def test_tools_registered_with_required_args(self):
        attach = self.tools["attach_task_file"].inputSchema
        self.assertEqual(attach.get("required", []), ["task_id", "file_path"])
        listing = self.tools["list_task_attachments"].inputSchema
        self.assertEqual(listing.get("required", []), ["task_id"])

    async def test_attach_documents_allowlist_and_caps(self):
        description = self.tools["attach_task_file"].description
        self.assertIn("stl", description)
        self.assertIn("25", description)
        self.assertIn("10", description)


class AttachFileBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def _tmp_file(self, name: str, content: bytes) -> Path:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(
            lambda: [p.unlink() for p in directory.glob("*")]
            and directory.rmdir(),
        )
        path = directory / name
        path.write_bytes(content)
        return path

    async def test_attach_uploads_local_file_bytes(self):
        path = self._tmp_file("bracket.stl", b"solid cube\nendsolid cube\n")
        with patch.object(
            server, "_request", new_callable=AsyncMock,
            return_value={"id": "a1", "filename": "bracket.stl"},
        ) as request:
            result = await server.attach_task_file("task-1", str(path))

        self.assertEqual(result["id"], "a1")
        request.assert_awaited_once()
        args = request.await_args
        self.assertEqual(args.args, ("POST", "/tasks/task-1/attachments"))
        self.assertEqual(args.kwargs["params"], {"filename": "bracket.stl"})
        self.assertEqual(args.kwargs["content"], b"solid cube\nendsolid cube\n")
        self.assertEqual(
            args.kwargs["headers"]["Content-Type"], "application/octet-stream",
        )

    async def test_attach_honors_filename_override(self):
        path = self._tmp_file("download(1).stl", b"solid\nendsolid\n")
        with patch.object(
            server, "_request", new_callable=AsyncMock, return_value={},
        ) as request:
            await server.attach_task_file(
                "task-1", str(path), filename="bracket v2.stl",
            )
        self.assertEqual(
            request.await_args.kwargs["params"], {"filename": "bracket v2.stl"},
        )

    async def test_attach_refuses_locally_without_uploading(self):
        with patch.object(
            server, "_request", new_callable=AsyncMock,
        ) as request:
            missing = await server.attach_task_file("task-1", "/no/such/file.stl")
            self.assertTrue(missing["error"])

            bad_ext = self._tmp_file("malware.exe", b"MZ")
            refused = await server.attach_task_file("task-1", str(bad_ext))
            self.assertTrue(refused["error"])
            self.assertIn("extension", refused["detail"])

            big = self._tmp_file("big.stl", b"\0" * (25 * 1024 * 1024 + 1))
            oversize = await server.attach_task_file("task-1", str(big))
            self.assertTrue(oversize["error"])
            self.assertIn("25 MB", oversize["detail"])

        request.assert_not_awaited()

    async def test_list_calls_endpoint(self):
        with patch.object(
            server, "_request", new_callable=AsyncMock,
            return_value={"attachments": []},
        ) as request:
            await server.list_task_attachments("task-9")
        request.assert_awaited_once_with("GET", "/tasks/task-9/attachments")


if __name__ == "__main__":
    unittest.main()
