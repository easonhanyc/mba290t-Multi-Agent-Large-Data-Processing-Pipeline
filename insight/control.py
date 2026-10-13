"""Execution controls shared by every model stage.

- RateLimiter: one requests/minute + tokens/minute bucket per provider, shared by all workers.
- SpendLedger: one ledger per run directory. Before each attempt a worker reserves the
  attempt's worst-case cost (estimated input x input price + output cap x output price);
  admission stops when spent + unknown + reserved + next reservation would exceed the cap.
  Timeouts are settled as "unknown": their reservation keeps counting against the cap.
- execute(): one task = one logical request; transient errors (429/5xx/timeouts/connection)
  retry with exponential backoff and full jitter up to retry.max_attempts. Each attempt is
  logged as its own call row (dispatched -> succeeded/failed).
- Dispatcher: bounded thread pool; the orchestrator thread owns validation and results.
"""

import json
import random
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from .providers import ProviderError, estimate_tokens
from .util import monotonic, new_call_id, utc_now


class BudgetExceeded(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, limits: dict):
        # limits: provider -> (requests_per_minute, tokens_per_minute)
        self._lock = threading.Lock()
        self._state = {}
        for name, (rpm, tpm) in limits.items():
            self._state[name] = {"rpm": float(rpm), "tpm": float(tpm), "r": float(rpm), "t": float(tpm), "at": monotonic()}

    def acquire(self, provider, tokens, stop_event=None):
        st = self._state.get(provider)
        if st is None:
            return 0.0
        tokens = min(float(tokens), st["tpm"])
        waited = 0.0
        while True:
            with self._lock:
                now = monotonic()
                elapsed = now - st["at"]
                st["at"] = now
                st["r"] = min(st["rpm"], st["r"] + elapsed * st["rpm"] / 60.0)
                st["t"] = min(st["tpm"], st["t"] + elapsed * st["tpm"] / 60.0)
                if st["r"] >= 1 and st["t"] >= tokens:
                    st["r"] -= 1
                    st["t"] -= tokens
                    return waited
                need_r = max(0.0, 1 - st["r"]) * 60.0 / st["rpm"]
                need_t = max(0.0, tokens - st["t"]) * 60.0 / st["tpm"]
                delay = min(max(need_r, need_t, 0.01), 5.0)
            if stop_event is not None and stop_event.wait(delay):
                raise InterruptedError("stop requested while waiting for rate limit")
            if stop_event is None:
                time.sleep(delay)
            waited += delay


@dataclass
class Reservation:
    amount: float
    settled: bool = False


class SpendLedger:
    def __init__(self, cap_usd: float, spent: float = 0.0, unknown: float = 0.0):
        self.cap = float(cap_usd)
        self.spent = float(spent)       # settled actual cost (usage x rates)
        self.unknown = float(unknown)   # reservations of calls whose outcome/charge is unknown
        self.reserved = 0.0             # in-flight reservations
        self.denials = 0
        self._lock = threading.Lock()

    def reserve(self, amount: float) -> Reservation:
        with self._lock:
            if self.spent + self.unknown + self.reserved + amount > self.cap + 1e-12:
                self.denials += 1
                raise BudgetExceeded(
                    f"spent ${self.spent:.6f} + unknown ${self.unknown:.6f} + reserved ${self.reserved:.6f} "
                    f"+ next ${amount:.6f} would exceed cap ${self.cap:.2f}")
            self.reserved += amount
            return Reservation(amount)

    def settle(self, res: Reservation, actual: float, unknown: bool = False):
        with self._lock:
            if res.settled:
                return
            res.settled = True
            self.reserved -= res.amount
            if unknown:
                self.unknown += res.amount
            else:
                self.spent += actual

    def snapshot(self):
        with self._lock:
            return {"cap_usd": self.cap, "spent_usd": round(self.spent, 8), "unknown_usd": round(self.unknown, 8),
                    "reserved_usd": round(self.reserved, 8), "denials": self.denials}


@dataclass
class Task:
    role: str                 # enrich | verify | group | memo (contract role names)
    tier: str                 # primary | fallback1 | fallback2 | verify | group | memo
    provider: object          # adapter instance
    request: dict
    review_ids: list          # original review IDs actually sent in this request
    max_output_tokens: int
    prompt_chars: int
    label_config: str = None
    stage_config: str = None
    task_attempt: int = 1     # 1, or 2 for the single invalid-output retry
    context: dict = field(default_factory=dict)


