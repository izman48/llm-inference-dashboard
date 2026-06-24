import type { AutoscalerView } from "../types";
import { GLOSSARY } from "../glossary";
import { InfoTip } from "./InfoTip";

interface Props {
  autoscaler: AutoscalerView;
  currentWorkers: number;
  backend: string;
  onChange: (patch: Partial<AutoscalerView>) => void;
}

export function AutoscalerPanel({ autoscaler, currentWorkers, backend, onChange }: Props) {
  return (
    <div className="panel">
      <h3>
        Autoscaler
        <InfoTip text={GLOSSARY.autoscaler} label="What is the autoscaler?" />
      </h3>
      {backend === "realmodel" && (
        <div className="warn">
          ⚠ Each real-model worker loads its own copy of the model into memory. Max is capped
          server-side (default 4) so a high value can't exhaust your RAM.
        </div>
      )}
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
        <InfoTip text={GLOSSARY.targetQueue} label="What is target queue depth?" />
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
