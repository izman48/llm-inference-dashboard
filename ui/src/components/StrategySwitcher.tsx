interface Props {
  strategies: string[];
  current: string;
  onChange: (name: string) => void;
}

export function StrategySwitcher({ strategies, current, onChange }: Props) {
  return (
    <div className="panel">
      <h3>Routing strategy</h3>
      <select
        aria-label="routing strategy"
        value={current}
        onChange={(e) => onChange(e.target.value)}
      >
        {strategies.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  );
}
