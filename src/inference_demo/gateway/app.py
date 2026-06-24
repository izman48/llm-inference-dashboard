"""FastAPI gateway — the live system tying the pure pieces together over sim
workers, plus the API the React console drives.

The pool advances via a background loop in production (``run_background=True``,
which also pumps the load generator) and via explicit ``POST /api/step`` calls in
tests, so contract tests stay deterministic.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from inference_demo.autoscaler import AutoscalerConfig
from inference_demo.loadgen import LoadGenerator, LoadPreset
from inference_demo.metrics import PROMETHEUS_CONTENT_TYPE
from inference_demo.pool import PoolManager, build_pool
from inference_demo.routing.strategies import STRATEGY_NAMES
from inference_demo.types import Priority, Request, WorkerId


@dataclass(frozen=True)
class GatewayConfig:
    """Deployment guardrails. Defaults are permissive (local dev); the public
    demo sets these via env to stay sim-only, gated, and capped (see CLAUDE.md)."""

    control_token: str | None = None  # if set, POST/control endpoints require it
    demo: bool = False  # force sim backend, apply caps
    max_workers_cap: int = 1024
    max_rate_cap: float = 100_000.0
    max_tokens_cap: int = 1_000_000
    # Real-model workers each load their own model copy, so cap that pool tightly to
    # avoid OOM-ing the host when someone cranks max workers. Override per-machine.
    realmodel_max_workers: int = 4

    @classmethod
    def from_env(cls) -> GatewayConfig:
        return cls(
            control_token=os.environ.get("CONTROL_TOKEN") or None,
            demo=os.environ.get("PUBLIC_DEMO", "").lower() in ("1", "true", "yes"),
            max_workers_cap=int(os.environ.get("PUBLIC_MAX_WORKERS", "1024")),
            max_rate_cap=float(os.environ.get("PUBLIC_MAX_RATE", "100000")),
            max_tokens_cap=int(os.environ.get("PUBLIC_MAX_TOKENS", "1000000")),
            realmodel_max_workers=int(os.environ.get("REALMODEL_MAX_WORKERS", "4")),
        )


class SubmitBody(BaseModel):
    prompt_tokens: int = Field(gt=0)
    max_tokens: int = Field(gt=0)
    priority: Literal["interactive", "batch"] = "interactive"
    prefix_key: str | None = None


class StepBody(BaseModel):
    n: int = Field(default=1, ge=1, le=10_000)


class StrategyBody(BaseModel):
    name: str


class BackendBody(BaseModel):
    backend: Literal["sim", "openai", "realmodel"]
    base_url: str | None = None
    model: str | None = None


class BatchingBody(BaseModel):
    continuous: bool


def _available_backends() -> list[dict[str, object]]:
    """Which backends this process can switch to. sim + openai always; realmodel only
    when the heavy deps are installed (host-native; never inside the Linux Docker image)."""
    realmodel = (
        importlib.util.find_spec("torch") is not None
        and importlib.util.find_spec("transformers") is not None
    )
    return [
        {"id": "sim", "label": "Sim", "available": True, "reason": ""},
        {"id": "openai", "label": "Endpoint (self-hosted)", "available": True, "reason": ""},
        {
            "id": "realmodel",
            "label": "Real model (self-hosted)",
            "available": realmodel,
            "reason": ""
            if realmodel
            else "host-native only (needs the realmodel extra); not in this deployment",
        },
    ]


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


def create_app(
    pool: PoolManager,
    *,
    run_background: bool = False,
    tick_s: float = 0.05,
    config: GatewayConfig | None = None,
) -> FastAPI:
    cfg = config or GatewayConfig()

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

    def require_control(x_control_token: str | None = Header(default=None)) -> None:
        # Gate mutating endpoints behind a shared secret when one is configured.
        if cfg.control_token and x_control_token != cfg.control_token:
            raise HTTPException(status_code=401, detail="invalid or missing control token")

    gated = [Depends(require_control)]

    @app.post("/api/submit", dependencies=gated)
    def submit(body: SubmitBody) -> dict[str, str]:
        req = Request(
            id=next_req_id(),
            prompt_tokens=min(body.prompt_tokens, cfg.max_tokens_cap),
            max_tokens=min(body.max_tokens, cfg.max_tokens_cap),
            priority=Priority(body.priority),
            arrival_ts=pool.clock,
            prefix_key=body.prefix_key,
        )
        wid = pool.submit(req)
        return {"req_id": req.id, "worker_id": str(wid)}

    @app.post("/api/step", dependencies=gated)
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

    @app.post("/api/strategy", dependencies=gated)
    def set_strategy(body: StrategyBody) -> dict[str, str]:
        if body.name not in STRATEGY_NAMES:
            raise HTTPException(status_code=422, detail=f"unknown strategy: {body.name!r}")
        pool.set_strategy(body.name)
        return {"strategy": body.name}

    @app.get("/api/backends")
    def backends() -> dict[str, object]:
        # `switchable` is false on the public demo: a hosted box must stay sim-only,
        # never taking an arbitrary endpoint URL server-side (SSRF). See README.
        return {
            "current": pool.backend,
            "switchable": not cfg.demo,
            "available": _available_backends(),
            "endpoint": pool.endpoint,
        }

    @app.post("/api/backend", dependencies=gated)
    def set_backend(body: BackendBody) -> dict[str, object]:
        if cfg.demo:
            raise HTTPException(403, "backend switching is disabled on the public demo (sim-only)")
        available = {b["id"] for b in _available_backends() if b["available"]}
        if body.backend not in available:
            raise HTTPException(422, detail=f"backend not available here: {body.backend!r}")
        pool.set_backend(body.backend, base_url=body.base_url, model=body.model)
        return {"backend": pool.backend, "endpoint": pool.endpoint}

    @app.post("/api/batching", dependencies=gated)
    def set_batching(body: BatchingBody) -> dict[str, object]:
        # Continuous vs static batching — only meaningful for the real-model backend
        # (our decode loop); a no-op for sim/openai, which we surface to the caller.
        pool.set_batching(body.continuous)
        effective = pool.backend == "realmodel"
        return {"continuous": body.continuous, "applies": effective, "backend": pool.backend}

    @app.post("/api/autoscaler", dependencies=gated)
    def set_autoscaler(body: AutoscalerBody) -> dict[str, object]:
        c = pool.autoscaler.config
        max_workers = body.max_workers if body.max_workers is not None else c.max_workers
        max_workers = min(max_workers, cfg.max_workers_cap)  # hard cap
        if pool.backend == "realmodel":
            max_workers = min(max_workers, cfg.realmodel_max_workers)  # one model copy / worker
        min_workers = body.min_workers if body.min_workers is not None else c.min_workers
        target = body.target_queue_depth
        if target is None:
            target = c.target_queue_depth
        # Keep the target coherent: within the worker cap and above the scale-down line.
        target = min(max(target, c.scale_down_queue_depth), float(max_workers))
        new_cfg = AutoscalerConfig(
            min_workers=min(min_workers, max_workers),
            max_workers=max_workers,
            target_queue_depth=target,
            scale_down_queue_depth=c.scale_down_queue_depth,
            cooldown_s=c.cooldown_s,
        )
        pool.set_autoscaler(config=new_cfg, enabled=body.enabled)
        return pool.pool_snapshot()["autoscaler"]  # type: ignore[return-value]

    @app.post("/api/loadgen", dependencies=gated)
    def start_loadgen(body: LoadGenBody) -> dict[str, object]:
        rate = min(body.base_rate, cfg.max_rate_cap)  # hard cap
        state.loadgen = LoadGenerator(preset=LoadPreset(body.preset), base_rate=rate)
        return {"preset": body.preset, "base_rate": rate}

    @app.post("/api/loadgen/stop", dependencies=gated)
    def stop_loadgen() -> dict[str, bool]:
        state.loadgen = None
        return {"stopped": True}

    @app.post("/api/workers/kill", dependencies=gated)
    def kill_worker(body: KillBody) -> dict[str, str | None]:
        wid = WorkerId(body.worker_id) if body.worker_id else None
        killed = pool.kill_worker(wid)
        return {"killed": str(killed) if killed is not None else None}

    @app.post("/api/reset", dependencies=gated)
    def reset() -> dict[str, object]:
        # Recover a wedged or messy demo: stop load and restore the starting pool +
        # cleared metrics, without restarting the server.
        state.loadgen = None
        pool.reset()
        return {"reset": True, "num_workers": pool.num_workers}

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

    # Optionally serve the built console from the same container (co-host deploy).
    # Mounted last so /api/* and /metrics (registered above) take precedence.
    ui_dist = os.environ.get("UI_DIST")
    if ui_dist and os.path.isdir(ui_dist):
        app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")

    return app


async def _run_loop(
    pool: PoolManager, tick_s: float, get_loadgen: Callable[[], LoadGenerator | None]
) -> None:  # pragma: no cover - timing loop, exercised in live runs
    # This loop is the heartbeat: every tick advances the pool and pumps load. It
    # must never die, or the whole console freezes (clock stops, no autoscaling).
    # So each tick is isolated in try/except, and we only submit when a worker
    # exists — killing every worker mid-demo can no longer crash the loop (the
    # autoscaler's min-workers floor brings the pool back on the next tick).
    while True:
        try:
            lg = get_loadgen()
            if lg is not None:
                arrivals = lg.sample(tick_s)
                if pool.num_workers > 0:
                    for req in arrivals:
                        pool.submit(req)
            pool.step()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("control-plane tick failed; continuing")
        await asyncio.sleep(tick_s)


def _pool_from_env(cfg: GatewayConfig) -> PoolManager:
    """Build the pool from env for `make dev` / the container. WORKER_BACKEND=
    sim|openai|realmodel (default sim); demo mode forces sim and caps max workers."""
    backend = "sim" if cfg.demo else os.environ.get("WORKER_BACKEND", "sim")
    # Each realmodel worker loads its own model copy into memory, so keep that pool
    # tiny on a laptop (one worker, scale to at most two). sim/openai are cheap.
    n_workers = 1 if backend == "realmodel" else 2
    max_workers = min(2 if backend == "realmodel" else 8, cfg.max_workers_cap)
    # Start in continuous batching; REALMODEL_CONTINUOUS=0 starts in static (toggle live too).
    continuous = os.environ.get("REALMODEL_CONTINUOUS", "1").lower() not in ("0", "false", "no")
    return build_pool(
        backend=backend,
        n_workers=n_workers,
        max_workers=max_workers,
        base_url=os.environ.get("OPENAI_BASE_URL", "http://localhost:11434"),
        model=os.environ.get("MODEL_NAME", "qwen2.5:0.5b"),
        continuous=continuous,
    )


# Module-level app for `uvicorn inference_demo.gateway.app:app` (background on).
_cfg = GatewayConfig.from_env()
app = create_app(_pool_from_env(_cfg), run_background=True, config=_cfg)
