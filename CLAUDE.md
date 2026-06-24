# Inference Demo — Project Memory

A small but real LLM inference serving system: a control plane (router + autoscaler +
live observability console) sitting on top of model workers that do continuous batching.
Built to demonstrate distributed-systems competence for an Anthropic "Senior SWE, Inference"
application. Treat it as a portfolio/interview artifact: clarity, correctness, and honest
framing matter as much as raw functionality.

## Why this exists (the problem)

Serving one LLM to many users is slow because requests queue behind each other and a single
model handles them one at a time. Real inference systems fix this with (1) **batching** —
running many requests through the model together, amortizing the expensive weight-load over
the whole batch — and (2) **multiple model replicas with intelligent routing** between them,
plus **autoscaling** to match capacity to load. This project is a toy-scale, honest
implementation of that control plane.

Thesis to optimize for: *given a fixed pool of workers and a mixed workload
(interactive + batch), intelligently route, schedule, and autoscale to maximize useful
throughput while protecting interactive tail latency — and prove every decision with
before/after observability.* The control plane is the centre of gravity, not the batching.

## What it is (the system)

- **Router** — receives each request, picks which worker handles it. Strategy is pluggable and
  switchable live (see Routing strategies below).
- **Worker** — runs a model and does continuous (in-flight) batching: admit queued requests and
  evict finished sequences each decode step. Per-sequence KV cache.
- **Autoscaler** — adds/removes workers based on queue depth / load.
- **Observability + console** — staged metrics (TTFT, queue wait, prefill/decode, p99) rendered
  live. First-class feature, not an afterthought.
- **Load generator** — synthetic traffic (Poisson arrivals; configurable concurrency; presets:
  steady / burst / spike) to drive demos and benchmarks.

## Key design: the swappable Worker backend

Everything above the worker (router, scheduler, autoscaler, metrics, UI) is backend-agnostic.
One `Worker` interface (Python `Protocol`), three implementations:

1. **SimWorker** — no real model; tunable latency/throughput profile (and a modellable
   prefix-cache hit speedup). Runs anywhere (Docker, Linux, CI). Powers the portable demo, lets
   the whole control plane be unit-tested deterministically, and can fake hundreds/thousands of
   workers to show routing/autoscaling holds at scale.
2. **OpenAIWorker** — points at any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio). Lets a
   reviewer run live against a real model on any OS. NOTE: the external server owns the decode
   loop here, so this exercises routing/autoscaling/observability but NOT our batching.
