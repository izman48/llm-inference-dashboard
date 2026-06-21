import type { AutoscalerView } from "../types";

interface Props {
  autoscaler: AutoscalerView;
  currentWorkers: number;
  onChange: (patch: Partial<AutoscalerView>) => void;
}

export function AutoscalerPanel({ autoscaler, currentWorkers, onChange }: Props) {
  return (
    <div className="panel">
      <h3>Autoscaler</h3>
      <label className="row">
        <input
          type="checkbox"
          checked={autoscaler.enabled}
          onChange={(e) => onChange({ enabled: e.target.checked })}
        />
        enabled
      </label>
      <label className="row">
        min
        <input
          type="number"
          min={1}
          value={autoscaler.min_workers}
          onChange={(e) => onChange({ min_workers: Number(e.target.value) })}
        />
      </label>
      <label className="row">
        max
        <input
          type="number"
          min={1}
          value={autoscaler.max_workers}
          onChange={(e) => onChange({ max_workers: Number(e.target.value) })}
        />
      </label>
      <label className="row">
        target queue
        <input
          type="number"
          min={1}
          step={0.5}
          value={autoscaler.target_queue_depth}
          onChange={(e) => onChange({ target_queue_depth: Number(e.target.value) })}
        />
      </label>
      <div className="muted">current: {currentWorkers} workers</div>
    </div>
  );
}
