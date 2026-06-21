"""Load generator: Poisson arrivals with steady / burst / spike presets. The
plan is pure (seedable) so demos and tests are reproducible; LoadGenerator is the
live counterpart used by the gateway loop.
"""

from __future__ import annotations

from inference_demo.loadgen import LoadGenerator, LoadPreset, plan_arrivals, rate_at


def test_steady_plan_has_roughly_expected_count_and_bounds() -> None:
    plan = plan_arrivals(preset=LoadPreset.STEADY, base_rate=20.0, duration_s=10.0, seed=1)
    # ~ rate * duration = 200 arrivals; allow generous Poisson slack
    assert 150 <= len(plan) <= 250
    assert all(0.0 <= p.t_s <= 10.0 for p in plan)
    assert plan == sorted(plan, key=lambda p: p.t_s)  # time-ordered


def test_plan_is_deterministic_under_seed() -> None:
    a = plan_arrivals(preset=LoadPreset.BURST, base_rate=10.0, duration_s=5.0, seed=7)
    b = plan_arrivals(preset=LoadPreset.BURST, base_rate=10.0, duration_s=5.0, seed=7)
    assert [(p.t_s, p.req.id) for p in a] == [(p.t_s, p.req.id) for p in b]


def test_spike_concentrates_arrivals_in_the_spike_window() -> None:
    d = 10.0
    plan = plan_arrivals(preset=LoadPreset.SPIKE, base_rate=20.0, duration_s=d, seed=3)
    in_spike = sum(1 for p in plan if 0.4 * d <= p.t_s <= 0.6 * d)  # 20% of the timeline
    outside = len(plan) - in_spike
    # the spike window (20% of time) should hold a disproportionate share
    assert in_spike > outside * 0.5


def test_rate_at_spike_is_higher_inside_the_window() -> None:
    base = 10.0
    assert rate_at(LoadPreset.SPIKE, base, t_s=5.0, duration_s=10.0) > rate_at(
        LoadPreset.SPIKE, base, t_s=0.0, duration_s=10.0
    )
    assert rate_at(LoadPreset.STEADY, base, t_s=5.0, duration_s=10.0) == base


def test_live_generator_emits_roughly_rate_times_duration() -> None:
    gen = LoadGenerator(preset=LoadPreset.STEADY, base_rate=50.0, seed=2)
    total = 0
    for _ in range(100):  # 100 ticks of 0.1s = 10s -> ~500 requests
        total += len(gen.sample(0.1))
    assert 350 <= total <= 650
