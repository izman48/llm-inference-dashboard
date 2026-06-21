import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

// A hoisted fixture so the vi.mock factory can reference it.
const { sample } = vi.hoisted(() => {
  return {
    sample: {
      metrics: {
        completed_total: 42,
        in_flight: 12,
        tokens_total: 1337,
        throughput_tok_s: 712.4,
        ttft_p50_s: 0.03,
        ttft_p99_s: 0.08,
        e2e_p50_s: 0.25,
        e2e_p99_s: 0.51,
      },
      pool: {
        num_workers: 2,
        strategy: "least-pending-tokens",
        clock_s: 12.3,
        autoscaler: { enabled: true, min_workers: 1, max_workers: 8, target_queue_depth: 4 },
        workers: [
          { worker_id: "w0", queue_depth: 5, in_flight: 8, tok_per_s: 100, cached_prefixes: 2, healthy: true },
        ],
      },
      recent: [],
    },
  };
});

vi.mock("./api", () => ({
  getStrategies: vi.fn().mockResolvedValue(["least-pending-tokens", "round-robin"]),
  subscribe: vi.fn((cb: (s: unknown) => void) => {
    cb(sample);
    return () => undefined;
  }),
  setStrategy: vi.fn().mockResolvedValue({}),
  setAutoscaler: vi.fn().mockResolvedValue({}),
  startLoadgen: vi.fn().mockResolvedValue({}),
  stopLoadgen: vi.fn().mockResolvedValue({}),
  killWorker: vi.fn().mockResolvedValue({ killed: "w0" }),
}));

import { App } from "./App";
import * as api from "./api";

describe("App (smoke)", () => {
  it("renders live metrics from the SSE feed and wires the kill-worker scenario", async () => {
    render(<App />);
    // came from the mocked subscribe() snapshot
    expect(await screen.findByText("712 tok/s")).toBeInTheDocument();
    expect(screen.getByText(/strategy: least-pending-tokens/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Kill a worker"));
    expect(api.killWorker).toHaveBeenCalled();
  });
});
