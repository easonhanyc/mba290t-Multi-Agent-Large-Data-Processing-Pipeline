"""Offline stub server for plumbing tests. NOT a model.

It speaks the three providers' wire formats on 127.0.0.1 so the real SDK adapters, retries,
ledger, cache, resume and exports can be exercised with zero network calls and zero spend:
  POST /v1/systemone   TypeSafe System One (Choice / Score / Noul answers)
  POST /v1/responses   OpenAI Responses API (json_schema output)
  POST /v1/messages    Anthropic Messages API (output_config json_schema)
  POST /v1/decisions   OpenAI Decisions API (choice / score / predicate answers)

Answers are chosen by hashing the request, so they are deterministic and MEANINGLESS as
labels. Reported token counts are character-based placeholders. The pipeline renames every
model ID with a "stub-" prefix in this mode, so stub artifacts cannot pass for real output.

Fault injection (per provider, 1-based request counter): "429", "500", "timeout", "slow",
"malformed", "truncated"; e.g. {"typesafe": {3: "429"}, "openai": {2: "malformed"}}.
"""

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _h(*parts) -> int:
    return int(hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12], 16)


def _choice_answer(seed, options, forced=None):
    n = len(options)
    idx = options.index(forced) if forced in options else _h(seed, "pick") % n
    top = 0.50 + (_h(seed, "conf") % 50) / 100.0  # 0.50 .. 0.99: mostly confident, some below thresholds
    rest = (1 - top) / (n - 1) if n > 1 else 0.0
    probs = {o: round(top if i == idx else rest, 6) for i, o in enumerate(options)}
    return options[idx], round(top, 4), probs


def jev_answers(body):
    state = json.dumps(body.get("state"), sort_keys=True, ensure_ascii=False)
    answers = {}
    questions = body.get("questions", {})
    # Make most (not all) stub answers internally consistent, like a real classifier would:
    # praise/request/unclear usually get no_problem; complaints usually get at least "annoyance".
    intent = None
    if "intent" in questions and questions["intent"].get("type") == "choice":
        intent = _choice_answer((body.get("model"), "intent", state), list(questions["intent"]["criteria"]))[0]
    for qid, q in questions.items():
        seed = (body.get("model"), qid, state)
        if q.get("type") == "choice":
            opts = list(q["criteria"].keys())
            forced = None
            if qid == "severity" and intent is not None and _h(seed, "consistent") % 10 < 8:
                pick = opts[_h(seed, "pick") % len(opts)]
                if intent in ("praise", "request", "unclear"):
                    forced = "no_problem"
                elif intent == "complaint" and pick == "no_problem":
                    forced = "annoyance"
            choice, conf, probs = _choice_answer(seed, opts, forced)
            answers[qid] = {"type": "choice", "choice": choice, "confidence": conf, "probabilities": probs}
        elif q.get("type") == "score":
            levels = q["criteria"]
            _, conf, probs = _choice_answer(seed, [str(i) for i in range(len(levels))])
            score = sum(int(k) * v for k, v in probs.items())
            answers[qid] = {"type": "score", "score": round(score, 4), "confidence": conf,
                            "legend": {str(i): (lv if isinstance(lv, str) else json.dumps(lv)) for i, lv in enumerate(levels)},
                            "probabilities": probs}
        elif q.get("type") == "noul":
            answers[qid] = {"type": "noul", "noul": round((_h(seed, "noul") % 60) / 100.0, 2)}
    return answers


def decisions_answers(body):
    """Decisions request -> answers list, reusing the Jev stub on the equivalent typed questions."""
    qs = {}
    for q in body.get("questions", []):
        if q["type"] == "choice":
            qs[q["name"]] = {"type": "choice", "criteria": {c["value"]: c["description"] for c in q["choices"]}}
        elif q["type"] == "score":
            qs[q["name"]] = {"type": "score", "criteria": [lv["description"] for lv in q["levels"]]}
        elif q["type"] == "predicate":
            qs[q["name"]] = {"type": "noul", "criteria": {}}
    out = []
    for name, a in jev_answers({"model": body.get("model"), "state": body.get("input"), "questions": qs}).items():
        if a["type"] == "choice":
            out.append({"type": "choice", "name": name, "choice": a["choice"], "confidence": a["confidence"],
                        "probabilities": [{"value": v, "probability": p} for v, p in a["probabilities"].items()]})
        elif a["type"] == "score":
            out.append({"type": "score", "name": name, "score": a["score"], "confidence": a["confidence"],
                        "probabilities": [{"value": int(v), "label": f"level_{v}", "probability": p}
                                          for v, p in a["probabilities"].items()]})
        else:
            out.append({"type": "predicate", "name": name, "probability": a["noul"]})
    return out


