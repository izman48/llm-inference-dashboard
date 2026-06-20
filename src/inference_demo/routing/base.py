"""The routing seam: the ``RoutingStrategy`` protocol.

A strategy is a pure decision rule — given the current worker states and a
request, return the chosen worker. No model, no network, no I/O (a couple carry
tiny internal state: a round-robin cursor, an injected RNG). The router filters
out unhealthy workers before calling a strategy, so strategies may assume the
list they receive is non-empty and all-eligible.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from inference_demo.types import Request, WorkerId, WorkerState


@runtime_checkable
class RoutingStrategy(Protocol):
    name: str

    def choose(self, states: list[WorkerState], req: Request) -> WorkerId:
        """Pick a worker for ``req`` from ``states`` (non-empty, all healthy)."""
        ...
