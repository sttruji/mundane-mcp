"""Mundane MCP server (design doc §6, Layer 2).

A thin adapter: each tool maps to a Layer-1 REST endpoint and forwards the
agent's API key. Runs over stdio, one process per agent -- self-hosted by
each agent operator, not a shared service Mundane runs centrally. See
mcp_server/README.md for install + MCP client config. Entry point:
`mundane-mcp` (console script) or `python -m mcp_server.server`.

NOTE: uses the official MCP Python SDK (`pip install mcp`). Verify tool/registration
syntax against the SDK version you install; the FastMCP surface is shown here.
"""
import json
import os
import re
import uuid
from io import BytesIO
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP, Image as MCPImage
from PIL import Image as PILImage, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

API_BASE = os.environ.get("MUNDANE_API_BASE", "http://localhost:8000/v1")
API_KEY = os.environ.get("MUNDANE_API_KEY", "")

mcp = FastMCP("mundane")

MAX_PROOF_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_PROOF_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_PROOF_LONG_SIDE = 1568
MAX_PROOF_DECODED_PIXELS = 40_000_000
MAX_TASK_WAIT_SECONDS = 55.0
_PROOF_UPLOAD_PATH = re.compile(r"^(?:/v1)?/proof-uploads/([^/]+)/?$")

register_heif_opener()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API_BASE,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30,
    )


async def _request(method: str, path: str, **kw) -> dict | list:
    async with _client() as c:
        r = await c.request(method, path, **kw)
        # Surface structured spend/screening errors to the agent verbatim.
        if r.status_code >= 400:
            try:
                return {"error": True, "status": r.status_code, "detail": r.json()}
            except Exception:
                return {"error": True, "status": r.status_code, "detail": r.text}
        return r.json()


def _protected_upload_path(raw_url: object) -> str | None:
    """Return an API-relative proof path without trusting the submitted host."""
    if not isinstance(raw_url, str):
        return None
    match = _PROOF_UPLOAD_PATH.fullmatch(urlsplit(raw_url).path)
    if match is None:
        return None
    try:
        upload_id = str(uuid.UUID(match.group(1)))
    except ValueError:
        return None
    return f"/proof-uploads/{upload_id}"


def _jpeg_for_model(raw: bytes) -> bytes:
    """Orient, bound, and encode a proof photo for multimodal MCP clients."""
    if len(raw) > MAX_PROOF_DOWNLOAD_BYTES:
        raise ValueError("proof photo exceeds the 8 MB retrieval limit")
    try:
        with PILImage.open(BytesIO(raw)) as source:
            if source.width * source.height > MAX_PROOF_DECODED_PIXELS:
                raise ValueError("proof photo exceeds the safe decoded-pixel limit")
            source.load()
            image = ImageOps.exif_transpose(source)
            image.thumbnail(
                (MAX_PROOF_LONG_SIDE, MAX_PROOF_LONG_SIDE),
                PILImage.Resampling.LANCZOS,
            )
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                flattened = PILImage.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                image = flattened
            else:
                image = image.convert("RGB")

            for quality in (85, 75, 65, 55):
                output = BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
                encoded = output.getvalue()
                if len(encoded) <= MAX_PROOF_OUTPUT_BYTES:
                    return encoded
    except (
        OSError,
        UnidentifiedImageError,
        PILImage.DecompressionBombError,
    ) as exc:
        raise ValueError("proof upload is not a decodable image") from exc
    raise ValueError("normalized proof photo exceeds the 2 MB MCP limit")


async def _fetch_proof_image(path: str) -> MCPImage | dict:
    async with _client() as client:
        response = await client.get(path)
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            return {
                "error": True,
                "status": response.status_code,
                "detail": detail,
            }
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if not content_type.startswith("image/"):
            return {
                "error": True,
                "status": 502,
                "detail": "proof upload did not return an image",
            }
        try:
            normalized = _jpeg_for_model(response.content)
        except ValueError as exc:
            return {"error": True, "status": 422, "detail": str(exc)}
        return MCPImage(data=normalized, format="jpeg")


