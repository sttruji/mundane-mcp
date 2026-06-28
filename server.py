"""Mundane MCP server (design doc §6, Layer 2).

A thin adapter: each tool maps to a Layer-1 REST endpoint and forwards the
agent's API key. Any MCP-capable agent connects to this server and gets the
Mundane toolset. Run over stdio:  python -m mcp_server.server

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
    """Create a real-world task (screened before it becomes offerable). Write
    instructions a stranger could follow with no extra context. Money in cents."""
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
    min_rating: float = 0,
    min_rating_count: int = 0,
    max_rate_minor: int | None = None,
    limit: int = 20,
) -> list | dict:
    """Find verified workers near a point matching capability, rating, and price
    filters, ranked for selection. Does not commit funds."""
    params = {
        "lat": lat, "lng": lng, "radius_km": radius_km, "min_rating": min_rating,
        "min_rating_count": min_rating_count, "limit": limit,
    }
    if capability is not None:
        params["capability"] = capability
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
    """Current state of a task: lifecycle, active offer, worker, proof, timeline."""
    return await _request("GET", f"/tasks/{task_id}")


@mcp.tool()
async def cancel_task(task_id: str, reason: str | None = None) -> dict:
    """Cancel a task and any pending offer (subject to cancellation policy)."""
    return await _request("POST", f"/tasks/{task_id}/cancel", json={"reason": reason})


@mcp.tool()
async def submit_completion_review(task_id: str, decision: str, reason: str | None = None) -> dict:
    """Review submitted proof. 'accept' releases escrow; 'reject' needs a reason
    and opens a dispute."""
    body = {"task_id": task_id, "decision": decision, "reason": reason}
    return await _request("POST", f"/tasks/{task_id}/review", json=body)


@mcp.tool()
async def submit_rating(task_id: str, score: int, description: str) -> dict:
    """Rate a worker 1-5 with a description for a completed task (once per task)."""
    body = {"task_id": task_id, "score": score, "description": description}
    return await _request("POST", f"/tasks/{task_id}/rating", json=body)


if __name__ == "__main__":
    mcp.run()
