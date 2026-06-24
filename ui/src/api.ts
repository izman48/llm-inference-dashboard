import type { AutoscalerView, BackendsInfo, Preset, Snapshot } from "./types";

// Optional control token (baked at build time) — sent on mutating requests so a
// gated public demo stays fully clickable. Not a real secret (it ships in the
// bundle); the actual protection is the server-side hard caps.
const CONTROL_TOKEN = import.meta.env.VITE_CONTROL_TOKEN;

function postHeaders(): Record<string, string> {
  const h: Record<string, string> = { "content-type": "application/json" };
  if (CONTROL_TOKEN) h["x-control-token"] = CONTROL_TOKEN;
  return h;
}

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: postHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return (await res.json()) as T;
}

export async function getSnapshot(): Promise<Snapshot> {
  const res = await fetch("/api/snapshot");
  if (!res.ok) throw new Error(`/api/snapshot -> ${res.status}`);
  return (await res.json()) as Snapshot;
}

export async function getStrategies(): Promise<string[]> {
  const res = await fetch("/api/strategies");
  if (!res.ok) throw new Error(`/api/strategies -> ${res.status}`);
  return ((await res.json()) as { strategies: string[] }).strategies;
}

export interface SubmitBody {
  prompt_tokens: number;
  max_tokens: number;
  priority: "interactive" | "batch";
  prefix_key?: string | null;
}

export const submit = (b: SubmitBody) =>
  postJSON<{ req_id: string; worker_id: string }>("/api/submit", b);

export const setStrategy = (name: string) =>
  postJSON<{ strategy: string }>("/api/strategy", { name });

export const setAutoscaler = (b: Partial<AutoscalerView>) =>
  postJSON<AutoscalerView>("/api/autoscaler", b);

export const startLoadgen = (preset: Preset, base_rate: number) =>
  postJSON<unknown>("/api/loadgen", { preset, base_rate });

export const stopLoadgen = () => postJSON<unknown>("/api/loadgen/stop", {});

export const killWorker = () =>
  postJSON<{ killed: string | null }>("/api/workers/kill", {});

export const resetPool = () =>
  postJSON<{ reset: boolean; num_workers: number }>("/api/reset", {});

export async function getBackends(): Promise<BackendsInfo> {
  const res = await fetch("/api/backends");
  if (!res.ok) throw new Error(`/api/backends -> ${res.status}`);
  return (await res.json()) as BackendsInfo;
}

export const setBackend = (backend: string, base_url?: string, model?: string) =>
  postJSON<{ backend: string }>("/api/backend", { backend, base_url, model });

export const setBatching = (continuous: boolean) =>
  postJSON<{ continuous: boolean; applies: boolean }>("/api/batching", { continuous });

/** Subscribe to the live SSE snapshot stream. Returns an unsubscribe fn. */
export function subscribe(onSnapshot: (s: Snapshot) => void): () => void {
  const es = new EventSource("/api/stream");
  es.onmessage = (ev) => {
    try {
      onSnapshot(JSON.parse(ev.data) as Snapshot);
    } catch {
      /* ignore malformed frame */
    }
  };
  return () => es.close();
}
