import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { sampleSnapshot } from "../testFixtures";
import { MetricCards } from "./MetricCards";

describe("MetricCards", () => {
  it("renders throughput, in-flight and percentile cards", () => {
    render(<MetricCards metrics={sampleSnapshot.metrics} />);
    expect(screen.getByText("712 tok/s")).toBeInTheDocument();
    expect(screen.getByText("In-flight")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("0.51 s")).toBeInTheDocument(); // e2e p99
  });
});
