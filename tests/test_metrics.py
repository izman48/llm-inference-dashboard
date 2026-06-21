"""Metrics records the per-request lifecycle and derives staged timings (TTFT,
end-to-end), throughput, and percentiles — pure aggregation, plus a Prometheus
text exposition. Tested without any worker in the loop.
"""

from __future__ import annotations

from inference_demo.metrics import Metrics
from inference_demo.stats import percentile
from inference_demo.types import WorkerId


def test_percentile_nearest_rank() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([10.0], 99) == 10.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 100) == 4.0


def _one_request(
    m: Metrics, rid: str, *, arrival: float, first: float, final: float, n: int
) -> None:
    m.on_submit(rid, arrival_ts=arrival)
    m.on_route(rid, WorkerId("w0"), "least-pending-tokens")
    for i in range(n):
        ts = first + (final - first) * (i / max(1, n - 1))
        m.on_token(rid, ts=ts, is_final=(i == n - 1))


def test_records_ttft_and_e2e_and_counts() -> None:
    m = Metrics()
    _one_request(m, "r1", arrival=0.0, first=0.2, final=1.0, n=5)
    snap = m.snapshot()
    assert snap.completed_total == 1
    assert snap.tokens_total == 5
    assert round(snap.ttft_p50_s, 3) == 0.2  # arrival -> first token
    assert round(snap.e2e_p50_s, 3) == 1.0  # arrival -> final token


def test_in_flight_gauge_and_throughput_positive() -> None:
    m = Metrics()
    _one_request(m, "r1", arrival=0.0, first=0.1, final=0.5, n=10)
    _one_request(m, "r2", arrival=0.1, first=0.2, final=0.6, n=10)
    m.set_in_flight(3)
    snap = m.snapshot()
    assert snap.in_flight == 3
    assert snap.completed_total == 2
    assert snap.throughput_tok_s > 0.0


def test_recent_requests_log_carries_routing_decision() -> None:
    m = Metrics()
    _one_request(m, "r1", arrival=0.0, first=0.2, final=1.0, n=3)
    recent = m.recent_requests(10)
    assert len(recent) == 1
    row = recent[0]
    assert row["req_id"] == "r1"
    assert row["worker_id"] == "w0"
    assert row["strategy"] == "least-pending-tokens"
    assert row["tokens"] == 3
    assert row["ttft_s"] > 0


def test_prometheus_exposition_has_metric_names() -> None:
    m = Metrics()
    _one_request(m, "r1", arrival=0.0, first=0.2, final=1.0, n=4)
    m.set_in_flight(2)
    text = m.prometheus().decode()
    assert "inference_requests_total" in text
    assert "inference_tokens_total" in text
    assert "inference_in_flight" in text