@dataclass
class Outcome:
    status: str               # ok | budget | transient | permanent_input | systemic | invalid_output | cancelled
    result: object = None
    error: str = None
    request_id: str = None    # local id of the final attempt
    attempts: int = 0


class Context:
    """Per-invocation shared state handed to workers."""

    def __init__(self, store, cfg, rates, limiter, ledger, run_id, phase, worker_label="w"):
        self.store, self.cfg, self.rates, self.limiter, self.ledger = store, cfg, rates, limiter, ledger
        self.run_id, self.phase = run_id, phase
        self.stop_admitting = threading.Event()   # graceful: finish in-flight work, start nothing new
        self.stop_reason = None
        self.retry = cfg["retry"]
        self._worker_names = threading.local()
        self.worker_label = worker_label
        self.consecutive_failures = 0

    def request_stop(self, reason):
        if not self.stop_admitting.is_set():
            self.stop_reason = reason
            self.stop_admitting.set()

    def worker_name(self):
        name = getattr(self._worker_names, "name", None)
        if name is None:
            name = threading.current_thread().name
            self._worker_names.name = name
        return name


def backoff_delay(attempt, retry_cfg, retry_after=None):
    base = float(retry_cfg["backoff_initial_s"]) * (2 ** (attempt - 1))
    delay = random.uniform(0, min(float(retry_cfg["backoff_max_s"]), base))  # full jitter
    if retry_after:
        delay = max(delay, float(retry_after))
    return min(delay, float(retry_cfg["backoff_max_s"]))


