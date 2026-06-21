"""Synthetic traffic to drive demos and benchmarks.

* ``plan_arrivals`` — a pure, seedable schedule (Poisson arrivals via thinning)
  used by tests and offline runs.
* ``LoadGenerator`` — the live counterpart the gateway loop pumps each tick.

Presets shape the arrival rate over time: STEADY (flat), BURST (square wave),
SPIKE (low baseline with a sharp surge in the middle of the cycle).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from inference_demo.types import Priority, Request

_PREFIXES = ["sys-assistant", "sys-coder", "conv-42"]


class LoadPreset(Enum):
    STEADY = "steady"
    BURST = "burst"
    SPIKE = "spike"


@dataclass(frozen=True)
class PlannedRequest:
    t_s: float
    req: Request


def rate_at(preset: LoadPreset, base_rate: float, t_s: float, duration_s: float) -> float:
    """Instantaneous arrival rate (req/s) at time ``t_s`` for a preset."""
    if preset is LoadPreset.STEADY:
        return base_rate
    if preset is LoadPreset.BURST:
        period = max(1e-9, duration_s / 4)
        phase = (t_s % period) / period
        return base_rate * 2.0 if phase < 0.5 else base_rate * 0.25
    # SPIKE
    if 0.4 * duration_s <= t_s <= 0.6 * duration_s:
        return base_rate * 4.0
    return base_rate * 0.3


def _peak_rate(preset: LoadPreset, base_rate: float) -> float:
    return {
        LoadPreset.STEADY: base_rate,
        LoadPreset.BURST: base_rate * 2.0,
        LoadPreset.SPIKE: base_rate * 4.0,
    }[preset]


def _make_request(rng: random.Random, req_id: str) -> Request:
    long_tail = rng.random() < 0.2
    out = rng.randint(200, 400) if long_tail else rng.randint(8, 48)
    priority = Priority.BATCH if rng.random() < 0.15 else Priority.INTERACTIVE
    prefix = rng.choice(_PREFIXES) if rng.random() < 0.3 else None
    return Request(
        id=req_id,
        prompt_tokens=rng.randint(16, 512),
        max_tokens=out,
        priority=priority,
        arrival_ts=0.0,
        prefix_key=prefix,
    )


def plan_arrivals(
    *, preset: LoadPreset, base_rate: float, duration_s: float, seed: int
) -> list[PlannedRequest]:
    """Generate a reproducible arrival schedule via Poisson thinning."""
    rng = random.Random(seed)
    peak = _peak_rate(preset, base_rate)
    plan: list[PlannedRequest] = []
    if peak <= 0:
        return plan
    t = 0.0
    i = 0
    while True:
        t += rng.expovariate(peak)
        if t > duration_s:
            break
        if rng.random() <= rate_at(preset, base_rate, t, duration_s) / peak:  # thinning accept
            plan.append(PlannedRequest(t_s=t, req=_make_request(rng, f"r{i}")))
            i += 1
    return plan


class LoadGenerator:
    """Live generator: ``sample(dt)`` returns the requests that arrived in the last
    ``dt`` seconds, following the preset's rate. ``cycle_s`` is the period used by
    BURST/SPIKE since a live stream has no fixed duration."""

    def __init__(
        self,
        *,
        preset: LoadPreset,
        base_rate: float,
        seed: int | None = None,
        cycle_s: float = 20.0,
    ) -> None:
        self.preset = preset
        self.base_rate = base_rate
        self.cycle_s = cycle_s
        self._rng = random.Random(seed)
        self._t = 0.0
        self._n = 0

    def sample(self, dt_s: float) -> list[Request]:
        out: list[Request] = []
        end = self._t + dt_s
        rate = rate_at(self.preset, self.base_rate, self._t, self.cycle_s)
        if rate > 0:
            t = self._t
            while True:
                t += self._rng.expovariate(rate)
                if t >= end:
                    break
                out.append(_make_request(self._rng, f"g{self._n}"))
                self._n += 1
        self._t = end
        return out
