import type { Snapshot } from "./types";

export const sampleSnapshot: Snapshot = {
  metrics: {
    completed_total: 42,
    in_flight: 12,
    tokens_total: 1337,
    throughput_tok_s: 712.4,
    offered_load_req_s: 18.2,
    ttft_p50_s: 0.03,
    ttft_p99_s: 0.08,
    e2e_p50_s: 0.25,
    e2e_p99_s: 0.51,
  },
  pool: {
    num_workers: 2,
    strategy: "least-pending-tokens",
    backend: "sim",
    continuous: true,
    endpoint: { base_url: "http://localhost:11434", model: "qwen2.5:0.5b" },
    clock_s: 12.3,
    autoscaler: {
      enabled: true,
      min_workers: 1,
      max_workers: 8,
      target_queue_depth: 4.0,
    },
    workers: [
      { worker_id: "w0", queue_depth: 5, in_flight: 8, tok_per_s: 100, cached_prefixes: 2, healthy: true },
      { worker_id: "w1", queue_depth: 1, in_flight: 4, tok_per_s: 100, cached_prefixes: 0, healthy: true },
    ],
  },
  recent: [
    { req_id: "u0", worker_id: "w0", strategy: "least-pending-tokens", ttft_s: 0.03, e2e_s: 0.25, tokens: 20 },
    { req_id: "u1", worker_id: "w1", strategy: "least-pending-tokens", ttft_s: 0.04, e2e_s: 0.31, tokens: 14 },
  ],
};