def instance(schema, seed, path="$", context=""):
    """Deterministic JSON instance of a (simple) JSON schema."""
    if "enum" in schema:
        vals = schema["enum"]
        if path.endswith(".cited_reviews[]"):
            return vals[0]
        return vals[_h(seed, path) % len(vals)]
    t = schema.get("type")
    if t == "object":
        obj = {k: instance(v, seed, f"{path}.{k}", context) for k, v in schema.get("properties", {}).items()}
        if "recommended_area" in obj and isinstance(obj.get("alternatives"), list):
            # keep the stub memo internally consistent: alternatives are the other areas
            areas = schema["properties"]["recommended_area"]["enum"]
            obj["alternatives"] = [{"area": a, "why_not_first": "Stub text (offline plumbing test)."}
                                   for a in areas if a != obj["recommended_area"]]
        return obj
    if t == "array":
        items = schema.get("items", {})
        id_enum = items.get("properties", {}).get("id", {}).get("enum") if items.get("type") == "object" else None
        if id_enum:
            out = []
            for alias in id_enum:
                obj = instance(items, f"{seed}|{alias}", f"{path}[]", context)
                obj["id"] = alias
                out.append(obj)
            return out
        area_enum = items.get("properties", {}).get("area", {}).get("enum") if items.get("type") == "object" else None
        if area_enum:
            out = []
            for area in area_enum[1:]:
                obj = instance(items, f"{seed}|{area}", f"{path}[]", context)
                obj["area"] = area
                out.append(obj)
            return out
        if path.endswith("misfit_quotes"):
            return []
        n = 1 if "enum" in items else 2
        return [instance(items, f"{seed}|{i}", f"{path}[]", context) for i in range(n)]
    if t == "string":
        if path.endswith("recommendation"):
            return "Stub memo text (offline plumbing test, not a finding), citing {C01} and {C02}." \
                if "{C01}" in context and "{C02}" in context else "Stub memo text (offline plumbing test)."
        if path.endswith(".name"):
            return "Stub issue name"
        return "Stub text from the offline test server; not a model output."
    if t == "integer":
        return 1
    if t == "number":
        return 0.0
    if t == "boolean":
        return _h(seed, path) % 4 == 0
    return None


