import * as api from "../api";
import { GLOSSARY } from "../glossary";
import { InfoTip } from "./InfoTip";

interface Props {
  backend: string;
  continuous: boolean;
}

// Live continuous-vs-static batching switch for the real-model worker — the only
// backend whose decode loop is ours. Hidden for sim/openai (their batching isn't ours).
export function BatchingToggle({ backend, continuous }: Props) {
  if (backend !== "realmodel") return null;
  return (
    <div className="panel">
      <h3>
        Batching
        <InfoTip text={GLOSSARY.batchingMode} label="Continuous vs static batching" />
      </h3>
      <label className="row">
        <input
          type="checkbox"
          checked={continuous}
          onChange={(e) => api.setBatching(e.target.checked).catch(() => undefined)}
        />
        continuous
      </label>
      <div className="muted">
        {continuous
          ? "admit / evict every step (ours)"
          : "static: drain the batch before admitting the next"}
      </div>
    </div>
  );
}
