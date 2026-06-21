import type { AutoscalerView, Preset, Snapshot } from "./types";

const JSON_HEADERS = { "content-type": "application/json" };

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: JSON_HEADERS,
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
