"""OpenAI Decisions API adapter (POST /v1/decisions, gpt-6-luna): one review per request, typed answers.

Takes the same request as the Jev adapter ({"state", "questions"} from prompts.jev_request) and returns
answers in the same shape, so EnrichStage parses, validates and routes both classifiers identically:
  Jev choice -> Decisions choice (choices = value/description)    answer: choice, confidence, probabilities
  Jev score  -> Decisions score  (levels ordered low to high)     answer: score (0..n-1 weighted), confidence
  Jev noul   -> Decisions predicate                               answer: noul = probability
A refused question is left out of the answers, so the parser reports it missing (invalid -> retry -> fallback).
The installed SDK predates a typed `client.decisions`, so the request goes through the SDK's own HTTP
client (same auth, timeouts and error classes) with retries disabled like every other adapter. The raw
response type is the SDK's own transport (httpx2): importing the legacy `httpx` package from a worker
thread races with the SDK's response-type check in other threads.
"""

import json

from . import ProviderError, Result, empty_usage
from .openai_responses import raise_mapped


def to_decisions_questions(questions: dict) -> list:
    out = []
    for name, q in questions.items():
        t, crit = q["type"], q["criteria"]
        if t == "choice":
            out.append({"type": "choice", "name": name, "instructions": q["instructions"],
                        "choices": [{"value": k, "description": v} for k, v in crit.items()]})
        elif t == "score":
            out.append({"type": "score", "name": name, "instructions": q["instructions"],
                        "levels": [{"label": f"level_{i}", "description": d} for i, d in enumerate(crit)]})
        elif t == "noul":
            extra = " ".join(f"{k.capitalize()} means: {v}" for k, v in crit.items()) if isinstance(crit, dict) else ""
            out.append({"type": "predicate", "name": name, "instructions": f"{q['instructions']} {extra}".strip()})
        else:
            raise ValueError(f"question {name!r}: unsupported type {t!r}")
    return out


def from_decisions_answers(answers: list) -> tuple:
    """Decisions answers list -> (Jev-shaped {name: answer}, [refused names])."""
    out, refused = {}, []
    for a in answers or []:
        name, t = a.get("name"), a.get("type")
        if t == "choice":
            out[name] = {"type": "choice", "choice": a.get("choice"), "confidence": a.get("confidence"),
                         "probabilities": {p.get("value"): p.get("probability") for p in a.get("probabilities") or []}}
        elif t == "score":
            out[name] = {"type": "score", "score": a.get("score"), "confidence": a.get("confidence"),
                         "probabilities": {str(p.get("value")): p.get("probability") for p in a.get("probabilities") or []}}
        elif t == "predicate":
            out[name] = {"type": "noul", "noul": a.get("probability")}
        elif t == "refusal":
            refused.append(name)
    return out, refused


class OpenAIDecisionsProvider:
    kind = "openai_decisions"

    def __init__(self, name, model, effort, api_key, spec, paid):
        import httpx2
        import openai

        self.openai, self.httpx2 = openai, httpx2
        self.name, self.model, self.effort, self.paid = name, model, effort, paid
        self.timeout = float(spec.get("timeout_s", 30))
        self.client = openai.OpenAI(api_key=api_key, base_url=spec["base_url"], max_retries=0, timeout=self.timeout)

    def call(self, request, timeout=None) -> Result:
        """request = {"state": <json>, "questions": {qid: {"type", "instructions", "criteria"}}} (Jev shape)."""
        o = self.openai
        body = {"model": self.model,
                # The review travels as JSON data under the key the questions refer to (`review_text`).
                "input": json.dumps(request["state"], ensure_ascii=False),
                "questions": to_decisions_questions(request["questions"])}
        try:
            resp = self.client.post("/decisions", cast_to=self.httpx2.Response, body=body,
                                    options={"timeout": timeout or self.timeout})
        except o.OpenAIError as e:
            raise_mapped(o, e)
        rid = resp.headers.get("x-request-id")
        try:
            payload = resp.json()
        except ValueError as e:
            raise ProviderError("invalid_output", f"response is not JSON: {e}", status=resp.status_code) from e
        answers, refused = from_decisions_answers(payload.get("answers"))
        raw = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        usage = empty_usage()
        if not raw or not raw.get("input_tokens"):
            usage["usage_missing"] = True  # charged at the reservation by control.execute (never assumed free)
        if raw:
            usage["input_tokens"] = int(raw.get("input_tokens") or 0)
            usage["output_tokens"] = int(raw.get("output_tokens") or 0)
            details = raw.get("input_tokens_details") or {}
            usage["cached_input_tokens"] = int(details.get("cached_tokens") or 0)
        usage["raw"] = raw  # evidence: kept verbatim (None if the beta response carries no usage block)
        usage["rate_limits"] = {k: v for k, v in resp.headers.items() if k.lower().startswith("x-ratelimit")} or None
        return Result(data={"answers": answers, "refused": refused}, usage=usage,
                      model_reported=payload.get("model") or self.model,
                      provider_request_id=rid or payload.get("id"),
                      finish="refusal" if refused and not answers else "complete")
