"""Each routing strategy is a pure decision rule — test it against fabricated
WorkerState lists so the decision is provable, deterministically, with no workers
or network in sight. The naive strategies are the baseline that makes the smart
ones legible, so they get tested too.
"""

from __future__ import annotations

import random
from collections.abc import Iterable

from inference_demo.routing.base import RoutingStrategy
from inference_demo.routing.strategies import (
    STRATEGY_NAMES,
    HardwareAware,
    LeastPendingTokens,
    LeastQueueDepth,
    PowerOfTwoChoices,
    PrefixAffinity,
    RoundRobin,
    make_strategy,
)
from inference_demo.routing.strategies import (
    Priority as PriorityStrategy,
)
from inference_demo.routing.strategies import (
    Random as RandomStrategy,
)
from inference_demo.types import Priority, Request, WorkerId, WorkerState


def ws(
    wid: str,
    *,
    q: int = 0,
    inflight: int = 0,
    pending: int = 0,
    healthy: bool = True,
    speed: float = 1.0,
    prefixes: Iterable[str] = (),
) -> WorkerState:
    return WorkerState(
        worker_id=WorkerId(wid),
        queue_depth=q,
        pending_tokens=pending,
        in_flight=inflight,
        tok_per_s=100.0,
        healthy=healthy,
        speed_profile=speed,
        cached_prefixes=frozenset(prefixes),
    )


def req(*, priority: Priority = Priority.INTERACTIVE, prefix: str | None = None) -> Request:
    return Request(
        id="r",
        prompt_tokens=100,
        max_tokens=50,
        priority=priority,
        arrival_ts=0.0,
        prefix_key=prefix,
    )


# ---- naive baselines -------------------------------------------------------


def test_random_is_seedable_and_in_range() -> None:
    states = [ws("a"), ws("b"), ws("c")]
    s1 = RandomStrategy(rng=random.Random(7))
    s2 = RandomStrategy(rng=random.Random(7))
    picks1 = [s1.choose(states, req()) for _ in range(10)]
    picks2 = [s2.choose(states, req()) for _ in range(10)]
    assert picks1 == picks2  # same seed -> same sequence
    assert all(p in {WorkerId("a"), WorkerId("b"), WorkerId("c")} for p in picks1)


def test_round_robin_cycles_in_order() -> None:
    states = [ws("a"), ws("b"), ws("c")]
    rr = RoundRobin()
    seq = [rr.choose(states, req()) for _ in range(7)]
    assert seq == [WorkerId(x) for x in ["a", "b", "c", "a", "b", "c", "a"]]


def test_round_robin_ignores_load() -> None:
    # the villain: cycles even onto a hammered worker
    rr = RoundRobin()
    states = [ws("a", inflight=99), ws("b")]
    assert rr.choose(states, req()) == WorkerId("a")


# ---- load-aware ------------------------------------------------------------


def test_least_queue_depth_picks_fewest_outstanding() -> None:
    states = [ws("a", q=3, inflight=2), ws("b", q=0, inflight=1), ws("c", q=5)]
    assert LeastQueueDepth().choose(states, req()) == WorkerId("b")


def test_least_queue_depth_tie_breaks_by_worker_id() -> None:
    states = [ws("b", q=1), ws("a", q=1)]
    assert LeastQueueDepth().choose(states, req()) == WorkerId("a")


def test_least_pending_tokens_differs_from_request_count() -> None:
    # 'a' has fewer requests but a huge token backlog; 'b' has more requests,
    # less actual work. Token-aware routing must prefer 'b'.
    states = [ws("a", q=1, pending=2000), ws("b", q=4, pending=50)]
    assert LeastQueueDepth().choose(states, req()) == WorkerId("a")  # by count
    assert LeastPendingTokens().choose(states, req()) == WorkerId("b")  # by work


def test_power_of_two_picks_lighter_of_its_two_samples() -> None:
    # Three workers; the globally-lightest ('c') must NOT be sampled, proving Po2
    # only ever picks the lighter of its two random samples, not the global min.
    states = [ws("a", inflight=10), ws("b", inflight=5), ws("c", inflight=0)]
    seed = 4  # chosen so the sample is {a, b} and excludes the global-lightest 'c'
    sampled = random.Random(seed).sample(states, 2)
    lighter = min(sampled, key=lambda s: s.in_flight + s.queue_depth).worker_id
    assert WorkerId("c") not in {s.worker_id for s in sampled}  # guard the premise
    assert PowerOfTwoChoices(rng=random.Random(seed)).choose(states, req()) == lighter


def test_power_of_two_with_single_worker_returns_it() -> None:
    assert PowerOfTwoChoices(rng=random.Random(0)).choose([ws("solo")], req()) == WorkerId("solo")


# ---- inference-native ------------------------------------------------------


def test_prefix_affinity_routes_to_cache_holder_even_if_loaded() -> None:
    states = [ws("a", inflight=0), ws("b", inflight=20, prefixes=["sys"])]
    assert PrefixAffinity().choose(states, req(prefix="sys")) == WorkerId("b")


def test_prefix_affinity_falls_back_to_least_loaded_on_miss() -> None:
    states = [ws("a", inflight=2), ws("b", inflight=0)]
    assert PrefixAffinity().choose(states, req(prefix="unseen")) == WorkerId("b")
    assert PrefixAffinity().choose(states, req(prefix=None)) == WorkerId("b")


def test_prefix_affinity_picks_least_loaded_holder() -> None:
    states = [ws("a", inflight=9, prefixes=["sys"]), ws("b", inflight=1, prefixes=["sys"])]
    assert PrefixAffinity().choose(states, req(prefix="sys")) == WorkerId("b")


def test_priority_interactive_goes_to_least_work_batch_backfills() -> None:
    states = [ws("a", pending=10), ws("b", pending=500), ws("c", pending=100)]
    strat = PriorityStrategy()
    assert strat.choose(states, req(priority=Priority.INTERACTIVE)) == WorkerId("a")
    # batch backfills the busiest, reserving idle workers for interactive traffic
    assert strat.choose(states, req(priority=Priority.BATCH)) == WorkerId("b")


def test_hardware_aware_sends_interactive_to_fast_batch_to_slow() -> None:
    states = [ws("fast", speed=2.0), ws("mid", speed=1.0), ws("slow", speed=0.5)]
    strat = HardwareAware()
    assert strat.choose(states, req(priority=Priority.INTERACTIVE)) == WorkerId("fast")
    assert strat.choose(states, req(priority=Priority.BATCH)) == WorkerId("slow")


# ---- factory / registry ----------------------------------------------------


def test_make_strategy_builds_every_named_strategy() -> None:
    assert set(STRATEGY_NAMES) == {
        "random",
        "round-robin",
        "least-queue-depth",
        "least-pending-tokens",
        "power-of-two-choices",
        "prefix-affinity",
        "priority",
        "hardware-aware",
    }
    for name in STRATEGY_NAMES:
        strat = make_strategy(name, seed=0)
        assert isinstance(strat, RoutingStrategy)
        assert strat.name == name
        assert strat.choose([ws("a"), ws("b")], req()) in {WorkerId("a"), WorkerId("b")}
