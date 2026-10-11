"""Provider adapters behind one small interface, plus the shared rate table.

Every adapter wraps the provider's official SDK with the SDK's own retries DISABLED
(max_retries=0), so each HTTP attempt is visible to the pipeline: it is reserved in the
spend ledger, rate-limited, logged, and retried (or not) by insight.control.

SDKs are imported lazily inside each adapter: ingest, ranking, exports and the offline
cost calculator run on the standard library alone.
"""

import csv
import math
import os
import threading
from dataclasses import dataclass, field

from ..util import PROJECT_ROOT


class ProviderError(Exception):
    """kind: transient | permanent_input | systemic | invalid_output."""

    def __init__(self, kind, message, status=None, retry_after=None, unknown_charge=False, usage=None,
                 provider_request_id=None):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retry_after = retry_after
        self.unknown_charge = unknown_charge
        self.usage = usage
        self.provider_request_id = provider_request_id


@dataclass
class Result:
    data: object                      # parsed answers / JSON object, or None when output was unusable
    text: str = ""
    usage: dict = field(default_factory=dict)  # input/cached/cache_write/output/reasoning tokens (+ raw)
    provider_request_id: str | None = None
    model_reported: str | None = None
    finish: str = "complete"          # complete | truncated | refusal | ...
    service_tier: str = "standard"    # processing tier the provider reports it used (standard | flex | subscription)
    billing: str = "api"              # api (billed per token) | subscription (Claude Pro via claude -p; not billed per call)


def empty_usage():
    return {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0,
            "reasoning_tokens": 0}


class MissingKeyError(RuntimeError):
    pass


