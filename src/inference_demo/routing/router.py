"""The Router: one switchable seam in front of the strategy spread.

It owns the current strategy (hot-swappable at runtime — the live switcher behind
the console), filters out unhealthy workers, and delegates the decision. Keeping
health-filtering here means every strategy stays a clean decision rule.
"""

from __future__ import annotations

from inference_demo.routing.base import RoutingStrategy
from inference_demo.types import Request, WorkerId, WorkerState


class NoHealthyWorkersError(RuntimeError):
    """Raised when there is no healthy worker available to route to."""


class Router:
    def __init__(self, strategy: RoutingStrategy) -> None:
        self._strategy = strategy

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    def set_strategy(self, strategy: RoutingStrategy) -> None:
        """Swap the routing strategy live."""
        self._strategy = strategy

    def route(self, states: list[WorkerState], req: Request) -> WorkerId:
        healthy = [s for s in states if s.healthy]
        if not healthy:
            raise NoHealthyWorkersError("no healthy workers available to route to")
        return self._strategy.choose(healthy, req)
