"""PoolManager ties the pure pieces (workers + router + autoscaler + metrics) into
a steppable live system over sim workers. Driven deterministically here.
"""

from __future__ import annotations

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
