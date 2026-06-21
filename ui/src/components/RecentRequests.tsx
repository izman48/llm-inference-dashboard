import type { RecentRow } from "../types";

interface Props {
  rows: RecentRow[];
}

export function RecentRequests({ rows }: Props) {
  return (
    <div className="panel">
      <h3>Recent requests</h3>
      <table className="recent-table">
        <thead>
          <tr>
            <th>req</th>
            <th>worker</th>
            <th>strategy</th>
            <th>TTFT</th>
            <th>E2E</th>
            <th>tok</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.req_id}>
              <td>{r.req_id}</td>
              <td>{r.worker_id}</td>
              <td>{r.strategy}</td>
              <td>{r.ttft_s.toFixed(2)}</td>
              <td>{r.e2e_s.toFixed(2)}</td>
              <td>{r.tokens}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