3. **RealModelWorker** — a real small model with OUR continuous batching, host-native only
   (doesn't run in Docker on macOS). Framework is a DEFERRED phase-6 choice — you do NOT need it
   to build phases 0-5: HuggingFace transformers + MPS is the recommended default (familiar,
   strong CV signal, and you own the decode loop so your batching is what's shown); MLX/mlx-lm is
   an optional Apple-native speed upgrade; or skip custom batching and demo a real model via
   Ollama through OpenAIWorker. The mode that demonstrates batching + the static-vs-continuous
   benchmark.

This one abstraction is simultaneously the demo-portability story, the "hardware-agnostic"
story (mirrors how real fleets put diverse accelerators behind one interface), and what makes
the control plane TDD-able against SimWorker.

### Architecture seam (define on commit one)

```python
class Worker(Protocol):
    def admit(self, req: Request) -> SeqId: ...
    def step(self) -> list[TokenEvent]: ...   # advance the running batch one decode step
    def in_flight(self) -> int: ...

class RoutingStrategy(Protocol):
    def choose(self, worker_states: list[WorkerState], req: Request) -> WorkerId: ...
```

Scheduler and every RoutingStrategy are pure: given state in, decision out, no model/network.
The TDD crown jewels — test exhaustively against fabricated states.

## Routing strategies (build the spread — the contrast IS the demo)

Naive ones are not filler; they are the baseline that makes the smart ones legible.

Naive baselines (demo villains):
- **random** — pick any worker. The floor.
- **round-robin** — cycle in order; ignores load. Fine under uniform traffic, breaks under
  skew (LLM output length varies ~10x). Headline villain: failure is visible on the dashboard.

Load-aware (honest defaults):
- **least-queue-depth** — fewest in-flight requests. Big jump over round-robin.
- **least-pending-tokens** — count estimated remaining *tokens* of work, not request count.
  The LLM-aware upgrade (a 2000-token request != a 10-token request).
- **power-of-two-choices** — sample 2 workers, route to the lighter. Near-optimal at O(1);
  avoids the thundering-herd that naive global-least-loaded hits at scale.

Inference-native (differentiators):
- **prefix-affinity / KV-cache-aware** — route requests sharing a prompt prefix (system prompt,
  conversation) to the same worker to reuse cached KV. Trades load-balance for cache hit-rate.
  The standout: proves LLM serving is stateful. Ties to prompt caching. (cf. GORGO.)
- **priority / SLA-class** — interactive jumps ahead; batch/research backfills spare capacity.
  Maps to the JD's prod/research/experimental workloads.
- **hardware-aware** — sim workers with different speed profiles; latency-sensitive -> fast,
  throughput -> slow. The compute-agnostic story without real heterogeneous hardware.

Frontier (name for awareness, do NOT build): prefill/decode-disaggregation-aware routing
(DistServe/Splitwise); output-length-prediction routing.

Demo arc: under one bursty, skewed load, step round-robin -> least-queue ->
least-pending-tokens -> power-of-two -> prefix-affinity, narrating p99 and cache-hit-rate.

## Two layers of batching (don't conflate)

Production fleets batch at two layers: each replica does continuous batching internally
(vLLM / our MLXWorker), and a control plane routes/load-balances across replicas. This
project's contribution is the control-plane layer; the per-replica batcher is ours (MLX) or the
external server's (vLLM/Ollama). Pointing at vLLM is not cheating — it's the real architecture.

## The control console (the deployed UI)

Not a read-only dashboard — a console the reviewer operates:
- **Backend selector** — Sim / Endpoint / MLX.
- **Endpoint config** (Endpoint mode) — model URL + model name + test/connection button.
- **Load generator** — presets (steady/burst/spike), rate + concurrency, start/stop.
- **Routing** — live strategy switcher (the strategies above).
- **Autoscaler** — on/off, min/max workers, target queue depth, current count.
- **Worker pool view** — per-worker queue depth + tok/s (the "where the load goes" view);
  shows autoscaler adding workers under pressure.
- **Observability** — throughput, TTFT p50, p99, in-flight; recent-requests log with per-request
  routing decision + TTFT.
- **Scenario buttons** — one-click "kill a worker" / "switch strategy" to create clean
  before/after moments. Demos are won here.

### Endpoint feature — reachability + security (design around this)

- Reachability: a hosted VPS CANNOT reach a reviewer's localhost model. The custom-endpoint
  field is fully useful only in LOCAL/self-hosted mode (reviewer's UI -> their control plane ->
  their localhost Ollama). On the hosted demo, custom endpoints need a public tunnel or a model
  we pre-host.
- Security: taking an arbitrary URL server-side on a public box is SSRF. So: custom-endpoint
  ENABLED in self-hosted/local mode; PUBLIC demo defaults to sim + an optional pre-hosted model.
  If custom URLs are ever allowed publicly, allowlist schemes and block private IP ranges. State
  this handling in the README (it's a senior signal).

## Run modes (how anyone connects)

1. Easiest: hosted live URL (sim backend on a VPS) — click, operate the console.
2. `make up` (`docker compose up`) — sim backend locally, any OS, zero deps.
3. `make up-ollama` — dockerized control plane + a REAL model served by host-native
   Ollama (reached via `host.docker.internal`; Docker on macOS has no GPU passthrough, so
   the model stays on the host). Shows routing/observability on a real model, not our batching.
4. Bring-your-own model (local, host-native): `WORKER_BACKEND=openai`, `OPENAI_BASE_URL`, `MODEL_NAME`.
5. Full build: real model host-native (transformers+MPS recommended, or MLX) — our continuous
   batching; recorded demo / screen-share. The only mode that shows our batcher live.

## Tech stack

- Python (control plane, scheduler, router, workers, load-gen). FastAPI gateway/API.
- Real-model worker (phase 6, host-native, lazy/optional import — NOT needed for phases 0-5):
  HuggingFace transformers + torch (MPS) recommended; MLX/mlx-lm optional. Model: a small one
  e.g. `Qwen2.5-0.5B-Instruct` (4-bit).
- Metrics: Prometheus `/metrics` + SSE/WebSocket stream to the UI.
- UI: React control console (live charts, strategy switcher, load-gen + endpoint controls).
- Docker Compose for control plane + sim/openai backends (NOT the MLX worker).
- Reverse proxy with auto-HTTPS (Caddy) for the VPS deploy.

## Engineering principles (non-negotiable)

- **TDD.** Tests first, especially scheduler and every RoutingStrategy (pure logic; cover
  deterministically against SimWorker). Slow/flaky model code stays thin behind the interface.
- **Maintainable above all.** Strict Worker / RoutingStrategy seams; small modules.
- **Depth over breadth.** Wins on the depth of the routing + autoscaling + observability spine.
  Everything else is optional polish added only once the spine is solid. Resist feature sprawl.

## Build plan (sprints — each ends in something shippable)

1. **Spine core.** `Worker` protocol + `SimWorker`; scheduler test-first; single worker.
   DELIVERABLE: static-vs-continuous benchmark + throughput/latency graph, produced against
   SimWorker FIRST (sim models "all wait for slowest" vs "evict/admit per step"), so the money
   graph exists before any real model. Re-run for real in MLX mode later to confirm sim honesty.
2. **Observability.** Prometheus metrics, staged timings (TTFT, queue wait, prefill/decode),
   live SSE stream, first React dashboard.
3. **Routing + console.** Pluggable live-switchable strategies (full spread above); multi-worker;
   the control console — strategy switcher, load-gen, worker-pool view, scenario buttons.
4. **Scalability + real model.** Autoscaler; real-model worker (transformers+MPS recommended /
   optional MLX); `OpenAIWorker`
   + endpoint config panel (local-mode-first; SSRF/reachability handling); Docker compose.
5. **Package + deploy.** VPS deploy + hosted live URL (sim-only, gated controls, hard resource
   caps, dashboard-only exposure); README with architecture diagram + recorded demo + prior-work.

## In scope / out of scope

IN: the spine (router + strategies, scheduler/batching, autoscaler, observability, console),
three backends, load generator, Docker (control plane), VPS deploy, benchmark + tuning case study.

OUT (park unless spine is rock-solid): paged attention (claim slot-based continuous batching,
non-paged — say so), structured/JSON sampling, multi-region infra, many model architectures,
GPU-kernel-level work, prefill/decode disaggregation.

## Honesty constraints (state plainly in README)

- Our batching is "continuous (in-flight) batching, non-paged" — do not imply PagedAttention.
- Hosted/VPS and OpenAI-backend modes prove routing/autoscaling/observability, NOT our batching.
  Our batching is shown only in real-model mode (transformers/MLX) + the static-vs-continuous benchmark.
- The live URL is a bonus, never the only artifact: ship hosted URL + README recording + repo.

## Prior work (cite in README background)

- Orca: iteration-level scheduling (continuous batching) + selective batching. Yu et al.,
  OSDI 2022. The idea this project implements at toy scale (~36.9x throughput vs prior systems,
  serving-infra only, no model changes).
- vLLM / PagedAttention: explicit KV-cache memory management making continuous batching
  memory-efficient. Kwon et al., SOSP 2023.
- GORGO: KV-cache-reuse-aware cross-region routing — reference for prefix-affinity routing.
- Frontier (awareness): prefill/decode disaggregation (DistServe, Splitwise), chunked prefill,
  speculative decoding (a latency axis, stacks on top of batching).

## Open decisions / notes

- Real-model framework: DEFERRED to phase 6, not needed earlier. Recommended HuggingFace
  transformers + MPS (familiar, name-recognition, you own the decode loop via `past_key_values`);
  MLX/mlx-lm optional faster Apple-native path; Ollama-via-OpenAIWorker the zero-framework fallback
  (real model, but its batching, not yours). All "own the loop" options manage a per-sequence KV
  cache + attention masking so batched sequences don't cross-attend.
- Docker->host Ollama networking: `host.docker.internal` (macOS/Windows) or host networking /
  `--add-host` on Linux. Document it.

## How this file scales (knowledge transfer)

Keep this root CLAUDE.md as the constitution. As areas get deep, lift detail into docs and
import via `@docs/<name>.md` (Claude Code supports `@path` imports, max 5 hops) or add
directory-level CLAUDE.md files. Likely future splits: `@docs/routing-strategies.md`,
`@docs/observability.md`. Use `#` in a session to append a learning here; keep ## Commands live.

## Commands

Python is managed with `uv`; the venv is pinned to 3.12 via `.python-version`.

- `make setup` — `uv sync --extra dev` (create venv + install runtime & dev deps).
- `make test` — `uv run pytest` (scheduler property tests + SimWorker + bench guard).
- `make lint` — `uv run ruff check .` + `ruff format --check .`.
- `make typecheck` — `uv run mypy` (strict on `src/`).
- `make bench` — run the static-vs-continuous benchmark; writes the money graph +
  summary to `src/inference_demo/bench/out/` (`static_vs_continuous.svg` / `.md`).
- `make bench-real` — real-model static-vs-continuous benchmark (host-native, needs
  the `realmodel` extra); writes `real_static_vs_continuous.{svg,md}` to the same dir.
- `make dev` — serve the control-plane API on `127.0.0.1:8000`
  (`uvicorn inference_demo.gateway.app:app`). Background loop steps the pool + pumps
  the load generator. Key endpoints: `POST /api/submit`, `POST /api/loadgen`,
  `POST /api/strategy`, `POST /api/autoscaler`, `POST /api/workers/kill`,
  `GET /api/snapshot`, `GET /api/stream` (SSE), `GET /metrics` (Prometheus).
- `make up` — `docker compose up --build`: full sim stack (control-plane API,
  internal-only, + Caddy serving the console) at `http://localhost:8080`. The
  backend runs in demo mode (sim-only, capped). Prod deploy adds
  `deploy/docker-compose.prod.yml` (binds 80/443, auto-HTTPS) with `SITE_ADDRESS`
  + `CONTROL_TOKEN` set. Env caps: `PUBLIC_DEMO`, `PUBLIC_MAX_WORKERS`,
  `PUBLIC_MAX_RATE`, `PUBLIC_MAX_TOKENS`, `CONTROL_TOKEN`. Caddy never proxies
  `/metrics` (internals stay private).
- `make up-ollama` — `docker compose -f docker-compose.yml -f docker-compose.ollama.yml
  up --build`: the same dockerized control plane, but the override sets `PUBLIC_DEMO=0`
  + `WORKER_BACKEND=openai` + `OPENAI_BASE_URL=http://host.docker.internal:11434` so it
  routes to a REAL model served by host-native Ollama (`ollama serve` + `ollama pull
  qwen2.5:0.5b` first; `MODEL_NAME` overrides the tag). Docker on macOS has no GPU
  passthrough, so the model must stay on the host — this exercises routing/observability
  on a real model, NOT our batching. `extra_hosts` maps `host.docker.internal` on Linux.

Backends (phase 6). `make dev` reads `WORKER_BACKEND` (default `sim`):

- `sim` — SimWorker, no model, runs anywhere (default; what CI tests).
- `openai` — `OpenAIWorker` against an OpenAI-compatible endpoint; set
  `OPENAI_BASE_URL` + `MODEL_NAME` (e.g. Ollama: `ollama run qwen2.5:0.5b`).
  Local/self-hosted only (SSRF — see Endpoint feature notes). Tested in CI via a
  mocked HTTP endpoint.
- `realmodel` — `RealModelWorker` (HF transformers + MPS, OUR continuous batching).
  Host-native only. First install the heavy deps: `uv sync --extra dev --extra
  realmodel`. On-device tests are gated: `uv run pytest -m realmodel` (downloads
  Qwen2.5-0.5B-Instruct ~1 GB on first run). Excluded from the default `make test`.

React control console (`ui/`, Vite + TS; needs Node/npm):

- `make ui-install` — `npm --prefix ui install`.
- `make ui-dev` — Vite dev server on `127.0.0.1:5273` (proxies `/api` + `/metrics`
  to `127.0.0.1:8000`). Run `make dev` (gateway) alongside it. Port 5273 dodges the
  common 5173; if 5273 is busy Vite auto-picks the next free port (see the printed URL).
- `make ui-build` — `tsc -b && vite build` (must be clean).
- `make ui-test` — Vitest component + smoke tests.

(`docker compose up` and demo scripts get filled in as those phases land.)