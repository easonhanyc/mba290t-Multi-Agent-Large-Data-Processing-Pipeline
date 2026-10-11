"""TypeSafe Jev (System One) adapter: one review per request, typed Choice/Score/Noul answers."""

from . import ProviderError, Result, empty_usage


class JevProvider:
    kind = "typesafe"

    def __init__(self, name, model, effort, api_key, spec, paid):
        import typesafe_sdk as ts

        self.ts = ts
        self.name, self.model, self.effort, self.paid = name, model, effort, paid
        self.timeout = float(spec.get("timeout_s", 30))
        self.client = ts.TypeSafeClient(api_key=api_key, model=model, base_url=spec["base_url"],
                                        retry=ts.RetryPolicy(max_retries=0), timeout=self.timeout)

    def call(self, request, timeout=None) -> Result:
        """request = {"state": <json>, "questions": {qid: {"type", "instructions", "criteria"}}}."""
        ts = self.ts
        try:
            resp = self.client.system_one(request["state"], request["questions"], model=self.model,
                                          timeout=timeout or self.timeout)
        except ts.TypeSafeAPIResponseValidationError as e:
            raise ProviderError("invalid_output", f"response failed SDK validation: {e}", status=e.status) from e
        except ts.TypeSafeRateLimitError as e:
            wait = (e.retry_after_ms or 0) / 1000 or None
            raise ProviderError("transient", f"rate limited: {e}", status=e.status, retry_after=wait) from e
        except ts.TypeSafeInternalServerError as e:
            raise ProviderError("transient", f"server error: {e}", status=e.status) from e
        except (ts.TypeSafeAuthenticationError, ts.TypeSafePermissionDeniedError, ts.TypeSafeNotFoundError) as e:
            raise ProviderError("systemic", f"{type(e).__name__}: {e}", status=e.status) from e
        except (ts.TypeSafeBadRequestError, ts.TypeSafeUnprocessableEntityError) as e:
            raise ProviderError("permanent_input", f"{type(e).__name__}: {e}", status=e.status) from e
        except ts.TypeSafeAPITimeoutError as e:
            raise ProviderError("transient", f"timeout: {e}", unknown_charge=True) from e
        except ts.TypeSafeAPIConnectionError as e:
            raise ProviderError("transient", f"connection error: {e}") from e
        except ts.TypeSafeAPIError as e:
            kind = "transient" if e.status in (408, 409, 429) or e.status >= 500 else "permanent_input"
            raise ProviderError(kind, f"HTTP {e.status}: {e}", status=e.status) from e
        answers = {}
        for qid, ans in resp.answers.items():
            answers[qid] = ans.model_dump(mode="json")
        usage = empty_usage()
        usage["input_tokens"] = int(resp.usage.input_tokens or 0)
        usage["output_tokens"] = int(resp.usage.output_tokens or 0)
        return Result(data={"answers": answers}, usage=usage, model_reported=resp.model,
                      provider_request_id=resp.__dict__.get("_request_id"))
