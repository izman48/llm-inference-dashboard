"""Observability — first-class, not an afterthought.

Records each request's lifecycle (submit -> route -> first token -> final token)
and derives staged timings (TTFT, end-to-end), throughput, and p50/p99 over a
recent window. Also exposes a Prometheus text exposition for ``/metrics``.

Timestamps are supplied by the caller (the PoolManager's sim clock), so this
module stays pure aggregation with no notion of wall-clock time.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)

from inference_demo.stats import percentile
from inference_demo.types import WorkerId

PROMETHEUS_CONTENT_TYPE = CONTENT_TYPE_LATEST


@dataclass
class _Open:
    req_id: str
    worker_id: str
    strategy: str
    arrival_ts: float
    first_token_ts: float | None = None
    tokens: int = 0


@dataclass(frozen=True)
class CompletedRequest:
    req_id: str
    worker_id: str
    strategy: str
    ttft_s: float
    e2e_s: float
    tokens: int
    finish_ts: float


@dataclass(frozen=True)
class MetricsSnapshot:
    completed_total: int
    in_flight: int
    tokens_total: int
    throughput_tok_s: float
    ttft_p50_s: float
    ttft_p99_s: float
    e2e_p50_s: float
    e2e_p99_s: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "completed_total": self.completed_total,
            "in_flight": self.in_flight,
            "tokens_total": self.tokens_total,
            "throughput_tok_s": round(self.throughput_tok_s, 2),
            "ttft_p50_s": round(self.ttft_p50_s, 3),
            "ttft_p99_s": round(self.ttft_p99_s, 3),
            "e2e_p50_s": round(self.e2e_p50_s, 3),
            "e2e_p99_s": round(self.e2e_p99_s, 3),
        }


class Metrics:
    def __init__(self, window: int = 200) -> None:
        self._open: dict[str, _Open] = {}
        self._recent: deque[CompletedRequest] = deque(maxlen=window)
        self._completed_total = 0
        self._tokens_total = 0
        self._in_flight = 0

        self._registry = CollectorRegistry()
        self._c_requests = Counter(
            "inference_requests_total", "Completed requests", registry=self._registry
        )
        self._c_tokens = Counter(
            "inference_tokens_total", "Output tokens generated", registry=self._registry
        )
        self._g_in_flight = Gauge(
            "inference_in_flight", "Sequences currently running", registry=self._registry
        )

    # ---- lifecycle ----------------------------------------------------------

    def on_submit(self, req_id: str, arrival_ts: float) -> None:
        self._open[req_id] = _Open(req_id=req_id, worker_id="", strategy="", arrival_ts=arrival_ts)

    def on_route(self, req_id: str, worker_id: WorkerId, strategy: str) -> None:
        rec = self._open.get(req_id)
        if rec is not None:
            rec.worker_id = str(worker_id)
            rec.strategy = strategy

    def on_token(self, req_id: str, ts: float, is_final: bool, n_tokens: int = 1) -> None:
        rec = self._open.get(req_id)
        if rec is None:
            return
        if rec.first_token_ts is None:
            rec.first_token_ts = ts
        rec.tokens += n_tokens
        self._tokens_total += n_tokens
        self._c_tokens.inc(n_tokens)
        if is_final:
            self._complete(rec, ts)

    def _complete(self, rec: _Open, finish_ts: float) -> None:
        first = rec.first_token_ts if rec.first_token_ts is not None else finish_ts
        self._recent.append(
            CompletedRequest(
                req_id=rec.req_id,
                worker_id=rec.worker_id,
                strategy=rec.strategy,
                ttft_s=first - rec.arrival_ts,
                e2e_s=finish_ts - rec.arrival_ts,
                tokens=rec.tokens,
                finish_ts=finish_ts,
            )
        )
        self._completed_total += 1
        self._c_requests.inc()
        self._open.pop(rec.req_id, None)

    def set_in_flight(self, n: int) -> None:
        self._in_flight = n
        self._g_in_flight.set(n)

    # ---- reads --------------------------------------------------------------

    def snapshot(self) -> MetricsSnapshot:
        ttfts = [r.ttft_s for r in self._recent]
        e2es = [r.e2e_s for r in self._recent]
        return MetricsSnapshot(
            completed_total=self._completed_total,
            in_flight=self._in_flight,
            tokens_total=self._tokens_total,
            throughput_tok_s=self._throughput(),
            ttft_p50_s=percentile(ttfts, 50),
            ttft_p99_s=percentile(ttfts, 99),
            e2e_p50_s=percentile(e2es, 50),
            e2e_p99_s=percentile(e2es, 99),
        )

    def _throughput(self) -> float:
        """Output tokens/sec across the recent window's completion span."""
        if len(self._recent) < 2:
            return 0.0
        span = self._recent[-1].finish_ts - self._recent[0].finish_ts
        if span <= 0:
            return 0.0
        return sum(r.tokens for r in self._recent) / span

    def recent_requests(self, k: int) -> list[dict[str, object]]:
        rows = list(self._recent)[-k:]
        return [
            {
                "req_id": r.req_id,
                "worker_id": r.worker_id,
                "strategy": r.strategy,
                "ttft_s": round(r.ttft_s, 3),
                "e2e_s": round(r.e2e_s, 3),
                "tokens": r.tokens,
            }
            for r in reversed(rows)  # newest first
        ]

    def prometheus(self) -> bytes:
        return generate_latest(self._registry)
