import { useState } from "react";
import type { Preset } from "../types";

interface Props {
  onStart: (preset: Preset, rate: number) => void;
  onStop: () => void;
}

const PRESETS: Preset[] = ["steady", "burst", "spike"];

export function LoadGenControls({ onStart, onStop }: Props) {
  const [preset, setPreset] = useState<Preset>("steady");
  const [rate, setRate] = useState(20);
  return (
    <div className="panel">
      <h3>Load generator</h3>
      <label className="row">
        preset
        <select
          aria-label="load preset"
          value={preset}
          onChange={(e) => setPreset(e.target.value as Preset)}
        >
          {PRESETS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <label className="row">
        rate (req/s)
        <input
          type="number"
          min={1}
          value={rate}
          onChange={(e) => setRate(Number(e.target.value))}
        />
      </label>
      <div className="row">
        <button onClick={() => onStart(preset, rate)}>Start</button>
        <button onClick={onStop}>Stop</button>
      </div>
    </div>
  );
}
