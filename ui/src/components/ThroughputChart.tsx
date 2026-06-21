import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Props {
  history: number[];
}

export function ThroughputChart({ history }: Props) {
  const data = history.map((v, i) => ({ t: i, tps: v }));
  return (
    <div className="panel chart-panel">
      <h3>Throughput (tok/s)</h3>
      <div style={{ width: "100%", height: 160 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <XAxis dataKey="t" hide />
            <YAxis width={44} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="tps"
              stroke="#2ca02c"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
