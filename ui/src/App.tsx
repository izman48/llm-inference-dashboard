import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import { AutoscalerPanel } from "./components/AutoscalerPanel";
import { BackendSelector } from "./components/BackendSelector";
import { LoadGenControls } from "./components/LoadGenControls";
import { MetricCards } from "./components/MetricCards";
import { RecentRequests } from "./components/RecentRequests";
import { ScenarioButtons } from "./components/ScenarioButtons";
import { StrategySwitcher } from "./components/StrategySwitcher";
import { TimeSeriesChart } from "./components/TimeSeriesChart";
import { WorkerPoolView } from "./components/WorkerPoolView";
import { GLOSSARY } from "./glossary";
import type { AutoscalerView, Snapshot } from "./types";

const HISTORY = 60;

export function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [history, setHistory] = useState<number[]>([]);
  const [loadHistory, setLoadHistory] = useState<number[]>([]);
  const connected = useRef(false);

  useEffect(() => {
    api.getStrategies().then(setStrategies).catch(() => undefined);
    const unsubscribe = api.subscribe((s) => {
      connected.current = true;
      setSnapshot(s);
      setHistory((h) => [...h, s.metrics.throughput_tok_s].slice(-HISTORY));
      setLoadHistory((h) => [...h, s.metrics.offered_load_req_s].slice(-HISTORY));
    });
    return unsubscribe;
  }, []);

  function onReset() {
    api.resetPool().catch(() => undefined);
    setHistory([]);
    setLoadHistory([]);
  }

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
        <button className="reset-btn" onClick={onReset} title="Stop load and restore the starting pool + cleared metrics">
          Reset
        </button>
      </header>

      <MetricCards metrics={metrics} />

      <div className="grid">
        <div className="col-main">
          <TimeSeriesChart
            title="Throughput (tok/s)"
            history={history}
            color="#2ca02c"
            tip={GLOSSARY.throughputChart}
          />
          <TimeSeriesChart
            title="Offered load (req/s)"
            history={loadHistory}
            color="#e6a817"
            tip={GLOSSARY.offeredLoadChart}
          />
          <WorkerPoolView workers={pool.workers} />
          <RecentRequests rows={recent} />
        </div>
        <aside className="col-side">
          <BackendSelector current={pool.backend} />
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
            backend={pool.backend}
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
