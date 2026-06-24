import { useEffect, useState } from "react";
import * as api from "../api";
import { GLOSSARY } from "../glossary";
import type { BackendsInfo } from "../types";
import { InfoTip } from "./InfoTip";

// Live backend selector. Reflects the actually-running backend (from the snapshot)
// and switches it on the server. The real-model and OpenAI-compatible endpoint
// backends are self-hosted only: switching is disabled on the public demo (a hosted
// box must stay sim-only — taking an arbitrary endpoint URL server-side is SSRF).
const TIP: Record<string, string> = {
  sim: GLOSSARY.backendSim,
  openai: GLOSSARY.backendEndpoint,
  realmodel: GLOSSARY.backendReal,
};

interface Props {
  current: string; // the backend the server reports running (snapshot.pool.backend)
}

export function BackendSelector({ current }: Props) {
  const [info, setInfo] = useState<BackendsInfo | null>(null);
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("");

  useEffect(() => {
    api
      .getBackends()
      .then((b) => {
        setInfo(b);
        setUrl(b.endpoint.base_url);
        setModel(b.endpoint.model);
      })
      .catch(() => undefined);
  }, []);

  function choose(id: string) {
    if (id === "openai") api.setBackend("openai", url, model).catch(() => undefined);
    else api.setBackend(id).catch(() => undefined);
  }

  const switchable = info?.switchable ?? false;
  const options = info?.available ?? [];

  return (
    <div className="panel">
      <h3>Backend</h3>
      {info && !switchable && (
        <div className="muted">Locked to sim on the public demo (sim-only for safety).</div>
      )}
      {options.map((b) => {
        const disabled = !switchable || !b.available;
        const tip = b.available ? TIP[b.id] : `${TIP[b.id]} — ${b.reason}`;
        return (
          <div key={b.id}>
            <label className="row">
              <input
                type="radio"
                name="backend"
                checked={current === b.id}
                disabled={disabled}
                onChange={() => choose(b.id)}
              />
              {b.label}
              <InfoTip text={tip} label={`About the ${b.label} backend`} />
            </label>
            {b.id === "openai" && switchable && b.available && (
              <div className="endpoint-config">
                <input
                  aria-label="endpoint url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="http://host:11434"
                />
                <input
                  aria-label="endpoint model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="model name"
                />
                <button onClick={() => choose("openai")}>Use endpoint</button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
