// Plain-English definitions for the dashboard's jargon, surfaced via <InfoTip>.
// Single source of truth so the wording is easy to tune in one place.
export const GLOSSARY = {
  // --- metric cards ---
  throughput:
    "Output tokens per second across all workers, averaged over the last 5 seconds " +
    "(tokens completed in the last 5s ÷ 5). Because it's a 5-second moving average it " +
    "ramps down to 0 a few seconds after traffic stops — it reflects recent work, not " +
    "only what's running this instant.",
  inFlight:
    "Requests being decoded across all workers right now. Drops to 0 immediately when " +
    "work stops — unlike throughput, which is a rolling average and lags by a few seconds.",
  completed: "Total requests finished since the server started.",
  ttft:
    "Time To First Token — how long a request waits (queue + prefill) before it streams " +
    "its first output token. The delay a user actually feels before text starts appearing.",
  ttftP50:
    "Median TTFT: half of requests start streaming faster than this, half slower. The " +
    "typical experience.",
  ttftP99:
    "99th-percentile TTFT: only 1 request in 100 is slower than this. The tail latency — " +
    "what your unluckiest users see, and what naive routing blows up under skew.",
  e2e: "End-to-end latency: from arrival to the final token — the whole request.",
  e2eP99:
    "99th-percentile end-to-end latency: 1 request in 100 takes longer than this to fully " +
    "complete.",

  // --- charts ---
  throughputChart:
    "Output tokens/sec over time, a smoothed (exponential) moving average. The gentle ramp " +
    "to 0 after you stop traffic is the average decaying — not a bug; it mirrors what a " +
    "Prometheus rate() graph does.",
  offeredLoad:
    "Requests per second arriving from the load generator, smoothed — the demand you're " +
    "placing on the system. Compare it against throughput and queue depth to see whether the " +
    "pool is keeping up.",
  offeredLoadChart:
    "Offered load over time (req/s, smoothed): the demand the load generator is creating. " +
    "Watch it against throughput — when load outruns capacity, queues and TTFT climb until " +
    "the autoscaler adds workers.",

  // --- backends ---
  backendSim:
    "Sim: a simulated worker, no real model. Tunable latency/throughput so the whole " +
    "control plane (routing, autoscaling, batching, metrics) runs anywhere and is fully " +
    "testable. This is what the hosted demo uses.",
  backendEndpoint:
    "Endpoint: routes to any OpenAI-compatible server you run (Ollama, vLLM, LM Studio). " +
    "Exercises real routing + observability against a real model — but that external server " +
    "owns the batching, not us. Self-hosted only (a public box can't reach your localhost, " +
    "and taking arbitrary URLs server-side is an SSRF risk).",
  backendReal:
    "Real model: a small real model (e.g. Qwen2.5-0.5B) running OUR continuous batching — " +
    "we own the decode loop and the per-sequence KV cache. Host-native only (needs GPU/MPS; " +
    "doesn't run in the demo container).",

  // --- batching mode (real model) ---
  batchingMode:
    "Continuous batching admits and evicts sequences every decode step — a finished sequence " +
    "frees its slot immediately and a waiting one joins the running batch mid-flight (the " +
    "project's core technique). Static batching admits a whole batch and drains it before " +
    "starting the next, so the batch runs at the pace of its slowest sequence and the GPU idles " +
    "on the stragglers. Flip this on a real model under load to watch throughput drop and tail " +
    "latency climb — the static-vs-continuous story, live.",

  // --- routing ---
  strategy:
    "How the router picks which worker handles each request. Switch it live and watch p99 " +
    "and load balance move. Naive strategies (random, round-robin) ignore load; smarter ones " +
    "balance by queue depth or pending tokens, or reuse cached prompt prefixes.",

  // --- worker pool columns ---
  workerQueue: "Requests waiting at this worker, not yet started decoding.",
  workerInFlight: "Requests this worker is actively decoding right now.",
  workerLoad:
    "queue + in-flight, drawn as a bar scaled to the busiest worker — so routing skew is " +
    "visible at a glance.",
  workerCached:
    "Distinct prompt prefixes this worker has cached. Prefix-aware routing sends matching " +
    "prompts here to reuse the cached KV and skip re-prefill.",

  // --- load generator ---
  loadPreset:
    "Traffic shape: steady = constant Poisson arrivals; burst = on/off bursts; spike = a " +
    "sudden surge then drop. Used to create clean before/after moments.",
  loadRate: "Average requests per second the generator submits.",

  // --- autoscaler ---
  autoscaler:
    "Adds/removes workers automatically based on load, keeping the average queue near your " +
    "target.",
  targetQueue:
    "The per-worker queue depth the autoscaler aims to hold. Sustained above it → scale up; " +
    "comfortably below → scale down.",
} as const;