@mcp.tool()
async def list_capabilities() -> list | dict:
    """List task capabilities this agent may dispatch, with per-capability
    constraints and required proof types. Call before posting a task."""
    return await _request("GET", "/capabilities")


@mcp.tool()
async def get_spend_status() -> dict:
    """Return the authenticated agent and principal identity, wallet balance,
    and remaining headroom against every spend cap. Money fields are integer
    minor units in the returned currency. Consult before making offers."""
    return await _request("GET", "/spend-status")


@mcp.tool()
async def topup_wallet(
    amount_minor: int,
    currency: str = "USD",
    success_url: str = "https://mundane.market/?topup=success",
    cancel_url: str = "https://mundane.market/?topup=cancelled",
    idempotency_key: str | None = None,
) -> dict:
    """Create a Stripe Checkout link that adds funds to the principal's wallet.
    Returns checkout_url -- hand that link to your human, who pays on Stripe's
    hosted page (the agent never touches card details). The wallet credits
    automatically once payment completes; confirm with get_spend_status.
    amount_minor is in the smallest currency unit (500 = $5.00) and currency
    must match the principal's wallet currency."""
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    body = {
        "amount_minor": amount_minor, "currency": currency,
        "success_url": success_url, "cancel_url": cancel_url,
    }
    return await _request("POST", "/wallet/topup", json=body, headers=headers)


@mcp.tool()
async def submit_experience_feedback(
    gap_text: str,
    tags: list[str] | None = None,
    free_text: str | None = None,
    task_id: str | None = None,
) -> dict:
    """Explicitly submit post-task experience feedback to Mundane. Phrase
    `gap_text` as "If I'd had a way to ..., I could have ..." and optionally
    link the owned `task_id`, add categorical `tags`, and provide context in
    `free_text`. All submitted text is stored as untrusted data; it is not
    interpreted as instructions or used to change the active task."""
    body = {
        "gap_text": gap_text,
        "tags": tags or [],
        "free_text": free_text,
        "task_id": task_id,
    }
    return await _request("POST", "/agents/feedback", json=body)


@mcp.tool()
async def post_task(
    title: str,
    instructions: str,
    lat: float,
    lng: float,
    required_capabilities: list[str],
    budget_max_minor: int,
    deadline: str,
    address: str | None = None,
    proof_requirements: list[str] | None = None,
    proof_requirement_opt_outs: list[str] | None = None,
    currency: str = "USD",
    idempotency_key: str | None = None,
) -> dict:
    """Create a real-world task and run the full screening cascade: policy_gate
    regex, task_shapes shape_match, a Claude LLM classifier when ANTHROPIC_API_KEY is set
    or SCREENING_LLM_FALLBACK when absent, then human_review parking when needed.
    Results in status open, rejected, or screening. Write instructions a stranger
    can execute. `budget_max_minor` is the all-in ceiling in integer minor units
    of `currency`; `deadline` is an ISO 8601 timestamp with a timezone. Latitude
    and longitude are decimal degrees.

    The stored proof requirements are the union of each required capability's
    unwaivable floor, its default proof types, and your `proof_requirements`
    extras. `proof_requirement_opt_outs` waives a capability *default* where it
    isn't the product — e.g. `["geo_checkin"]` on a photo task whose location
    doesn't matter. Waiving a capability floor (like geo check-in on an errand)
    returns a structured 422; floors are never waivable."""
    body = {
        "title": title, "instructions": instructions,
        "location": {"lat": lat, "lng": lng, "address": address},
        "required_capabilities": required_capabilities,
        "budget_max_minor": budget_max_minor, "currency": currency,
        "deadline": deadline, "proof_requirements": proof_requirements or [],
        "proof_requirement_opt_outs": proof_requirement_opt_outs or [],
        "idempotency_key": idempotency_key,
    }
    return await _request("POST", "/tasks", json=body)


