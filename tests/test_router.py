"""The Router wraps a strategy, filters unhealthy workers, and hot-swaps the
strategy at runtime (the live switcher behind the console).
"""

from __future__ import annotations

import pytest

from inference_demo.routing.router import NoHealthyWorkersError, Router
from inference_demo.routing.strategies import LeastQueueDepth, RoundRobin
from inference_demo.types import Priority, Request, WorkerId, WorkerState


def ws(wid: str, *, q: int = 0, healthy: bool = True) -> WorkerState:
    return WorkerState(
        worker_id=WorkerId(wid),
        queue_depth=q,
        pending_tokens=0,
        in_flight=0,
        tok_per_s=100.0,
        healthy=healthy,
        speed_profile=1.0,
        cached_prefixes=frozenset(),
    )


def req() -> Request:
    return Request("r", 10, 10, Priority.INTERACTIVE, 0.0, None)


def test_router_skips_unhealthy_workers() -> None:
    # 'a' is the least loaded but unhealthy -> must be skipped
    states = [ws("a", q=0, healthy=False), ws("b", q=2), ws("c", q=5)]
    router = Router(LeastQueueDepth())
    assert router.route(states, req()) == WorkerId("b")


def test_router_raises_when_no_healthy_workers() -> None:
    states = [ws("a", healthy=False), ws("b", healthy=False)]
    router = Router(LeastQueueDepth())
    with pytest.raises(NoHealthyWorkersError):
        router.route(states, req())


def test_router_raises_on_empty_pool() -> None:
    router = Router(LeastQueueDepth())
    with pytest.raises(NoHealthyWorkersError):
        router.route([], req())


def test_router_hot_swaps_strategy() -> None:
    states = [ws("a", q=5), ws("b", q=0)]
    router = Router(RoundRobin())
    assert router.route(states, req()) == WorkerId("a")  # round-robin: first
    assert router.strategy_name == "round-robin"

    router.set_strategy(LeastQueueDepth())
    assert router.strategy_name == "least-queue-depth"
    assert router.route(states, req()) == WorkerId("b")  # now load-aware: least
