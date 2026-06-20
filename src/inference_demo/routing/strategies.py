"""The routing-strategy spread. The contrast IS the demo: naive baselines make
the smart strategies legible. Each is a pure decision rule over WorkerState.

Naive baselines:      random, round-robin
Load-aware:           least-queue-depth, least-pending-tokens, power-of-two-choices
Inference-native:     prefix-affinity, priority/SLA, hardware-aware

The router (router.py) filters unhealthy workers before calling ``choose``, so
strategies assume a non-empty, all-healthy list.
"""

from __future__ import annotations

import random

from inference_demo.routing.base import RoutingStrategy
from inference_demo.types import Priority as ReqPriority  # enum; the class below is named Priority
from inference_demo.types import Request, WorkerId, WorkerState


def _req_load(s: WorkerState) -> int:
    """Outstanding requests resident at a worker (queued + running)."""
    return s.queue_depth + s.in_flight


def _least_loaded(states: list[WorkerState]) -> WorkerId:
    return min(states, key=lambda s: (_req_load(s), str(s.worker_id))).worker_id


def _least_pending(states: list[WorkerState]) -> WorkerId:
    return min(states, key=lambda s: (s.pending_tokens, str(s.worker_id))).worker_id


# ---- naive baselines (demo villains) ---------------------------------------


class Random:
    name = "random"

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        return self._rng.choice(states).worker_id


class RoundRobin:
    """Cycle through workers in order, ignoring load — breaks under skew."""

    name = "round-robin"

    def __init__(self) -> None:
        self._i = 0

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        wid = states[self._i % len(states)].worker_id
        self._i += 1
        return wid


# ---- load-aware (honest defaults) ------------------------------------------


class LeastQueueDepth:
    """Fewest outstanding requests. A big jump over round-robin under skew."""

    name = "least-queue-depth"

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        return _least_loaded(states)


class LeastPendingTokens:
    """Fewest estimated remaining *tokens* — a 2000-token request != a 10-token one."""

    name = "least-pending-tokens"

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        return _least_pending(states)


class PowerOfTwoChoices:
    """Sample two workers, route to the lighter. Near-optimal at O(1); dodges the
    thundering-herd that global least-loaded hits at scale."""

    name = "power-of-two-choices"

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        if len(states) <= 1:
            return states[0].worker_id
        a, b = self._rng.sample(states, 2)
        return min((a, b), key=lambda s: (_req_load(s), str(s.worker_id))).worker_id


# ---- inference-native (differentiators) ------------------------------------


class PrefixAffinity:
    """Route requests sharing a prompt prefix to the worker holding its cached KV,
    reusing it. Falls back to least-loaded on a cache miss. Proves serving is
    stateful (cf. GORGO)."""

    name = "prefix-affinity"

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        if req.prefix_key is not None:
            holders = [s for s in states if req.prefix_key in s.cached_prefixes]
            if holders:
                return _least_loaded(holders)  # least-loaded among cache holders
        return _least_loaded(states)


class Priority:
    """SLA-class routing: interactive jumps onto the worker with the least work;
    batch backfills the busiest worker, reserving idle capacity for interactive."""

    name = "priority"

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        if req.priority == ReqPriority.INTERACTIVE:
            return _least_pending(states)
        busiest = max(s.pending_tokens for s in states)
        return min(
            (s for s in states if s.pending_tokens == busiest),
            key=lambda s: str(s.worker_id),
        ).worker_id


class HardwareAware:
    """Latency-sensitive traffic -> fastest workers; throughput traffic -> slow
    workers, keeping the fast ones free for latency. The compute-agnostic story
    without real heterogeneous hardware."""

    name = "hardware-aware"

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        if req.priority == ReqPriority.INTERACTIVE:  # fastest first
            return min(
                states, key=lambda s: (-s.speed_profile, _req_load(s), str(s.worker_id))
            ).worker_id
        return min(  # slowest first, reserving fast workers for latency-sensitive traffic
            states, key=lambda s: (s.speed_profile, _req_load(s), str(s.worker_id))
        ).worker_id


# ---- registry / factory ----------------------------------------------------

STRATEGY_NAMES: list[str] = [
    "random",
    "round-robin",
    "least-queue-depth",
    "least-pending-tokens",
    "power-of-two-choices",
    "prefix-affinity",
    "priority",
    "hardware-aware",
]


def make_strategy(name: str, *, seed: int | None = None) -> RoutingStrategy:
    """Build a strategy by name. ``seed`` makes RNG-based strategies deterministic."""
    rng = random.Random(seed) if seed is not None else None
    if name == "random":
        return Random(rng=rng)
    if name == "round-robin":
        return RoundRobin()
    if name == "least-queue-depth":
        return LeastQueueDepth()
    if name == "least-pending-tokens":
        return LeastPendingTokens()
    if name == "power-of-two-choices":
        return PowerOfTwoChoices(rng=rng)
    if name == "prefix-affinity":
        return PrefixAffinity()
    if name == "priority":
        return Priority()
    if name == "hardware-aware":
        return HardwareAware()
    raise ValueError(f"unknown routing strategy: {name!r}")
