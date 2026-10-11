"""Anthropic Messages API adapter (Claude Sonnet 5), used only as a capped fallback or memo option."""

import json

from . import ProviderError, Result, empty_usage


class AnthropicMessagesProvider:
    kind = "anthropic"

    def __init__(self, name, model, effort, api_key, spec, paid):
        import anthropic

        self.anthropic = anthropic
        self.name, self.model, self.effort, self.paid = name, model, effort, paid
        self.timeout = float(spec.get("timeout_s", 120))
        self.client = anthropic.Anthropic(api_key=api_key, base_url=spec["base_url"], max_retries=0, timeout=self.timeout)

    def call(self, request, timeout=None) -> Result:
        """request = {"system", "user", "schema", "max_output_tokens"}."""
        a = self.anthropic
        output_config = {"format": {"type": "json_schema", "schema": request["schema"]}}
        if self.effort and self.effort != "n/a":
            output_config["effort"] = self.effort
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=int(request["max_output_tokens"]),
                system=request["system"],
                messages=[{"role": "user", "content": request["user"]}],
                output_config=output_config,
                thinking={"type": "adaptive"},
                timeout=timeout or self.timeout,
            )
        except a.APIResponseValidationError as e:
            raise ProviderError("invalid_output", f"response failed SDK validation: {e}") from e
        except (a.RateLimitError, a.OverloadedError, a.InternalServerError, a.ServiceUnavailableError) as e:
            raise ProviderError("transient", f"{type(e).__name__}: {e}", status=getattr(e, "status_code", None),
                                retry_after=_retry_after(getattr(e, "response", None))) from e
        except (a.AuthenticationError, a.PermissionDeniedError, a.NotFoundError) as e:
            raise ProviderError("systemic", f"{type(e).__name__}: {e}", status=getattr(e, "status_code", None)) from e
        except (a.BadRequestError, a.RequestTooLargeError, a.UnprocessableEntityError) as e:
            raise ProviderError("permanent_input", f"{type(e).__name__}: {e}", status=getattr(e, "status_code", None)) from e
        except a.APITimeoutError as e:
            raise ProviderError("transient", f"timeout: {e}", unknown_charge=True) from e
        except a.APIConnectionError as e:
            raise ProviderError("transient", f"connection error: {e}") from e
        except a.APIStatusError as e:
            kind = "transient" if e.status_code in (408, 409, 429) or e.status_code >= 500 else "permanent_input"
            raise ProviderError(kind, f"HTTP {e.status_code}: {e}", status=e.status_code) from e

        usage = empty_usage()
        u = msg.usage
        usage["input_tokens"] = int(u.input_tokens or 0) + int(u.cache_read_input_tokens or 0) + int(u.cache_creation_input_tokens or 0)
        usage["cached_input_tokens"] = int(u.cache_read_input_tokens or 0)
        usage["output_tokens"] = int(u.output_tokens or 0)
        if u.cache_creation_input_tokens:
            usage["cache_write_tokens"] = int(u.cache_creation_input_tokens)
        finish = {"end_turn": "complete", "max_tokens": "truncated", "refusal": "refusal"}.get(msg.stop_reason, str(msg.stop_reason))
        text = next((b.text for b in msg.content if getattr(b, "type", None) == "text"), "")
        data = None
        if finish == "complete":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                finish = "malformed_json"
        return Result(data=data, text=text, usage=usage, provider_request_id=getattr(msg, "_request_id", None) or msg.id,
                      model_reported=msg.model, finish=finish)


def _retry_after(response):
    try:
        value = response.headers.get("retry-after")
        return float(value) if value else None
    except (AttributeError, TypeError, ValueError):
        return None
