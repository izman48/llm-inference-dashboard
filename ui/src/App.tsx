import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import { AutoscalerPanel } from "./components/AutoscalerPanel";
import { BackendSelector } from "./components/BackendSelector";
import { LoadGenControls } from "./components/LoadGenControls";
import { MetricCards } from "./components/MetricCards";
import { RecentRequests } from "./components/RecentRequests";
import { ScenarioButtons } from "./components/ScenarioButtons";
import { StrategySwitcher } from "./components/StrategySwitcher";
import { ThroughputChart } from "./components/ThroughputChart";
import { WorkerPoolView } from "./components/WorkerPoolView";
import type { AutoscalerView, Snapshot } from "./types";

const HISTORY = 60;

export function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [history, setHistory] = useState<number[]>([]);
  const connected = useRef(false);

  useEffect(() => {
    api.getStrategies().then(setStrategies).catch(() => undefined);
    const unsubscribe = api.subscribe((s) => {
      connected.current = true;
      setSnapshot(s);
      setHistory((h) => [...h, s.metrics.throughput_tok_s].slice(-HISTORY));
    });
    return unsubscribe;
  }, []);

  function onStrategy(name: string) {
    api.setStrategy(name).catch(() => undefined);
    setSnapshot((s) => (s ? { ...s, pool: { ...s.pool, strategy: name } } : s));
  }

  function onAutoscaler(patch: Partial<AutoscalerView>) {
    api.setAutoscaler(patch).catch(() => undefined);
    setSnapshot((s) =>
      s ? { ...s, pool: { ...s.pool, autoscaler: { ...s.pool.autoscaler, ...patch } } } : s,
    );
  }

  if (!snapshot) {
    return <div className="connecting">Connecting to control plane…</div>;
  }

  const { metrics, pool, recent } = snapshot;
  return (
    <div className="app">
      <header className="topbar">
        <h1>LLM Inference Control Plane</h1>
        <span className="badge">strategy: {pool.strategy}</span>
        <span className="badge">t = {pool.clock_s.toFixed(1)}s</span>
        <span className="badge">{pool.num_workers} workers</span>
      </header>

      <MetricCards metrics={metrics} />

      <div className="grid">
        <div className="col-main">
          <ThroughputChart history={history} />
          <WorkerPoolView workers={pool.workers} />
          <RecentRequests rows={recent} />
        </div>
        <aside className="col-side">
          <BackendSelector />
          <StrategySwitcher
            strategies={strategies}
            current={pool.strategy}
            onChange={onStrategy}
          />
          <LoadGenControls
            onStart={(preset, rate) => api.startLoadgen(preset, rate).catch(() => undefined)}
            onStop={() => api.stopLoadgen().catch(() => undefined)}
          />
          <AutoscalerPanel
            autoscaler={pool.autoscaler}
            currentWorkers={pool.num_workers}
            onChange={onAutoscaler}
          />
          <ScenarioButtons
            onKillWorker={() => api.killWorker().catch(() => undefined)}
            onSpike={() => api.startLoadgen("spike", 80).catch(() => undefined)}
          />
        </aside>
      </div>
    </div>
  );
}
