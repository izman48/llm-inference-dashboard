"""FastAPI gateway — the live system tying the pure pieces together over sim
workers, plus the API the React console drives.

The pool advances via a background loop in production (``run_background=True``,
which also pumps the load generator) and via explicit ``POST /api/step`` calls in
tests, so contract tests stay deterministic.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from inference_demo.autoscaler import AutoscalerConfig
from inference_demo.loadgen import LoadGenerator, LoadPreset
from inference_demo.metrics import PROMETHEUS_CONTENT_TYPE
from inference_demo.pool import PoolManager, build_pool
from inference_demo.routing.strategies import STRATEGY_NAMES
from inference_demo.types import Priority, Request, WorkerId


class SubmitBody(BaseModel):
    prompt_tokens: int = Field(gt=0)
    max_tokens: int = Field(gt=0)
    priority: Literal["interactive", "batch"] = "interactive"
    prefix_key: str | None = None


class StepBody(BaseModel):
    n: int = Field(default=1, ge=1, le=10_000)


class StrategyBody(BaseModel):
    name: str


class AutoscalerBody(BaseModel):
    enabled: bool | None = None
    min_workers: int | None = Field(default=None, ge=1)
    max_workers: int | None = Field(default=None, ge=1)
    target_queue_depth: float | None = Field(default=None, gt=0)


class LoadGenBody(BaseModel):
    preset: Literal["steady", "burst", "spike"] = "steady"
    base_rate: float = Field(default=20.0, gt=0)


class KillBody(BaseModel):
    worker_id: str | None = None


class _State:
    """Mutable per-app state: request id counter + the active load generator."""

    def __init__(self) -> None:
        self.req_seq = 0
        self.loadgen: LoadGenerator | None = None


def create_app(pool: PoolManager, *, run_background: bool = False, tick_s: float = 0.05) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        if run_background:
            task = asyncio.create_task(_run_loop(pool, tick_s, get_loadgen))
        try:
            yield
        finally:
            if task is not None:
                task.cancel()

    app = FastAPI(title="inference-demo control plane", lifespan=lifespan)
    state = _State()

    def get_loadgen() -> LoadGenerator | None:
        return state.loadgen

    def next_req_id() -> str:
        n = state.req_seq
        state.req_seq = n + 1
        return f"u{n}"

    @app.post("/api/submit")
    def submit(body: SubmitBody) -> dict[str, str]:
        req = Request(
            id=next_req_id(),
            prompt_tokens=body.prompt_tokens,
            max_tokens=body.max_tokens,
            priority=Priority(body.priority),
            arrival_ts=pool.clock,
            prefix_key=body.prefix_key,
        )
        wid = pool.submit(req)
        return {"req_id": req.id, "worker_id": str(wid)}

    @app.post("/api/step")
    def step(body: StepBody) -> dict[str, float]:
        for _ in range(body.n):
            pool.step()
        return {"clock_s": round(pool.clock, 3)}

    @app.get("/api/snapshot")
    def snapshot() -> dict[str, object]:
        return pool.snapshot()

    @app.get("/api/strategies")
    def strategies() -> dict[str, list[str]]:
        return {"strategies": STRATEGY_NAMES}

    @app.post("/api/strategy")
    def set_strategy(body: StrategyBody) -> dict[str, str]:
        if body.name not in STRATEGY_NAMES:
            raise HTTPException(status_code=422, detail=f"unknown strategy: {body.name!r}")
        pool.set_strategy(body.name)
        return {"strategy": body.name}

    @app.post("/api/autoscaler")
    def set_autoscaler(body: AutoscalerBody) -> dict[str, object]:
        c = pool.autoscaler.config
        new_cfg = AutoscalerConfig(
            min_workers=body.min_workers if body.min_workers is not None else c.min_workers,
            max_workers=body.max_workers if body.max_workers is not None else c.max_workers,
            target_queue_depth=(
                body.target_queue_depth
                if body.target_queue_depth is not None
                else c.target_queue_depth
            ),
            scale_down_queue_depth=c.scale_down_queue_depth,
            cooldown_s=c.cooldown_s,
        )
        pool.set_autoscaler(config=new_cfg, enabled=body.enabled)
        return pool.pool_snapshot()["autoscaler"]  # type: ignore[return-value]

    @app.post("/api/loadgen")
    def start_loadgen(body: LoadGenBody) -> dict[str, str]:
        state.loadgen = LoadGenerator(preset=LoadPreset(body.preset), base_rate=body.base_rate)
        return {"preset": body.preset, "base_rate": str(body.base_rate)}

    @app.post("/api/loadgen/stop")
    def stop_loadgen() -> dict[str, bool]:
        state.loadgen = None
        return {"stopped": True}

    @app.post("/api/workers/kill")
    def kill_worker(body: KillBody) -> dict[str, str | None]:
        wid = WorkerId(body.worker_id) if body.worker_id else None
        killed = pool.kill_worker(wid)
        return {"killed": str(killed) if killed is not None else None}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(content=pool.metrics.prometheus(), media_type=PROMETHEUS_CONTENT_TYPE)

    @app.get("/api/stream")
    async def stream(limit: int | None = None) -> StreamingResponse:
        # limit bounds the number of events (used by tests); None = infinite (prod).
        async def gen() -> AsyncIterator[str]:
            sent = 0
            while limit is None or sent < limit:
                yield f"data: {json.dumps(pool.snapshot())}\n\n"
                sent += 1
                if limit is None or sent < limit:
                    await asyncio.sleep(tick_s)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


async def _run_loop(
    pool: PoolManager, tick_s: float, get_loadgen: Callable[[], LoadGenerator | None]
) -> None:  # pragma: no cover - timing loop, exercised in live runs
    while True:
        lg = get_loadgen()
        if lg is not None:
            for req in lg.sample(tick_s):
                pool.submit(req)
        pool.step()
        await asyncio.sleep(tick_s)


# Module-level app for `uvicorn inference_demo.gateway.app:app` (background on).
app = create_app(build_pool(), run_background=True)