class _Handler(BaseHTTPRequestHandler):
    server_version = "insight-stub/1"

    def log_message(self, fmt, *args):  # keep test output quiet
        pass

    def _send(self, status, payload, headers=None, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": {"message": "invalid JSON"}})
        srv = self.server.stub
        provider = {"/v1/systemone": "typesafe", "/v1/responses": "openai", "/v1/messages": "anthropic",
                    "/v1/decisions": "openai_decisions"}.get(self.path)
        if provider is None:
            return self._send(404, {"error": {"message": f"unknown path {self.path}"}})
        n = srv.count(provider)
        fault = srv.faults.get(provider, {}).get(n)
        srv.log.append({"provider": provider, "n": n, "fault": fault, "model": body.get("model")})
        if srv.capture_bodies:
            srv.bodies.append(raw.decode("utf-8", "replace"))
        if fault == "429":
            return self._send(429, {"error": {"type": "rate_limit_error", "message": "stub rate limit"}},
                              {"retry-after": "0"})
        if fault == "500":
            return self._send(500, {"error": {"type": "api_error", "message": "stub server error"}})
        if fault in ("timeout", "slow"):  # "timeout" exceeds a short client timeout; "slow" just delays
            time.sleep(srv.timeout_sleep)
        tokens_in = max(1, len(raw) // 4)
        if provider == "typesafe":
            answers = jev_answers(body)
            if fault == "malformed" and answers:
                answers.pop(sorted(answers)[0])
            return self._send(200, {"model": body.get("model"), "answers": answers,
                                    "usage": {"input_tokens": tokens_in, "output_tokens": 8 * len(answers)}},
                              {"x-typesafe-request-id": f"stub-ts-{n}"})
        if provider == "openai_decisions":
            answers = decisions_answers(body)
            if fault == "malformed" and answers:
                answers.pop(0)
            return self._send(200, {"id": f"dec_stub_{n}", "object": "decision", "model": body.get("model"),
                                    "answers": answers, "usage": {"input_tokens": tokens_in, "output_tokens": 0}},
                              {"x-request-id": f"stub-dec-{n}"})
        if provider == "openai":
            schema = body["text"]["format"]["schema"]
            data = instance(schema, body.get("input", ""), context=body.get("input", ""))
            text = json.dumps(data) if fault != "malformed" else '{"results": [ this is not json'
            status, incomplete = "completed", None
            if fault == "truncated":
                status, incomplete, text = "incomplete", {"reason": "max_output_tokens"}, text[: len(text) // 2]
            out_tokens = max(1, len(text) // 4)
            resp = {
                "id": f"resp_stub_{n}", "object": "response", "created_at": int(time.time()), "status": status,
                "model": body.get("model"), "error": None, "incomplete_details": incomplete,
                "instructions": None, "metadata": {}, "parallel_tool_calls": True, "temperature": None,
                "tool_choice": "auto", "tools": [], "top_p": None,
                "output": [{"type": "message", "id": f"msg_stub_{n}", "status": "completed", "role": "assistant",
                            "content": [{"type": "output_text", "text": text, "annotations": []}]}],
                "usage": {"input_tokens": tokens_in, "input_tokens_details": {"cached_tokens": 0},
                          "output_tokens": out_tokens, "output_tokens_details": {"reasoning_tokens": 0},
                          "total_tokens": tokens_in + out_tokens},
            }
            return self._send(200, resp, {"x-request-id": f"stub-oa-{n}"})
        schema = body["output_config"]["format"]["schema"]
        user = body["messages"][0]["content"] if body.get("messages") else ""
        data = instance(schema, user, context=user)
        text = json.dumps(data) if fault != "malformed" else "not json"
        stop = "max_tokens" if fault == "truncated" else "end_turn"
        resp = {"id": f"msg_stub_{n}", "type": "message", "role": "assistant", "model": body.get("model"),
                "content": [{"type": "text", "text": text}], "stop_reason": stop, "stop_sequence": None,
                "usage": {"input_tokens": tokens_in, "output_tokens": max(1, len(text) // 4),
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}
        return self._send(200, resp, {"request-id": f"stub-an-{n}"})


class StubServer:
    def __init__(self, faults=None, timeout_sleep=3.0):
        self.faults = {p: {int(k): v for k, v in d.items()} for p, d in (faults or {}).items()}
        self.timeout_sleep = timeout_sleep
        self._counts = {}
        self._lock = threading.Lock()
        self.log = []
        self.bodies = []
        self.capture_bodies = False
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.stub = self
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="stub-server", daemon=True)

    def count(self, provider):
        with self._lock:
            self._counts[provider] = self._counts.get(provider, 0) + 1
            return self._counts[provider]

    @property
    def base(self):
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def base_urls(self):
        return {"typesafe": self.base, "openai": self.base + "/v1", "anthropic": self.base,
                "openai_decisions": self.base + "/v1"}

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def parse_faults(spec: str) -> dict:
    """'typesafe:3=429,openai:2=malformed' -> {'typesafe': {3: '429'}, 'openai': {2: 'malformed'}}."""
    out = {}
    for part in filter(None, (spec or "").split(",")):
        left, kind = part.split("=")
        provider, n = left.split(":")
        lo, _, hi = n.partition("-")  # "typesafe:1-40=500" covers requests 1..40
        for i in range(int(lo), int(hi or lo) + 1):
            out.setdefault(provider.strip(), {})[i] = kind.strip()
    return out