@mcp.tool()
async def search_workers(
    lat: float,
    lng: float,
    radius_km: float = 25,
    capability: str | None = None,
    skill: str | None = None,
    min_rating: float = 0,
    min_rating_count: int = 0,
    max_rate_minor: int | None = None,
    limit: int = 20,
) -> list | dict:
    """Find verified workers near a point matching capability, rating, and price
    filters, ranked for selection. `ask_rate_minor` is each worker's enforced
    minimum per-task price in minor units; `ask_rate_basis` is `per_task`, and
    `max_rate_minor` filters on that same basis. `rate_card` contains advisory
    per-task asks for labeled work. When the task fits a label, offer at least
    that entry's `rate_minor`; labels are informational and are not matched or
    enforced by the offer endpoint. Does not commit funds.

    `skill` filters on workers' free-form self-declared qualifiers (e.g.
    'welding', 'bio lab support', 'notary') — an open vocabulary, fuzzy-matched
    (case-insensitive, tolerant of typos and word order, and matching a query
    word inside a multi-word tag). When the marketplace has semantic matching
    enabled, natural-language queries also bridge synonyms ('move heavy boxes'
    finds 'lifting heavy items') and a strong semantic match lifts
    `match_score`; if results look sparse, still try the worker's own likely
    wording or search without `skill` and read each result's `skills` list."""
    params = {
        "lat": lat, "lng": lng, "radius_km": radius_km, "min_rating": min_rating,
        "min_rating_count": min_rating_count, "limit": limit,
    }
    if capability is not None:
        params["capability"] = capability
    if skill is not None:
        params["skill"] = skill
    if max_rate_minor is not None:
        params["max_rate_minor"] = max_rate_minor
    return await _request("GET", "/workers", params=params)


@mcp.tool()
async def get_worker(worker_id: str) -> dict:
    """Return one worker's public profile and reputation. `ask_rate_minor` is
    the worker's enforced minimum per-task price in minor units and
    `ask_rate_basis` is `per_task`. `rate_card` entries are advisory asks for
    labeled work; when the task fits a label, offer at least that entry's
    `rate_minor`. Only the general ask is enforced by the offer endpoint."""
    return await _request("GET", f"/workers/{worker_id}")


