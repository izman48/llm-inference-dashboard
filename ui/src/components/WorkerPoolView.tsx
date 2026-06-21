import type { WorkerView } from "../types";

interface Props {
  workers: WorkerView[];
}

// The "where the load goes" view: per-worker queue depth + in-flight, with a bar
// scaled to the busiest worker so skew is visible at a glance.
export function WorkerPoolView({ workers }: Props) {
  const peak = Math.max(1, ...workers.map((w) => w.queue_depth + w.in_flight));
  return (
    <div className="panel">
      <h3>Worker pool ({workers.length})</h3>
      <table className="worker-table">
        <thead>
          <tr>
            <th>worker</th>
            <th>queue</th>
            <th>in-flight</th>
            <th>load</th>
            <th>cached</th>
          </tr>
        </thead>
        <tbody>
          {workers.map((w) => {
            const load = w.queue_depth + w.in_flight;
            return (
              <tr key={w.worker_id} className={w.healthy ? "" : "unhealthy"}>
                <td>{w.worker_id}</td>
                <td>{w.queue_depth}</td>
                <td>{w.in_flight}</td>
                <td>
                  <div className="bar-track" title={`${load}`}>
                    <div className="bar-fill" style={{ width: `${(load / peak) * 100}%` }} />
                  </div>
                </td>
                <td>{w.cached_prefixes}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
