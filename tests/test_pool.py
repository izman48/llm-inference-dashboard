"""PoolManager ties the pure pieces (workers + router + autoscaler + metrics) into
a steppable live system over sim workers. Driven deterministically here.
"""

from __future__ import annotations

import pytest

from inference_demo.pool import build_pool
from inference_demo.types import Priority, Request


def _req(rid: str, *, out: int = 10, prompt: int = 50) -> Request:
    return Request(
        id=rid,
        prompt_tokens=prompt,
        max_tokens=out,
        priority=Priority.INTERACTIVE,
        arrival_ts=0.0,
        prefix_key=None,
    )


def test_submit_routes_to_a_real_worker() -> None:
    pool = build_pool(n_workers=2, autoscale=False)
    wid = pool.submit(_req("r0"))
    assert wid in {s.worker_id for s in pool.worker_states()}
    # one request is now outstanding somewhere in the pool
    assert sum(s.queue_depth + s.in_flight for s in pool.worker_states()) == 1


def test_requests_complete_and_metrics_fill_in() -> None:
    pool = build_pool(n_workers=2, autoscale=False)
    for i in range(8):
        pool.submit(_req(f"r{i}", out=5))
    for _ in range(500):
        if all(s.queue_depth + s.in_flight == 0 for s in pool.worker_states()):
            break
        pool.step()
    snap = pool.metrics.snapshot()
    assert snap.completed_total == 8
    assert snap.tokens_total == 40  # 8 requests * 5 tokens
    assert snap.e2e_p50_s > 0.0


def test_autoscaler_adds_workers_under_load() -> None:
    pool = build_pool(n_workers=1, autoscale=True, min_workers=1, max_workers=4)
    for i in range(60):  # flood a single worker
        pool.submit(_req(f"r{i}", out=20))
    peak = 1
    for _ in range(400):
        pool.step()
        peak = max(peak, pool.num_workers)
    assert 1 < peak <= 4  # scaled up under load (then back down once it drained)


def test_autoscaler_removes_idle_workers_down_to_min() -> None:
    pool = build_pool(n_workers=4, autoscale=True, min_workers=1, max_workers=4)
    for _ in range(800):  # no load at all -> idle workers should be reclaimed
        pool.step()
    assert pool.num_workers == 1


def test_pool_recovers_to_min_workers_after_killing_all() -> None:
    # Regression: killing every worker must not wedge the pool at 0 — the
    # autoscaler's min floor brings it back (and the live loop can't crash).
    pool = build_pool(n_workers=2, autoscale=True, min_workers=1, max_workers=4)
    while pool.kill_worker() is not None:
        pass
    assert pool.num_workers == 0
    for _ in range(50):
        pool.step()
    assert pool.num_workers >= 1


def test_reset_restores_initial_pool_and_clears_metrics() -> None:
    pool = build_pool(n_workers=2, autoscale=False)
    for i in range(8):
        pool.submit(_req(f"r{i}", out=5))
    for _ in range(300):
        pool.step()
    assert pool.metrics.snapshot().completed_total > 0
    pool.reset()
    assert pool.num_workers == 2
    assert pool.clock == 0.0
    snap = pool.metrics.snapshot()
    assert snap.completed_total == 0
    assert snap.throughput_tok_s == 0.0


def test_kill_worker_removes_it() -> None:
    pool = build_pool(n_workers=3, autoscale=False)
    before = pool.num_workers
    killed = pool.kill_worker()
    assert killed is not None
    assert pool.num_workers == before - 1


def test_strategy_swap_changes_routing_name() -> None:
    pool = build_pool(n_workers=2, autoscale=False)
    pool.set_strategy("round-robin")
    assert pool.router.strategy_name == "round-robin"


def test_real_backend_advances_by_wall_clock_not_fixed_step() -> None:
    # sim advances by the modelled step (deterministic). A real backend advances by
    # measured wall time, so a slow decode step isn't credited to a fixed 0.05s —
    # which would otherwise inflate throughput and shrink TTFT.
    fake = {"t": 100.0}
    pool = build_pool(n_workers=1, backend="sim", autoscale=False)
    pool._time_fn = lambda: fake["t"]  # inject a controllable clock
    pool.step()
    assert pool.clock == pool.step_s  # sim: modelled step, ignores wall clock

    pool.set_backend("openai", base_url="http://x:11434")  # real backend (resets the clock)
    pool.step()  # first real step seeds with step_s
    seeded = pool.clock
    fake["t"] = 100.7  # 0.7s of real time elapses before the next step
    pool.step()
    assert pool.clock - seeded == pytest.approx(0.7)  # advanced by wall time, not step_s


def test_set_backend_switches_and_rebuilds_pool() -> None:
    pool = build_pool(n_workers=2, backend="sim", autoscale=False)
    assert pool.backend == "sim"
    # switch to the endpoint backend (constructs OpenAIWorkers; no network here)
    pool.set_backend("openai", base_url="http://example:11434", model="qwen2.5:0.5b")
    assert pool.backend == "openai"
    assert pool.endpoint == {"base_url": "http://example:11434", "model": "qwen2.5:0.5b"}
    assert pool.num_workers == 2  # rebuilt to the initial worker count
    # and back to sim
    pool.set_backend("sim")
    assert pool.backend == "sim"
    assert pool.num_workers == 2
