import type { MetricsSnapshot } from "../types";

interface Props {
  metrics: MetricsSnapshot;
}

interface Card {
  label: string;
  value: string;
}

export function MetricCards({ metrics }: Props) {
  const cards: Card[] = [
    { label: "Throughput", value: `${metrics.throughput_tok_s.toFixed(0)} tok/s` },
    { label: "In-flight", value: `${metrics.in_flight}` },
    { label: "Completed", value: `${metrics.completed_total}` },
    { label: "TTFT p50", value: `${metrics.ttft_p50_s.toFixed(2)} s` },
    { label: "TTFT p99", value: `${metrics.ttft_p99_s.toFixed(2)} s` },
    { label: "E2E p99", value: `${metrics.e2e_p99_s.toFixed(2)} s` },
  ];
  return (
    <div className="cards">
      {cards.map((c) => (
        <div className="card" key={c.label}>
          <div className="card-label">{c.label}</div>
          <div className="card-value">{c.value}</div>
        </div>
      ))}
    </div>
  );
}
