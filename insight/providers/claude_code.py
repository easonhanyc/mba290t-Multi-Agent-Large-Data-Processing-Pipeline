"""Claude Code headless adapter: `claude -p` under the user's Claude Pro login (no API key, no per-call bill).

Used for low-volume roles (verify, group naming, memo, the rare fallback2). Each call runs the local
`claude` CLI in an empty temporary directory with every tool, MCP server and settings file disabled,
our own system prompt, a JSON schema for structured output, and the prompt on stdin. ANTHROPIC_API_KEY
is removed from the child environment so the CLI cannot silently switch to API billing.

Usage is the CLI's own report (input, cache read/write, output tokens per model). Billing is
"subscription": the calculator shows $0 billed and, separately, the API-equivalent price from the
reported model's API rates (the course notes that subscription access is not proof calls are free).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import ProviderError, Result, empty_usage

_STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK",
              "CLAUDE_CODE_USE_VERTEX")
_LIMIT_WORDS = ("usage limit", "limit reached", "limit will reset", "out of extra usage", "weekly limit",
                "5-hour limit", "upgrade to")
_AUTH_WORDS = ("failed to authenticate", "not logged in", "please run /login", "oauth", "invalid api key")


def _command(spec):
    if spec.get("stub"):
        return [sys.executable, str(Path(__file__).resolve().parent.parent / "stub_claude.py")]
    return [spec.get("command", "claude")]


def _child_env(max_output_tokens=None):
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}
    if max_output_tokens:
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(int(max_output_tokens))
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


def auth_problem(spec):
    """None when `claude auth status` reports a subscription login; otherwise a short explanation."""
    exe = spec.get("command", "claude")
    if not shutil.which(exe):
        return f"`{exe}` CLI not found on PATH"
    try:
        out = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=30, env=_child_env(),
                             stdin=subprocess.DEVNULL)
        status = json.loads(out.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return f"could not read `claude auth status`: {e}"
    if not status.get("loggedIn"):
        return "the `claude` CLI is not logged in; run `claude auth login` with the Claude Pro account"
    method = str(status.get("authMethod", ""))
    if "api" in method.lower() and "key" in method.lower():
        return f"the `claude` CLI is using {method}; log in with the Claude Pro subscription instead"
    return None


class ClaudeCodeProvider:
    kind = "claude_code"

    def __init__(self, name, model, effort, api_key, spec, paid):
        self.name, self.model, self.effort, self.paid = name, model, effort, paid
        self.spec = spec
        self.timeout = float(spec.get("timeout_s", 180))
        self.command = _command(spec)
        self.workdir = tempfile.mkdtemp(prefix="insight-claude-")  # empty: no project files, no CLAUDE.md

    def _args(self, request):
        args = self.command + ["-p", "--output-format", "json", "--model", self.model, "--tools", "",
                               "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands",
                               "--setting-sources", "project",  # empty temp cwd: no user settings, hooks or apiKeyHelper
                               "--system-prompt", request["system"],
                               "--json-schema", json.dumps(request["schema"], separators=(",", ":"))]
        if self.effort in ("low", "medium", "high"):
            args += ["--effort", self.effort]
        return args

    def call(self, request, timeout=None) -> Result:
        timeout = timeout or self.timeout
        try:
            proc = subprocess.run(self._args(request), input=request["user"], capture_output=True, text=True,
                                  timeout=timeout, cwd=self.workdir,
                                  env=_child_env(request.get("max_output_tokens")))
        except subprocess.TimeoutExpired as e:
            raise ProviderError("transient", f"claude -p timed out after {timeout:.0f}s", unknown_charge=True) from e
        except OSError as e:
            raise ProviderError("systemic", f"could not start claude CLI: {e}") from e
        try:
            d = json.loads(proc.stdout)
        except json.JSONDecodeError:
            msg = (proc.stderr or proc.stdout or "").strip()[:300]
            raise ProviderError("transient", f"claude -p exit {proc.returncode} without JSON: {msg}")
        usage, model_reported = _usage(d)
        rid = f"cc-{d.get('session_id') or d.get('uuid')}"
        if d.get("is_error"):
            text = str(d.get("result") or d.get("terminal_reason") or "error").strip()
            low = text.lower()
            status = d.get("api_error_status")
            if any(w in low for w in _LIMIT_WORDS):
                raise ProviderError("systemic", f"Claude Pro usage limit: {text[:200]}", usage=usage,
                                    provider_request_id=rid)
            if any(w in low for w in _AUTH_WORDS):
                raise ProviderError("systemic", f"claude CLI authentication: {text[:200]}", provider_request_id=rid)
            if status in (429, 500, 502, 503, 504, 529) or "overloaded" in low or "rate limit" in low:
                raise ProviderError("transient", f"claude -p {status}: {text[:200]}", status=status, usage=usage,
                                    provider_request_id=rid)
            raise ProviderError("invalid_output", f"claude -p error: {text[:200]}", usage=usage, provider_request_id=rid)
        data = d.get("structured_output")
        finish = "complete"
        text = d.get("result") or ""
        if data is None:
            raw = text.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                finish = "malformed_json"
        if d.get("stop_reason") == "max_tokens":
            finish = "truncated"
        return Result(data=data if finish == "complete" else None, text=text if isinstance(text, str) else "",
                      usage=usage, provider_request_id=rid, model_reported=model_reported, finish=finish,
                      service_tier="subscription", billing="subscription")


def _usage(d):
    """Sum per-model usage (includes any auxiliary model the CLI used); fall back to the top-level block."""
    usage = empty_usage()
    per_model = d.get("modelUsage") or {}
    main, main_out = None, -1
    if per_model:
        for model, m in per_model.items():
            inp, cr, cw = int(m.get("inputTokens") or 0), int(m.get("cacheReadInputTokens") or 0), \
                int(m.get("cacheCreationInputTokens") or 0)
            usage["input_tokens"] += inp + cr + cw
            usage["cached_input_tokens"] += cr
            usage["cache_write_tokens"] += cw
            usage["output_tokens"] += int(m.get("outputTokens") or 0)
            if int(m.get("outputTokens") or 0) > main_out:
                main, main_out = model, int(m.get("outputTokens") or 0)
    else:
        u = d.get("usage") or {}
        cr, cw = int(u.get("cache_read_input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0)
        usage["input_tokens"] = int(u.get("input_tokens") or 0) + cr + cw
        usage["cached_input_tokens"] = cr
        usage["cache_write_tokens"] = cw
        usage["output_tokens"] = int(u.get("output_tokens") or 0)
    usage["reasoning_tokens"] = int(((d.get("usage") or {}).get("output_tokens_details") or {}).get("thinking_tokens") or 0)
    usage["raw"] = {"usage": d.get("usage"), "modelUsage": per_model, "total_cost_usd_cli_estimate": d.get("total_cost_usd"),
                    "num_turns": d.get("num_turns"), "duration_api_ms": d.get("duration_api_ms")}
    return usage, main
