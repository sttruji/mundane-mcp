"""MCP proof retrieval composes owner-scoped REST calls into image content."""

import base64
import json
import unittest
from io import BytesIO
from unittest.mock import patch

import httpx
from mcp.types import ImageContent, TextContent
from PIL import Image as PILImage

from mcp_server import server


API_BASE = "https://mundane.test/v1"
UPLOAD_ID_1 = "bdcf9e2b-e674-444f-82fe-1b9332cf905d"
UPLOAD_ID_2 = "f745ffaf-88cc-4f8f-8e6b-13f26f5ba1b4"


def _jpeg(width: int = 32, height: int = 24) -> bytes:
    output = BytesIO()
    PILImage.new("RGB", (width, height), color=(32, 96, 160)).save(
        output,
        format="JPEG",
        quality=95,
    )
    return output.getvalue()


def _heif(width: int = 18, height: int = 12) -> bytes:
    output = BytesIO()
    PILImage.new("RGB", (width, height), color=(120, 80, 40)).save(
        output,
        format="HEIF",
        quality=90,
    )
    return output.getvalue()


def _image_size(block: ImageContent) -> tuple[int, int]:
    with PILImage.open(BytesIO(base64.b64decode(block.data))) as image:
        return image.size


def _task_response(proof: list[dict]) -> dict:
    return {
        "task_id": "task-owned",
        "status": "submitted",
        "offer": None,
        "worker": None,
        "completion": {
            "submitted_at": "2026-07-17T12:00:00+00:00",
            "proof": proof,
            "review_decision": None,
            "reviewed_at": None,
        },
        "timeline": [],
    }


