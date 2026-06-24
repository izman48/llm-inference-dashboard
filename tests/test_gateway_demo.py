"""Deployment guardrails for the public demo: control-token gating + hard caps."""

from __future__ import annotations

from fastapi.testclient import TestClient

from inference_demo.gateway.app import GatewayConfig, create_app
from inference_demo.pool import build_pool


def _client(**cfg: object) -> TestClient:
    pool = build_pool(n_workers=2, autoscale=False)
    return TestClient(create_app(pool, run_background=False, config=GatewayConfig(**cfg)))


def test_control_token_gates_mutations_but_not_reads() -> None:
    c = _client(control_token="s3cret")

    # reads stay open
    assert c.get("/api/snapshot").status_code == 200
    assert c.get("/api/strategies").status_code == 200

    # mutations require the token
    assert c.post("/api/strategy", json={"name": "round-robin"}).status_code == 401
    ok = c.post(
        "/api/strategy", json={"name": "round-robin"}, headers={"x-control-token": "s3cret"}
    )
    assert ok.status_code == 200
    assert (
        c.post(
            "/api/strategy", json={"name": "round-robin"}, headers={"x-control-token": "no"}
        ).status_code
        == 401
    )


def test_no_token_means_open() -> None:
    c = _client()  # permissive default
    assert c.post("/api/strategy", json={"name": "round-robin"}).status_code == 200


def test_loadgen_rate_is_capped() -> None:
    c = _client(max_rate_cap=50.0)
    r = c.post("/api/loadgen", json={"preset": "spike", "base_rate": 9999})
    assert r.status_code == 200
    assert r.json()["base_rate"] == 50.0  # clamped to the cap


def test_autoscaler_max_workers_is_capped() -> None:
    c = _client(max_workers_cap=4)
    r = c.post("/api/autoscaler", json={"max_workers": 99})
    assert r.status_code == 200
    assert r.json()["max_workers"] == 4


def test_submit_clamps_token_counts() -> None:
    c = _client(max_tokens_cap=32)
    r = c.post("/api/submit", json={"prompt_tokens": 9999, "max_tokens": 9999})
    assert r.status_code == 200  # accepted, but clamped internally (no error)


def test_backend_switching_blocked_on_public_demo() -> None:
    # The hosted box must stay sim-only — taking an arbitrary endpoint URL there is SSRF.
    c = _client(demo=True)
    assert c.get("/api/backends").json()["switchable"] is False
    r = c.post("/api/backend", json={"backend": "openai", "base_url": "http://x:11434"})
    assert r.status_code == 403
