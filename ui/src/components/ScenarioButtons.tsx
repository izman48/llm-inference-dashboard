interface Props {
  onKillWorker: () => void;
  onSpike: () => void;
}

// One-click moments that create clean before/after stories on the dashboard.
export function ScenarioButtons({ onKillWorker, onSpike }: Props) {
  return (
    <div className="panel">
      <h3>Scenarios</h3>
      <div className="row">
        <button onClick={onKillWorker}>Kill a worker</button>
        <button onClick={onSpike}>Traffic spike</button>
      </div>
    </div>
  );
}
