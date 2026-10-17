"""Quote-support evaluation (evals/quote_support.py): blind items, validation, caching and the summary tables."""

import contextlib
import csv
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["INSIGHT_NO_DOTENV"] = "1"

from insight import cli  # noqa: E402
from insight.providers import Result  # noqa: E402
from insight.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_small.csv"


def load_qs():
    spec = importlib.util.spec_from_file_location("quote_support", ROOT / "evals" / "quote_support.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeJudge:
    """Answers every item: 'not_supported' topic when the quote is shorter than 15 characters, else supported."""

    def __init__(self):
        self.requests = []

    def call(self, request, timeout=None):
        self.requests.append(request)
        items = re.findall(r'<item id="(q\d+)">.*?<quote>(.*?)</quote>', request["user"], flags=re.S)
        res = [{"id": i, "topic": "not_supported" if len(q) < 15 else "supported", "intent": "supported",
                "severity": "partial", "quote_choice": "best", "reason": "fake"} for i, q in items]
        return Result(data={"results": res}, usage={"input_tokens": 100, "cached_input_tokens": 0,
                                                    "cache_write_tokens": 0, "output_tokens": 50, "reasoning_tokens": 0},
                      provider_request_id="cc-fake", model_reported="claude-haiku-4-5-20251001",
                      service_tier="subscription", billing="subscription")


class TestQuoteSupport(unittest.TestCase):
    def test_blind_items_summary_and_cache(self):
        qs = load_qs()
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d) / "run"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["run", "--input", str(FIXTURE), "--run-dir", str(rd), "--offline-stub"]), 0)
            store = Store(rd)
            cfg = cli._load_cfg_for_run(type("A", (), {"run_dir": str(rd), "config": None, "offline_stub": True})())
            done = store.results(cfg.label_config(), status="completed")[:4]
            labels = Path(d) / "labels.csv"
            with open(labels, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["review_id", "review_text", "topic", "intent", "severity", "evidence_quote"])
                w.writeheader()
                for p in done:
                    text = store.review(p["review_id"])["review_text"]
                    w.writerow({"review_id": p["review_id"], "review_text": text, "topic": p["topic"],
                                "intent": p["intent"], "severity": str(p["severity"]), "evidence_quote": p["evidence_quote"]})
            fake = FakeJudge()
            out = Path(d) / "qs"
            argv = ["--run-dir", str(rd), "--labelled", f"golden={labels}", "--sample", "3", "--out-dir", str(out),
                    "--offline-stub", "--workers", "1"]
            with mock.patch.object(qs.ProviderRegistry, "get", return_value=fake), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(qs.main(argv), 0)
            # the judge gets one item per review, with the run's own labels only: no human labels, no review IDs
            self.assertTrue(fake.requests)
            items = [json.loads(x) for x in (out / "items.jsonl").read_text().splitlines()]
            self.assertEqual(len(items), 4 + 3)
            self.assertEqual({i["who"] for i in items}, {"model"})
            sent = sum(len(re.findall(r'<item id="q\d+">', req["user"])) for req in fake.requests)
            self.assertEqual(sent, len({i["key"] for i in items}))  # identical items are sent once
            for req in fake.requests:
                self.assertNotIn("human", req["user"].lower())
                for p in done:
                    self.assertNotIn(p["review_id"], req["user"])
            summary = json.loads((out / "summary.json").read_text())
            self.assertNotIn("golden/human", summary["by_set"])
            gm = summary["by_set"]["golden/model"]
            self.assertEqual(gm["items"], 4)
            self.assertEqual(gm["exact_substring"], 4)
            self.assertEqual(gm["same_sentence_as_human"], 4)  # the labels file copied the model's own quotes
            self.assertEqual(gm["severity"]["partial"], 1.0)
            self.assertEqual(summary["by_set"]["final_sample/model"]["items"], 3)
            self.assertEqual(summary["meta"]["billed_usd"], 0.0)
            self.assertIn("Every model quote the judge did not accept", (out / "report.md").read_text())
            # a rerun with unchanged items sends nothing new
            n = len(fake.requests)
            with mock.patch.object(qs.ProviderRegistry, "get", return_value=fake), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(qs.main(argv), 0)
            self.assertEqual(len(fake.requests), n)

    def test_validation_rejects_missing_or_unknown_ids(self):
        qs = load_qs()
        batch = [{"id": "q0001"}, {"id": "q0002"}]
        ok = {"topic": "supported", "intent": "partial", "severity": "not_supported", "quote_choice": "best", "reason": ""}
        self.assertIsNotNone(qs.valid({"results": [{"id": "q0001", **ok}, {"id": "q0002", **ok}]}, batch))
        self.assertIsNone(qs.valid({"results": [{"id": "q0001", **ok}]}, batch))
        self.assertIsNone(qs.valid({"results": [{"id": "q0001", **ok}, {"id": "q0009", **ok}]}, batch))
        self.assertIsNone(qs.valid({"results": [{"id": "q0001", **ok}, {"id": "q0002", **ok, "topic": "maybe"}]}, batch))

    def test_same_sentence(self):
        qs = load_qs()
        self.assertTrue(qs.same_sentence("The app crashes.", "the app crashes"))
        self.assertTrue(qs.same_sentence("crashes", "The app crashes all the time."))
        self.assertFalse(qs.same_sentence("Love the songs.", "The app crashes."))
        self.assertFalse(qs.same_sentence("", "x"))


if __name__ == "__main__":
    unittest.main()
