"""API contract tests for the FastAPI gateway, driven with the TestClient.

The background stepping loop is OFF here; tests advance the pool deterministically
via POST /api/step so assertions are stable.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from inference_demo.gateway.app import create_app
from inference_demo.pool import build_pool


def client() -> TestClient:
    pool = build_pool(n_workers=2, autoscale=False)
    return TestClient(create_app(pool, run_background=False))


def test_submit_then_step_then_metrics_updates() -> None:
    c = client()
    r = c.post(
        "/api/submit", json={"prompt_tokens": 50, "max_tokens": 5, "priority": "interactive"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["worker_id"].startswith("w")
    assert "req_id" in body

    for _ in range(200):
        c.post("/api/step", json={"n": 1})
    snap = c.get("/api/snapshot").json()
    assert snap["metrics"]["completed_total"] == 1
    assert snap["metrics"]["tokens_total"] == 5


def test_strategies_listed_and_switchable_live() -> None:
    c = client()
    names = c.get("/api/strategies").json()["strategies"]
    assert "power-of-two-choices" in names

    r = c.post("/api/strategy", json={"name": "round-robin"})
    assert r.status_code == 200
    assert c.get("/api/snapshot").json()["pool"]["strategy"] == "round-robin"

    bad = c.post("/api/strategy", json={"name": "nope"})
    assert bad.status_code == 422


def test_autoscaler_config_roundtrip() -> None:
    c = client()
    r = c.post("/api/autoscaler", json={"enabled": True, "min_workers": 2, "max_workers": 6})
    assert r.status_code == 200
    cfg = c.get("/api/snapshot").json()["pool"]["autoscaler"]
    assert cfg["enabled"] is True
    assert cfg["min_workers"] == 2
    assert cfg["max_workers"] == 6


def test_kill_worker_endpoint_reduces_pool() -> None:
    c = client()
    before = c.get("/api/snapshot").json()["pool"]["num_workers"]
    r = c.post("/api/workers/kill", json={})
    assert r.status_code == 200
    after = c.get("/api/snapshot").json()["pool"]["num_workers"]
    assert after == before - 1


def test_autoscaler_target_clamped_within_worker_cap() -> None:
    # target_queue_depth must stay coherent — never above the worker cap.
    c = client()
    r = c.post("/api/autoscaler", json={"max_workers": 2, "target_queue_depth": 8})
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["max_workers"] == 2
    assert cfg["target_queue_depth"] <= 2


def test_backends_listed_and_switchable_live() -> None:
    c = client()
    info = c.get("/api/backends").json()
    assert info["current"] == "sim"
    assert info["switchable"] is True  # not a public demo
    ids = {b["id"] for b in info["available"]}
    assert {"sim", "openai", "realmodel"} <= ids

    r = c.post("/api/backend", json={"backend": "openai", "base_url": "http://x:11434"})
    assert r.status_code == 200
    assert r.json()["backend"] == "openai"
    assert c.get("/api/snapshot").json()["pool"]["backend"] == "openai"


def test_reset_endpoint_restores_pool_and_clears_metrics() -> None:
    c = client()
    c.post("/api/submit", json={"prompt_tokens": 50, "max_tokens": 5, "priority": "interactive"})
    for _ in range(200):
        c.post("/api/step", json={"n": 1})
    assert c.get("/api/snapshot").json()["metrics"]["completed_total"] == 1

    r = c.post("/api/reset", json={})
    assert r.status_code == 200
    assert r.json()["num_workers"] == 2
    snap = c.get("/api/snapshot").json()
    assert snap["metrics"]["completed_total"] == 0
    assert snap["metrics"]["throughput_tok_s"] == 0.0


def test_prometheus_endpoint_serves_text() -> None:
    c = client()
    r = c.get("/metrics")
    assert r.status_code == 200
    assert "inference_requests_total" in r.text


def test_sse_stream_emits_a_snapshot_event() -> None:
    c = client()
    with c.stream("GET", "/api/stream?limit=1") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("data:"):
                payload = json.loads(line[len("data:") :].strip())
                assert "metrics" in payload and "pool" in payload
                break
