// Backend selector. Sim is active; Endpoint (OpenAI-compatible) and MLX are
// present but disabled here — they land in phase 6 (and Endpoint is local-mode-only
// for SSRF/reachability reasons; see CLAUDE.md).
const BACKENDS = [
  { id: "sim", label: "Sim", enabled: true },
  { id: "endpoint", label: "Endpoint (phase 6)", enabled: false },
  { id: "mlx", label: "MLX (phase 6)", enabled: false },
];

export function BackendSelector() {
  return (
    <div className="panel">
      <h3>Backend</h3>
      {BACKENDS.map((b) => (
        <label key={b.id} className="row">
          <input type="radio" name="backend" defaultChecked={b.id === "sim"} disabled={!b.enabled} />
          {b.label}
        </label>
      ))}
    </div>
  );
}