# ---- rates -------------------------------------------------------------------------------------
class Rates:
    """Prices from cost/rates.csv (USD per 1,000,000 units, dated, with source links).

    Rows are keyed by (provider, model, tier, item). Billing items are mutually exclusive:
      input_uncached    = input - cached - cache_write
      input_cached      = provider prompt-cache reads
      input_cache_write = tokens written to the provider prompt cache (priced as uncached input when no row)
      output            = output tokens, already including reasoning/thinking tokens (never added twice)
    kind=subscription rows (Claude Pro via `claude -p`) carry no per-call charge; their API-equivalent
    value is reported separately from the kind=api row of the reported model, never as billed spend.
    """

    ITEMS = ("input_uncached", "input_cached", "input_cache_write", "output")
    REQUIRED = ("input_uncached", "input_cached", "output")

    def __init__(self, path=None, shadow_stub=False):
        self.path = path or PROJECT_ROOT / "cost" / "rates.csv"
        self.shadow_stub = shadow_stub
        self.table = {}
        self.kinds = {}
        with open(self.path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                kind = row.get("kind") or "api"
                if kind not in ("api", "subscription"):
                    continue
                tier = (row.get("tier") or "standard").strip() or "standard"
                key = (row["provider"], row["model"], tier, row["item"])
                self.table[key] = float(row["usd_per_million"]) / 1_000_000
                self.kinds[(row["provider"], row["model"])] = kind

    def is_subscription(self, provider, model):
        return self.kinds.get((provider, model)) == "subscription"

    def _lookup(self, provider, model, tier="standard"):
        if model.startswith("stub-"):
            if not self.shadow_stub:
                return {i: 0.0 for i in self.ITEMS}
            model = model[len("stub-"):]  # shadow pricing: stub calls priced as the real model (demo only)
        tier = {"default": "standard", "auto": "standard", None: "standard", "": "standard"}.get(tier, tier)
        if self.kinds.get((provider, model)) == "subscription":
            tier = "subscription"
        prices = {i: self.table.get((provider, model, tier, i)) for i in self.ITEMS}
        if any(prices[i] is None for i in self.REQUIRED):
            missing = [i for i in self.REQUIRED if prices[i] is None]
            raise KeyError(f"No rate for {provider}/{model} tier {tier} items {missing} in {self.path}")
        if prices["input_cache_write"] is None:
            prices["input_cache_write"] = prices["input_uncached"]
        return prices

    def has(self, provider, model, tier="standard"):
        try:
            self._lookup(provider, model, tier)
            return True
        except KeyError:
            return False

    @staticmethod
    def split(usage) -> dict:
        """Mutually exclusive billed units from one call's usage."""
        cached = int(usage.get("cached_input_tokens") or 0)
        write = int(usage.get("cache_write_tokens") or 0)
        inp = int(usage.get("input_tokens") or 0)
        return {"input_uncached": max(inp - cached - write, 0), "input_cached": cached, "input_cache_write": write,
                "output": int(usage.get("output_tokens") or 0)}

    def cost(self, provider, model, usage, tier="standard") -> float:
        p = self._lookup(provider, model, tier)
        return sum(units * p[item] for item, units in self.split(usage).items())

    def worst_case(self, provider, model, est_input_tokens, max_output_tokens) -> float:
        """Reservation before dispatch: always at the standard tier (the most expensive one used)."""
        p = self._lookup(provider, model, "standard")
        return est_input_tokens * max(p["input_uncached"], p["input_cache_write"]) + max_output_tokens * p["output"]

    def api_equivalent(self, model_reported, usage, provider="anthropic"):
        """What a subscription call would have cost on the provider's API (None if the model has no api row)."""
        if not model_reported:
            return None
        candidates = sorted({m for (pv, m, t, i) in self.table if pv == provider and t == "standard"
                             and self.kinds.get((pv, m)) == "api" and model_reported.startswith(m)}, key=len)
        if not candidates:
            return None
        return self.cost(provider, candidates[-1], usage, "standard")


def estimate_tokens(chars: int) -> int:
    """Conservative pre-call estimate (about 3 characters per token) for reservations only."""
    return int(math.ceil(chars / 3)) + 16


# ---- registry -----------------------------------------------------------------------------------
_CLIENT_LOCK = threading.Lock()


class ProviderRegistry:
    def __init__(self, cfg, base_url_override=None):
        self.cfg = cfg
        self.base_url_override = base_url_override or {}
        self._instances = {}

    def api_key(self, name):
        spec = self.cfg.provider(name)
        if self.cfg.offline_stub:
            return "stub-key-not-secret"
        if spec["kind"] == "claude_code":
            return None  # Claude Pro login of the local `claude` CLI; checked by readiness_problems()
        key = os.environ.get(spec["api_key_env"], "").strip()
        if not key:
            raise MissingKeyError(f"{spec['api_key_env']} is not set (needed for provider '{name}').")
        return key

    def missing_keys(self):
        missing = []
        for name in self.cfg.active_providers():
            try:
                self.api_key(name)
            except MissingKeyError:
                missing.append(self.cfg.provider(name)["api_key_env"])
        return missing

    def readiness_problems(self):
        """Non-key prerequisites, e.g. the `claude` CLI must be logged in with a subscription (live runs only)."""
        problems = []
        if self.cfg.offline_stub:
            return problems
        for name in self.cfg.active_providers():
            spec = self.cfg.provider(name)
            if spec["kind"] == "claude_code":
                from .claude_code import auth_problem
                p = auth_problem(spec)
                if p:
                    problems.append(f"{name}: {p}")
        return problems

    def get(self, name, model, effort):
        key = (name, model, effort)
        with _CLIENT_LOCK:
            if key in self._instances:
                return self._instances[key]
            spec = dict(self.cfg.provider(name))
            if name in self.base_url_override:
                spec["base_url"] = self.base_url_override[name]
            kind = spec["kind"]
            if kind == "typesafe":
                from .jev import JevProvider as cls
            elif kind == "openai":
                from .openai_responses import OpenAIResponsesProvider as cls
            elif kind == "anthropic":
                from .anthropic_messages import AnthropicMessagesProvider as cls
            elif kind == "claude_code":
                from .claude_code import ClaudeCodeProvider as cls
                if self.cfg.offline_stub:
                    spec["stub"] = True
            else:
                raise ValueError(f"Unknown provider kind {kind!r}")
            inst = cls(name=name, model=model, effort=effort, api_key=self.api_key(name), spec=spec,
                       paid=not self.cfg.offline_stub)
            self._instances[key] = inst
            return inst
