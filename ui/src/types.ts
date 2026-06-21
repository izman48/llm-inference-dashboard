// Mirrors the gateway's /api/snapshot shape (see pool.py PoolManager.snapshot).

export interface MetricsSnapshot {
  completed_total: number;
  in_flight: number;
  tokens_total: number;
  throughput_tok_s: number;
  ttft_p50_s: number;
  ttft_p99_s: number;
  e2e_p50_s: number;
  e2e_p99_s: number;
}

export interface WorkerView {
  worker_id: string;
  queue_depth: number;
  in_flight: number;
  tok_per_s: number;
  cached_prefixes: number;
  healthy: boolean;
}

export interface AutoscalerView {
  enabled: boolean;
  min_workers: number;
  max_workers: number;
  target_queue_depth: number;
}

export interface PoolView {
  num_workers: number;
  strategy: string;
  clock_s: number;
  autoscaler: AutoscalerView;
  workers: WorkerView[];
}

export interface RecentRow {
  req_id: string;
  worker_id: string;
  strategy: string;
  ttft_s: number;
  e2e_s: number;
  tokens: number;
}

export interface Snapshot {
  metrics: MetricsSnapshot;
  pool: PoolView;
  recent: RecentRow[];
}

export type Preset = "steady" | "burst" | "spike";
