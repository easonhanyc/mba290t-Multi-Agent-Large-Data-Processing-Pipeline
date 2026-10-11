"""Offline stand-in for `claude -p --output-format json --json-schema ...` (tests and offline runs only).

Answers deterministically from the JSON schema with insight.stub.instance; reports the model as
stub-<alias> and plausible token counts. STUB_CLAUDE_FAULT=limit|error|garbage forces a failure path.
Never used in a live run (the registry selects it only under --offline-stub).
"""

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from insight.stub import instance  # noqa: E402


def main(argv):
    opts, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            opts[a] = argv[i + 1]
            i += 2
        else:
            opts[a] = True
            i += 1
    prompt = sys.stdin.read()
    model = str(opts.get("--model", "sonnet"))
    model = model if model.startswith("stub-") else "stub-" + model
    sid = str(uuid.uuid4())
    fault = os.environ.get("STUB_CLAUDE_FAULT", "")
    base = {"type": "result", "session_id": sid, "uuid": str(uuid.uuid4()), "num_turns": 1, "duration_api_ms": 5,
            "total_cost_usd": 0, "stop_reason": "end_turn"}
    if fault == "garbage":
        print("not json at all")
        return 1
    if fault in ("limit", "error"):
        msg = "Claude AI usage limit reached|1760000000" if fault == "limit" else "Something odd happened"
        print(json.dumps({**base, "is_error": True, "subtype": "success", "result": msg, "usage": {}, "modelUsage": {}}))
        return 1
    schema = json.loads(opts.get("--json-schema", "{}"))
    seed = hashlib.sha256((prompt + model).encode()).hexdigest()
    data = instance(schema, seed, context=prompt)
    n_in = len(prompt) // 4 + len(str(opts.get("--system-prompt", ""))) // 4
    n_out = len(json.dumps(data)) // 4
    print(json.dumps({**base, "is_error": False, "subtype": "success", "result": json.dumps(data),
                      "structured_output": data,
                      "usage": {"input_tokens": n_in, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                                "output_tokens": n_out, "output_tokens_details": {"thinking_tokens": 0}},
                      "modelUsage": {model: {"inputTokens": n_in, "outputTokens": n_out, "cacheReadInputTokens": 0,
                                             "cacheCreationInputTokens": 0, "costUSD": 0}}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