class ProofRetrievalToolTests(unittest.IsolatedAsyncioTestCase):
    async def _call(self, handler, task_id: str = "task-owned"):
        transport = httpx.MockTransport(handler)

        def client_factory() -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url=API_BASE,
                headers={"Authorization": "Bearer agent-secret"},
                transport=transport,
                timeout=30,
            )

        with patch.object(server, "_client", side_effect=client_factory):
            return await server.mcp.call_tool(
                "get_task_proof",
                {"task_id": task_id},
            )

    async def test_returns_proof_metadata_and_image_content(self):
        requests: list[httpx.Request] = []
        photo = _jpeg()

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/v1/tasks/task-owned":
                return httpx.Response(
                    200,
                    json=_task_response(
                        [
                            {
                                "type": "photo",
                                "url": (
                                    "https://api.mundane.market/v1/"
                                    f"proof-uploads/{UPLOAD_ID_1}"
                                ),
                            },
                            {"type": "confirmation_code", "value": "R-12345"},
                        ]
                    ),
                )
            if request.url.path == f"/v1/proof-uploads/{UPLOAD_ID_1}":
                return httpx.Response(
                    200,
                    content=photo,
                    headers={"Content-Type": "image/jpeg"},
                )
            return httpx.Response(500, json={"detail": "unexpected request"})

        blocks = await self._call(handler)

        images = [block for block in blocks if isinstance(block, ImageContent)]
        text = "\n".join(
            block.text for block in blocks if isinstance(block, TextContent)
        )
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].mimeType, "image/jpeg")
        self.assertEqual(_image_size(images[0]), (32, 24))
        self.assertIn('"type": "photo"', text)
        self.assertIn('"type": "confirmation_code"', text)
        self.assertIn('"value": "R-12345"', text)
        self.assertEqual(
            [request.url.path for request in requests],
            [
                "/v1/tasks/task-owned",
                f"/v1/proof-uploads/{UPLOAD_ID_1}",
            ],
        )
        self.assertTrue(
            all(
                request.headers["authorization"] == "Bearer agent-secret"
                for request in requests
            )
        )

    async def test_fetches_every_photo_and_downscales_long_side(self):
        requests: list[httpx.Request] = []
        large_photo = _jpeg(2400, 1200)
        small_photo = _jpeg(20, 40)

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/v1/tasks/task-owned":
                return httpx.Response(
                    200,
                    json=_task_response(
                        [
                            {
                                "type": "photo",
                                "url": f"{API_BASE}/proof-uploads/{UPLOAD_ID_1}",
                            },
                            {
                                "type": "photo",
                                "url": f"{API_BASE}/proof-uploads/{UPLOAD_ID_2}",
                            },
                        ]
                    ),
                )
            photos = {
                f"/v1/proof-uploads/{UPLOAD_ID_1}": large_photo,
                f"/v1/proof-uploads/{UPLOAD_ID_2}": small_photo,
            }
            if request.url.path in photos:
                return httpx.Response(
                    200,
                    content=photos[request.url.path],
                    headers={"Content-Type": "image/jpeg"},
                )
            return httpx.Response(500, json={"detail": "unexpected request"})

        blocks = await self._call(handler)

        images = [block for block in blocks if isinstance(block, ImageContent)]
        self.assertEqual(len(images), 2)
        sizes = [_image_size(image) for image in images]
        self.assertEqual(sizes, [(1568, 784), (20, 40)])
        self.assertTrue(
            all(
                len(base64.b64decode(image.data)) <= server.MAX_PROOF_OUTPUT_BYTES
                for image in images
            )
        )
        self.assertEqual(
            [request.url.path for request in requests],
            [
                "/v1/tasks/task-owned",
                f"/v1/proof-uploads/{UPLOAD_ID_1}",
                f"/v1/proof-uploads/{UPLOAD_ID_2}",
            ],
        )

    async def test_heic_proof_is_returned_as_model_compatible_jpeg(self):
        heic_photo = _heif()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/tasks/task-owned":
                return httpx.Response(
                    200,
                    json=_task_response(
                        [
                            {
                                "type": "photo",
                                "url": f"{API_BASE}/proof-uploads/{UPLOAD_ID_1}",
                            }
                        ]
                    ),
                )
            if request.url.path == f"/v1/proof-uploads/{UPLOAD_ID_1}":
                return httpx.Response(
                    200,
                    content=heic_photo,
                    headers={"Content-Type": "image/heic"},
                )
            return httpx.Response(500, json={"detail": "unexpected request"})

        blocks = await self._call(handler)

        image = next(block for block in blocks if isinstance(block, ImageContent))
        self.assertEqual(image.mimeType, "image/jpeg")
        self.assertEqual(_image_size(image), (18, 12))

    async def test_non_owner_task_404_is_returned_without_fetching_a_photo(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(404, json={"detail": "Task not found"})

        blocks = await self._call(handler, task_id="task-owned-by-another-agent")

        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0].url.path,
            "/v1/tasks/task-owned-by-another-agent",
        )
        self.assertFalse(any(isinstance(block, ImageContent) for block in blocks))
        payload = json.loads(
            next(block.text for block in blocks if isinstance(block, TextContent))
        )
        self.assertEqual(payload["status"], 404)
        self.assertEqual(payload["detail"], {"detail": "Task not found"})

    async def test_worker_supplied_external_url_never_receives_agent_credentials(self):
        requests: list[httpx.Request] = []
        photo = _jpeg()

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/v1/tasks/task-owned":
                return httpx.Response(
                    200,
                    json=_task_response(
                        [
                            {
                                "type": "photo",
                                "url": (
                                    "https://attacker.example/v1/"
                                    f"proof-uploads/{UPLOAD_ID_1}"
                                ),
                            },
                            {
                                "type": "photo",
                                "url": "https://attacker.example/collect-agent-key",
                            },
                        ]
                    ),
                )
            if request.url.path == f"/v1/proof-uploads/{UPLOAD_ID_1}":
                return httpx.Response(
                    200,
                    content=photo,
                    headers={"Content-Type": "image/jpeg"},
                )
            return httpx.Response(500, json={"detail": "credentials escaped"})

        blocks = await self._call(handler)

        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request.url.host == "mundane.test" for request in requests))
        self.assertEqual(
            len([block for block in blocks if isinstance(block, ImageContent)]),
            1,
        )
        text = "\n".join(
            block.text for block in blocks if isinstance(block, TextContent)
        )
        self.assertIn("not a protected Mundane proof upload", text)


if __name__ == "__main__":
    unittest.main()
