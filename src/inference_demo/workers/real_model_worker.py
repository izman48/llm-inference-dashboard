"""RealModelWorker — a real small model with OUR continuous batching.

This is the backend that actually showcases the project's batching claim: we own
the decode loop (no ``model.generate``), keep a persistent batched KV cache, and
interleave prefill and decode steps (vLLM-style) so running sequences only ever
decode incrementally — admitting a new sequence prefills *it alone* and merges
its KV cache into the running batch (no re-prefill of existing sequences). We
admit/evict every step (continuous, non-paged). Greedy decode for determinism.

A ``continuous=False`` mode reproduces static batching (admit a whole batch, drain
it before admitting the next) for the static-vs-continuous benchmark.

Host-native only (MPS isn't available in Docker on macOS). Heavy deps (torch,
transformers) are imported lazily so the rest of the package — and CI — never
needs them. Default model: Qwen2.5-0.5B-Instruct. We do NOT implement paged
attention (the KV cache is contiguous + left-padded, not paged).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from inference_demo.types import Request, SeqId, TokenEvent, WorkerId, WorkerState

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


@dataclass
class _Seq:
    seq_id: SeqId
    token_ids: list[int]  # full real sequence so far (prompt + generated)
    max_new: int
    generated: int = 0
    finished: bool = False


class RealModelWorker:
    def __init__(
        self,
        worker_id: WorkerId,
        *,
        model_name: str = DEFAULT_MODEL,
        max_batch_size: int = 8,
        continuous: bool = True,
        device: str | None = None,
        dtype: Any = None,
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.worker_id = worker_id
        self.max_batch_size = max_batch_size
        self.continuous = continuous
        self._torch = torch
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._device = device

        # Handles are external/dynamically-typed; treat as Any (stubs vary by version).
        self._tok: Any = AutoTokenizer.from_pretrained(model_name)
        if self._tok.pad_token_id is None:
            self._tok.pad_token = self._tok.eos_token
        kwargs: dict[str, Any] = {} if dtype is None else {"dtype": dtype}
        model: Any = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)
        self._model: Any = model.to(device).eval()
        self._eos = self._tok.eos_token_id

        self._waiting: deque[_Seq] = deque()
        self._running: list[_Seq] = []
        self._generated: dict[SeqId, list[int]] = {}
        self._cache: Any = None  # persistent batched DynamicCache, rows align to _running
        self._attn: Any = None  # [B, S] attention mask, left-padded

    # ---- Worker protocol ----------------------------------------------------

    def admit(self, req: Request) -> SeqId:
        seq_id = SeqId(req.id)
        messages = [{"role": "user", "content": req.prompt_text or "Hello"}]
        enc = self._tok.apply_chat_template(messages, add_generation_prompt=True, return_dict=True)
        ids = [int(t) for t in enc["input_ids"]]
        self._waiting.append(_Seq(seq_id=seq_id, token_ids=ids, max_new=max(1, req.max_tokens)))
        return seq_id

    def step(self) -> list[TokenEvent]:
        self._evict_finished()
        free = self.max_batch_size - len(self._running)
        admit_ok = (self.continuous or not self._running) and bool(self._waiting) and free > 0
        with self._torch.no_grad():
            if admit_ok:
                return self._prefill_step(free)
            if self._running:
                return self._decode_step()
        return []

    def in_flight(self) -> int:
        return len(self._running)

    # ---- ControlWorker extras ----------------------------------------------

    def is_idle(self) -> bool:
        return not self._waiting and not self._running

    def generated_ids(self, seq_id: SeqId) -> list[int]:
        """Token ids generated for a sequence (for verification / detokenizing)."""
        return self._generated.get(seq_id, [])

    def reset(self) -> None:
        """Clear all sequence state (keeps the loaded model) — used by the benchmark."""
        self._waiting.clear()
        self._running = []
        self._generated = {}
        self._cache = None
        self._attn = None

    def set_continuous(self, continuous: bool) -> None:
        """Switch batching mode (continuous <-> static) live. Safe at any point — the
        flag is only read in step(); running sequences finish, then admission follows
        the new rule. No model reload, no dropped work."""
        self.continuous = continuous

    def state(self) -> WorkerState:
        pending = sum(max(0, s.max_new - s.generated) for s in self._running)
        pending += sum(s.max_new for s in self._waiting)
        return WorkerState(
            worker_id=self.worker_id,
            queue_depth=len(self._waiting),
            pending_tokens=pending,
            in_flight=len(self._running),
            tok_per_s=0.0,  # measured by Metrics, not self-reported here
            healthy=True,
            speed_profile=1.0,
            cached_prefixes=frozenset(),
        )

    # ---- the decode loop (ours) --------------------------------------------

    def _evict_finished(self) -> None:
        if not self._running:
            return
        keep = [i for i, s in enumerate(self._running) if not s.finished]
        if len(keep) == len(self._running):
            return
        if not keep:
            self._running, self._cache, self._attn = [], None, None
            return
        idx = self._torch.tensor(keep, device=self._device)
        self._cache.batch_select_indices(idx)
        self._attn = self._attn[idx]
        self._running = [self._running[i] for i in keep]

    def _prefill_step(self, free: int) -> list[TokenEvent]:
        chunk = [self._waiting.popleft() for _ in range(min(free, len(self._waiting)))]
        ids, attn = self._left_pad([s.token_ids for s in chunk])
        out = self._model(
            input_ids=ids,
            attention_mask=attn,
            position_ids=self._position_ids(attn),
            use_cache=True,
        )
        if self._cache is None:
            self._cache, self._attn = out.past_key_values, attn
        else:
            self._merge(out.past_key_values, attn)
        self._running.extend(chunk)
        return self._sample_and_emit(out.logits[:, -1, :], chunk)

    def _decode_step(self) -> list[TokenEvent]:
        torch = self._torch
        last = torch.tensor([[s.token_ids[-1]] for s in self._running], device=self._device)
        pos = self._attn.sum(dim=-1, keepdim=True)  # next position per row (0-indexed)
        ones = torch.ones((len(self._running), 1), dtype=self._attn.dtype, device=self._device)
        self._attn = torch.cat([self._attn, ones], dim=1)
        out = self._model(
            input_ids=last,
            attention_mask=self._attn,
            position_ids=pos,
            past_key_values=self._cache,
            use_cache=True,
        )
        self._cache = out.past_key_values
        return self._sample_and_emit(out.logits[:, -1, :], self._running)

    def _sample_and_emit(self, logits: Any, seqs: list[_Seq]) -> list[TokenEvent]:
        next_ids = self._torch.argmax(logits, dim=-1).tolist()
        events: list[TokenEvent] = []
        for s, tid in zip(seqs, next_ids, strict=True):
            s.token_ids.append(int(tid))
            s.generated += 1
            self._generated.setdefault(s.seq_id, []).append(int(tid))
            is_final = tid == self._eos or s.generated >= s.max_new
            s.finished = is_final
            events.append(TokenEvent(seq_id=s.seq_id, is_final=is_final, ts=0.0))
        return events

    def _merge(self, chunk_cache: Any, chunk_attn: Any) -> None:
        """Splice a freshly-prefilled chunk's KV cache into the running batch.

        Left-pad both to a common length, then concatenate along the batch dim —
        no re-prefill of the already-running sequences.
        """
        torch = self._torch
        s_run, s_new = self._attn.shape[1], chunk_attn.shape[1]
        s = max(s_run, s_new)
        run_pad, new_pad = s - s_run, s - s_new
        self._attn = torch.cat(
            [self._pad_mask(self._attn, run_pad), self._pad_mask(chunk_attn, new_pad)], dim=0
        )
        for run_layer, new_layer in zip(self._cache.layers, chunk_cache.layers, strict=True):
            run_layer.keys = torch.cat(
                [self._pad_time(run_layer.keys, run_pad), self._pad_time(new_layer.keys, new_pad)],
                dim=0,
            )
            run_layer.values = torch.cat(
                [
                    self._pad_time(run_layer.values, run_pad),
                    self._pad_time(new_layer.values, new_pad),
                ],
                dim=0,
            )

    def _left_pad(self, batch: list[list[int]]) -> tuple[Any, Any]:
        torch = self._torch
        maxlen = max(len(b) for b in batch)
        pad = self._tok.pad_token_id
        ids = [[pad] * (maxlen - len(b)) + b for b in batch]
        mask = [[0] * (maxlen - len(b)) + [1] * len(b) for b in batch]
        return torch.tensor(ids, device=self._device), torch.tensor(mask, device=self._device)

    def _position_ids(self, attn: Any) -> Any:
        # left-padding-aware: real tokens get 0,1,2,...; pad positions clamped to 0
        pos = attn.long().cumsum(dim=-1) - 1
        pos.masked_fill_(attn == 0, 0)
        return pos

    def _pad_mask(self, mask: Any, pad: int) -> Any:
        if pad == 0:
            return mask
        torch = self._torch
        zeros = torch.zeros((mask.shape[0], pad), dtype=mask.dtype, device=self._device)
        return torch.cat([zeros, mask], dim=1)

    def _pad_time(self, t: Any, pad: int) -> Any:
        # t is [B, H, S, D]; left-pad the time dim (S, i.e. dim=-2) by `pad`.
        return t if pad == 0 else self._torch.nn.functional.pad(t, (0, 0, pad, 0))
