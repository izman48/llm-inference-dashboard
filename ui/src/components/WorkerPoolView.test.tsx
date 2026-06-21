import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { sampleSnapshot } from "../testFixtures";
import { WorkerPoolView } from "./WorkerPoolView";

describe("WorkerPoolView", () => {
  it("renders a row per worker with the pool size in the heading", () => {
    render(<WorkerPoolView workers={sampleSnapshot.pool.workers} />);
    expect(screen.getByText("Worker pool (2)")).toBeInTheDocument();
    expect(screen.getByText("w0")).toBeInTheDocument();
    expect(screen.getByText("w1")).toBeInTheDocument();
  });
});