@mcp.tool()
async def make_offer(
    task_id: str,
    worker_id: str,
    amount_minor: int,
    currency: str = "USD",
    expires_in_seconds: int = 86400,
    message: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Offer a task to a worker. `amount_minor` is the worker's per-task amount
    in integer minor units of `currency`; the platform fee is added on top.
    `expires_in_seconds` is the pending-offer lifetime in seconds. On success,
    the all-in total is held in escrow. Structured errors report budget, worker
    eligibility / ask-rate, wallet, or spend-cap failures."""
    body = {
        "task_id": task_id, "worker_id": worker_id, "amount_minor": amount_minor,
        "currency": currency, "expires_in_seconds": expires_in_seconds,
        "message": message, "idempotency_key": idempotency_key,
    }
    return await _request("POST", "/offers", json=body)


@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    """Get task lifecycle state, active offer, assigned worker, completion proof,
    and timeline. Offer amounts are integer minor units and timestamps are ISO
    8601 strings. Timeline includes screened:<outcome> entries from the screening
    cascade, and status can include disputed or completed."""
    return await _request("GET", f"/tasks/{task_id}")


@mcp.tool()
async def await_task_update(
    task_id: str,
    timeout_seconds: float = MAX_TASK_WAIT_SECONDS,
) -> dict:
    """Wait `timeout_seconds` (capped at 55 seconds) for an owned task to change,
    then return its full
    status payload. `changed` is true when status, updated time, or task audit
    activity changed during the wait; false means the timeout elapsed. Use this
    instead of repeatedly calling get_task_status while waiting for a worker.
    """
    bounded_timeout = min(max(timeout_seconds, 0.0), MAX_TASK_WAIT_SECONDS)
    return await _request(
        "GET",
        f"/tasks/{task_id}",
        params={"wait_for_change": bounded_timeout},
        timeout=bounded_timeout + 5.0,
    )


@mcp.tool()
async def get_task_proof(task_id: str):
    """View submitted completion proof before accepting or rejecting it.

    Returns each proof item's metadata as text and each protected photo as MCP
    image content. Photos are oriented and reduced to a 1568px long side. Only
    the agent that owns the task can retrieve it; non-owners receive the task
    endpoint's 404 response.
    """
    task = await _request("GET", f"/tasks/{task_id}")
    if not isinstance(task, dict) or task.get("error"):
        return task

    completion = task.get("completion")
    proof = completion.get("proof") if isinstance(completion, dict) else None
    if not isinstance(proof, list) or not proof:
        return [f"Task {task_id} has no submitted completion proof."]

    content: list[object] = []
    for index, item in enumerate(proof, start=1):
        if not isinstance(item, dict):
            content.append(f"Proof {index} metadata is malformed.")
            continue

        upload_path = _protected_upload_path(item.get("url"))
        metadata = {key: value for key, value in item.items() if key != "url"}
        if upload_path is not None:
            metadata["upload_id"] = upload_path.rsplit("/", 1)[-1]
        content.append(
            f"Proof {index} metadata:\n"
            + json.dumps(metadata, sort_keys=True, ensure_ascii=True)
        )

        if item.get("type") != "photo":
            continue
        if upload_path is None:
            content.append(
                f"Proof {index} photo URL is not a protected Mundane proof upload."
            )
            continue

        image = await _fetch_proof_image(upload_path)
        if isinstance(image, dict):
            content.append(
                f"Proof {index} image retrieval failed:\n"
                + json.dumps(image, sort_keys=True, ensure_ascii=True)
            )
        else:
            content.append(image)
    return content


@mcp.tool()
async def update_task(
    task_id: str,
    title: str | None = None,
    instructions: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    address: str | None = None,
    required_capabilities: list[str] | None = None,
    budget_max_minor: int | None = None,
    deadline: str | None = None,
    proof_requirements: list[str] | None = None,
) -> dict:
    """Amend an unassigned task instead of cancel-and-repost. Supply only the
    fields to change; at least one is required. Material changes (title,
    instructions, location, capabilities, proof requirements) re-run the FULL
    screening cascade — the response's `status` may come back `rejected` — and
    withdraw any pending offer with an automatic escrow refund. Budget or
    deadline-only changes skip re-screening but are refused (409) while an
    offer is pending. Accepted, in-progress, and rejected tasks are immutable;
    editing them returns 409."""
    body: dict = {}
    if title is not None:
        body["title"] = title
    if instructions is not None:
        body["instructions"] = instructions
    if lat is not None or lng is not None or address is not None:
        if lat is None or lng is None:
            raise ValueError("location updates need both lat and lng")
        body["location"] = {"lat": lat, "lng": lng, "address": address}
    if required_capabilities is not None:
        body["required_capabilities"] = required_capabilities
    if budget_max_minor is not None:
        body["budget_max_minor"] = budget_max_minor
    if deadline is not None:
        body["deadline"] = deadline
    if proof_requirements is not None:
        body["proof_requirements"] = proof_requirements
    return await _request("PATCH", f"/tasks/{task_id}", json=body)


@mcp.tool()
async def cancel_task(task_id: str, reason: str | None = None) -> dict:
    """Cancel a task and any pending offer. An accepted task may charge the
    configured cancellation fee, returned as integer `fee_minor` units."""
    return await _request("POST", f"/tasks/{task_id}/cancel", json={"reason": reason})


@mcp.tool()
async def submit_completion_review(task_id: str, decision: str, reason: str | None = None) -> dict:
    """Review submitted proof with decision `accept` or `reject`. Reject requires
    a reason. Accept publishes the real escrow.release outbox
    event that captures the Stripe PaymentIntent and creates worker_payouts;
    reject requires a reason, creates a disputes row, and leaves ops resolution to
    POST /v1/ops/disputes/{id}/resolve with refund/release/split."""
    body = {"task_id": task_id, "decision": decision, "reason": reason}
    return await _request("POST", f"/tasks/{task_id}/review", json=body)


@mcp.tool()
async def submit_rating(task_id: str, score: int, description: str) -> dict:
    """Rate a completed task once with an integer score from 1 through 5 and a
    written description. Records the rating and recomputes the worker
    Bayesian aggregate (prior_mean=4.2, prior_weight=10);
    worker_new_aggregate_rating is the new aggregate."""
    body = {"task_id": task_id, "score": score, "description": description}
    return await _request("POST", f"/tasks/{task_id}/rating", json=body)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
