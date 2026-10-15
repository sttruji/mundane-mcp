"""The per-request key on hosted mounts, versus stdio's process key."""
from mcp_server import server


def test_a_bound_empty_key_never_borrows_the_process_key(monkeypatch):
    """Hosted mounts bind "" for anonymous calls; that must mean "no key"."""
    monkeypatch.setattr(server, "API_KEY", "process_wide_secret")
    assert server.current_api_key() == "process_wide_secret"   # stdio: unset falls back
    token = server.set_request_api_key("")
    try:
        assert server.current_api_key() == ""
    finally:
        server.reset_request_api_key(token)