def execute(task: Task, ctx: Context) -> Outcome:
    """Runs in a worker thread. Returns after success, a non-retryable error, or exhausted retries."""
    provider = task.provider
    est_in = estimate_tokens(task.prompt_chars)
    max_attempts = int(ctx.retry["max_attempts"])
    last = None
    if ctx.stop_admitting.is_set():  # queued before a stop (Ctrl-C, budget, systemic error): never sent
        return Outcome("cancelled", error="run stopping before this request started", attempts=0)
    for attempt in range(1, max_attempts + 1):
        try:
            worst = ctx.rates.worst_case(provider.name, provider.model, est_in, task.max_output_tokens)
        except KeyError as e:
            return Outcome("systemic", error=f"no price for {provider.name}/{provider.model}: {e}", attempts=attempt - 1)
        try:
            res = ctx.ledger.reserve(worst)
        except BudgetExceeded as e:
            return Outcome("budget", error=str(e), request_id=last, attempts=attempt - 1)
        try:
            ctx.limiter.acquire(provider.name, est_in + task.max_output_tokens, ctx.stop_admitting if attempt > 1 else None)
        except InterruptedError:
            ctx.ledger.settle(res, 0.0)
            return Outcome("cancelled", error="stopped while waiting for rate limit", request_id=last, attempts=attempt - 1)
        call_id = new_call_id("req")
        last = call_id
        started_wall, t0 = utc_now(), monotonic()
        ctx.store.call_dispatched({
            "request_id": call_id, "run_id": ctx.run_id, "role": task.role, "tier": task.tier, "phase": ctx.phase,
            "provider": provider.name, "model": provider.model, "effort": provider.effort,
            "label_config": task.label_config, "stage_config": task.stage_config,
            "review_ids": json.dumps(list(task.review_ids)), "attempt": attempt, "task_attempt": task.task_attempt,
            "outcome": "dispatched", "reserved_usd": worst, "started_at": started_wall, "worker": ctx.worker_name(),
            "max_output_tokens": task.max_output_tokens, "prompt_chars": task.prompt_chars,
        })
        try:
            result = provider.call(task.request)
        except ProviderError as e:
            duration = monotonic() - t0
            cost = ctx.rates.cost(provider.name, provider.model, e.usage) if e.usage else 0.0
            ctx.ledger.settle(res, cost, unknown=e.unknown_charge)
            ctx.store.call_settled(call_id, {
                # "unknown": the reservation keeps counting in this run, on resume and against the project cap
                "outcome": "unknown" if e.unknown_charge else "failed",
                "error": f"{e.kind}: {str(e)[:400]}", "http_status": e.status,
                "cost_usd": cost, "ended_at": utc_now(), "duration_s": round(duration, 4),
                "provider_request_id": e.provider_request_id,
                "notes": "charge unknown (timeout or dropped connection): reservation kept against the cap"
                         if e.unknown_charge else None,
            })
            if e.kind == "transient" and attempt < max_attempts and not ctx.stop_admitting.is_set():
                if ctx.stop_admitting.wait(backoff_delay(attempt, ctx.retry, e.retry_after)):
                    return Outcome("cancelled", error="stopped during backoff", request_id=call_id, attempts=attempt)
                continue
            return Outcome(e.kind, error=str(e)[:400], request_id=call_id, attempts=attempt)
        except Exception as e:  # unexpected adapter bug: record it, never swallow silently
            duration = monotonic() - t0
            ctx.ledger.settle(res, 0.0, unknown=True)
            ctx.store.call_settled(call_id, {"outcome": "unknown", "error": f"unexpected: {type(e).__name__}: {e}"[:400],
                                             "ended_at": utc_now(), "duration_s": round(duration, 4),
                                             "notes": "unexpected client error; charge unknown"})
            return Outcome("systemic", error=f"{type(e).__name__}: {e}", request_id=call_id, attempts=attempt)
        duration = monotonic() - t0
        u = result.usage
        try:
            cost = ctx.rates.cost(provider.name, provider.model, u, result.service_tier)
        except KeyError:  # tier without a dated rate: price at standard (the conservative choice) and say so
            cost = ctx.rates.cost(provider.name, provider.model, u, "standard")
        api_equiv = (ctx.rates.api_equivalent(result.model_reported, u) if result.billing == "subscription" else None)
        note = None
        if result.billing == "api" and provider.paid and u.get("usage_missing"):
            cost, note = worst, "provider reported no usage: charged at the worst-case reservation (conservative)"
        ctx.ledger.settle(res, cost)
        ctx.store.call_settled(call_id, {
            "outcome": "succeeded", "input_tokens": u.get("input_tokens"), "cached_input_tokens": u.get("cached_input_tokens"),
            "cache_write_tokens": u.get("cache_write_tokens"),
            "output_tokens": u.get("output_tokens"), "reasoning_tokens": u.get("reasoning_tokens"),
            "usage_raw": json.dumps(u, default=str), "cost_usd": cost, "ended_at": utc_now(),
            "duration_s": round(duration, 4), "provider_request_id": result.provider_request_id,
            "model_reported": result.model_reported, "finish": result.finish, "service_tier": result.service_tier,
            "billing": result.billing, "api_equiv_usd": api_equiv, "notes": note,
        })
        return Outcome("ok", result=result, request_id=call_id, attempts=attempt)
    return Outcome("transient", error="retries exhausted", request_id=last, attempts=max_attempts)



class Dispatcher:
    """Worker pools sharing one context (ledger, limiters). Cross-check tasks get their own pool so fast
    one-review calls never queue behind slow batched LLM calls; capacity() counts the main pool only."""

    SIDE_TIERS = ("crosscheck",)

    def __init__(self, ctx: Context, workers: int, per_worker: int, side_workers: int = 0):
        self.ctx = ctx
        self.capacity_total = max(1, workers * per_worker)
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="worker")
        self.side_pool = (ThreadPoolExecutor(max_workers=side_workers, thread_name_prefix="xcheck")
                          if side_workers > 0 else None)
        self.in_flight = {}

    def capacity(self):
        return self.capacity_total - sum(1 for t in self.in_flight.values() if t.tier not in self.SIDE_TIERS)

    def count(self, tier):
        return sum(1 for t in self.in_flight.values() if t.tier == tier)

    def submit(self, task: Task):
        pool = self.side_pool if (self.side_pool and task.tier in self.SIDE_TIERS) else self.pool
        fut = pool.submit(execute, task, self.ctx)
        self.in_flight[fut] = task

    def wait_some(self, timeout=0.5):
        if not self.in_flight:
            return []
        done, _ = wait(list(self.in_flight), timeout=timeout, return_when=FIRST_COMPLETED)
        out = []
        for fut in done:
            task = self.in_flight.pop(fut)
            out.append((task, fut.result()))
        return out

    def shutdown(self):
        self.pool.shutdown(wait=True, cancel_futures=False)
        if self.side_pool:
            self.side_pool.shutdown(wait=True, cancel_futures=False)
