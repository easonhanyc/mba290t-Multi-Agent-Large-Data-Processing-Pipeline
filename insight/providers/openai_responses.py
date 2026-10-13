"""OpenAI Responses API adapter (GPT-6 Luna), strict JSON-schema output, explicit reasoning effort."""

import json

from . import ProviderError, Result, empty_usage


class OpenAIResponsesProvider:
    kind = "openai"

    def __init__(self, name, model, effort, api_key, spec, paid):
        import openai

        self.openai = openai
        self.name, self.model, self.effort, self.paid = name, model, effort, paid
        self.timeout = float(spec.get("timeout_s", 90))
        self.client = openai.OpenAI(api_key=api_key, base_url=spec["base_url"], max_retries=0, timeout=self.timeout)

    def call(self, request, timeout=None) -> Result:
        """request = {"system", "user", "schema", "schema_name", "max_output_tokens"}."""
        o = self.openai
        kwargs = dict(
            model=self.model,
            instructions=request["system"],
            input=request["user"],
            text={"format": {"type": "json_schema", "name": request.get("schema_name", "output"),
                             "schema": request["schema"], "strict": True}},
            max_output_tokens=int(request["max_output_tokens"]),
            store=False,
            timeout=timeout or float(request.get("timeout_s") or self.timeout),
        )
        if request.get("service_tier") and request["service_tier"] != "standard":
            kwargs["service_tier"] = request["service_tier"]  # "flex": 50% of Standard, slower, may 429
        if request.get("prompt_cache_key"):
            kwargs["prompt_cache_key"] = request["prompt_cache_key"]
        if self.effort and self.effort != "n/a":
            kwargs["reasoning"] = {"effort": self.effort}  # "none" is supported and cheapest for GPT-6 Luna
        try:
            raw_resp = self.client.responses.with_raw_response.create(**kwargs)
            resp = raw_resp.parse()
        except o.OpenAIError as e:
            raise_mapped(o, e)
        headers = getattr(raw_resp, "headers", None) or {}

        usage = empty_usage()
        if resp.usage is None:
            usage["usage_missing"] = True  # charged at the reservation by control.execute (never assumed free)
        else:
            usage["input_tokens"] = int(resp.usage.input_tokens or 0)
            usage["output_tokens"] = int(resp.usage.output_tokens or 0)
            details = getattr(resp.usage, "input_tokens_details", None)
            usage["cached_input_tokens"] = int(getattr(details, "cached_tokens", 0) or 0)
            for attr in ("cache_write_tokens", "cache_creation_tokens", "cached_write_tokens"):
                if getattr(details, attr, None):
                    usage["cache_write_tokens"] = int(getattr(details, attr))
                    break
            odetails = getattr(resp.usage, "output_tokens_details", None)
            usage["reasoning_tokens"] = int(getattr(odetails, "reasoning_tokens", 0) or 0)
            try:
                usage["raw"] = resp.usage.model_dump()
            except Exception:  # raw usage is evidence only; never fail a call over it
                usage["raw"] = None
        usage["rate_limits"] = {k: v for k, v in headers.items() if str(k).lower().startswith("x-ratelimit")} or None
        tier = getattr(resp, "service_tier", None)
        tier = "standard" if tier in (None, "default", "auto") else str(tier)
        rid = getattr(resp, "_request_id", None) or headers.get("x-request-id") or resp.id
        finish = "complete"
        if resp.status == "incomplete":
            reason = getattr(resp.incomplete_details, "reason", None) or "incomplete"
            finish = "truncated" if reason == "max_output_tokens" else str(reason)
        text, refused = "", False
        for item in resp.output or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in item.content or []:
                if getattr(part, "type", None) == "output_text":
                    text += part.text
                elif getattr(part, "type", None) == "refusal":
                    refused = True
        if refused:
            finish = "refusal"
        data = None
        if finish == "complete":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                finish = "malformed_json"
        return Result(data=data, text=text, usage=usage, provider_request_id=rid,
                      model_reported=resp.model, finish=finish, service_tier=tier)


QUOTA_CODES = {"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"}


def raise_mapped(o, e):
    """Map an OpenAI SDK exception to ProviderError (shared by the Responses and Decisions adapters)."""
    status = getattr(e, "status_code", None)
    if isinstance(e, o.APIResponseValidationError):
        raise ProviderError("invalid_output", f"response failed SDK validation: {e}") from e
    if isinstance(e, o.RateLimitError):
        if getattr(e, "type", None) in QUOTA_CODES or getattr(e, "code", None) in QUOTA_CODES:
            # prepaid credit used up (observed live: type insufficient_quota, code credit_balance_exhausted): stop now
            raise ProviderError("systemic", f"insufficient_quota: {e}", status=429) from e
        raise ProviderError("transient", f"rate limited: {e}", status=429,
                            retry_after=_retry_after(getattr(e, "response", None))) from e
    if isinstance(e, (o.InternalServerError, o.ConflictError)):
        raise ProviderError("transient", f"server error: {e}", status=status) from e
    if isinstance(e, (o.AuthenticationError, o.PermissionDeniedError, o.NotFoundError)):
        raise ProviderError("systemic", f"{type(e).__name__}: {e}", status=status) from e
    if isinstance(e, (o.BadRequestError, o.UnprocessableEntityError)):
        raise ProviderError("permanent_input", f"{type(e).__name__}: {e}", status=status) from e
    if isinstance(e, o.APITimeoutError):
        raise ProviderError("transient", f"timeout: {e}", unknown_charge=True) from e
    if isinstance(e, o.APIConnectionError):
        # The request may have reached the server before the connection dropped: keep the reservation.
        raise ProviderError("transient", f"connection error: {e}", unknown_charge=True) from e
    if isinstance(e, o.APIStatusError):
        kind = "transient" if status in (408, 409, 429) or status >= 500 else "permanent_input"
        raise ProviderError(kind, f"HTTP {status}: {e}", status=status) from e
    raise e


def _retry_after(response):
    try:
        value = response.headers.get("retry-after")
        return float(value) if value else None
    except (AttributeError, TypeError, ValueError):
        return None
