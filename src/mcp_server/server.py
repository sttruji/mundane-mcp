"""Mundane MCP server (design doc §6, Layer 2).

A thin adapter: each tool maps to a Layer-1 REST endpoint and forwards the
agent's API key. Runs over stdio, one process per agent -- self-hosted by
each agent operator, not a shared service Mundane runs centrally. See
mcp_server/README.md for install + MCP client config. Entry point:
`mundane-mcp` (console script) or `python -m mcp_server.server`.

NOTE: uses the official MCP Python SDK (`pip install mcp`). Verify tool/registration
syntax against the SDK version you install; the FastMCP surface is shown here.
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("MUNDANE_API_BASE", "http://localhost:8000/v1")
API_KEY = os.environ.get("MUNDANE_API_KEY", "")

mcp = FastMCP("mundane")


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


@mcp.tool()
async def list_capabilities() -> list | dict:
    """List task capabilities this agent may dispatch, with per-capability
    constraints and required proof types. Call before posting a task."""
    return await _request("GET", "/capabilities")


@mcp.tool()
async def get_spend_status() -> dict:
    """Wallet balance and remaining headroom against every spend cap. Consult
    before making offers to avoid rejected escrow."""
    return await _request("GET", "/spend-status")


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
    currency: str = "USD",
    idempotency_key: str | None = None,
) -> dict:
    """Create a real-world task and run the full screening cascade: policy_gate
    regex, task_shapes shape_match, Claude Opus 4.7 when ANTHROPIC_API_KEY is set
    or SCREENING_LLM_FALLBACK when absent, then human_review parking when needed.
    Results in status open, rejected, or screening. Write instructions a stranger
    can execute."""
    body = {
        "title": title, "instructions": instructions,
        "location": {"lat": lat, "lng": lng, "address": address},
        "required_capabilities": required_capabilities,
        "budget_max_minor": budget_max_minor, "currency": currency,
        "deadline": deadline, "proof_requirements": proof_requirements or [],
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
    filters, ranked for selection. Does not commit funds.

    `skill` filters on workers' free-form self-declared qualifiers (e.g.
    'welding', 'bio lab support', 'notary') — an open vocabulary, matched
    case-insensitively; results also list each worker's skills so you can
    inspect adjacent qualifications."""
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
    """Full public profile and reputation detail for one worker."""
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
    """Offer a task to a worker. On success the amount is held in escrow while
    pending. Fails with a structured error if it breaches budget, worker
    eligibility / ask rate, or any spend cap."""
    body = {
        "task_id": task_id, "worker_id": worker_id, "amount_minor": amount_minor,
        "currency": currency, "expires_in_seconds": expires_in_seconds,
        "message": message, "idempotency_key": idempotency_key,
    }
    return await _request("POST", "/offers", json=body)


@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    """Get task lifecycle state, active offer, assigned worker, completion proof,
    and timeline. Timeline includes screened:<outcome> entries from the screening
    cascade, and status can include disputed or completed."""
    return await _request("GET", f"/tasks/{task_id}")


@mcp.tool()
async def cancel_task(task_id: str, reason: str | None = None) -> dict:
    """Cancel a task and any pending offer (subject to cancellation policy)."""
    return await _request("POST", f"/tasks/{task_id}/cancel", json={"reason": reason})


@mcp.tool()
async def submit_completion_review(task_id: str, decision: str, reason: str | None = None) -> dict:
    """Review submitted proof. Accept publishes the real escrow.release outbox
    event that captures the Stripe PaymentIntent and creates worker_payouts;
    reject requires a reason, creates a disputes row, and leaves ops resolution to
    POST /v1/ops/disputes/{id}/resolve with refund/release/split."""
    body = {"task_id": task_id, "decision": decision, "reason": reason}
    return await _request("POST", f"/tasks/{task_id}/review", json=body)


@mcp.tool()
async def submit_rating(task_id: str, score: int, description: str) -> dict:
    """Rate a completed task once. Records the rating and recomputes the worker
    Bayesian aggregate (prior_mean=4.2, prior_weight=10);
    worker_new_aggregate_rating is the new aggregate."""
    body = {"task_id": task_id, "score": score, "description": description}
    return await _request("POST", f"/tasks/{task_id}/rating", json=body)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
