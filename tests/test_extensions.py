"""Tests for the 200k-scope extensions: Claude Pro adapter, tiered rates, project cap, analysis, web database + API."""

import csv
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["INSIGHT_NO_DOTENV"] = "1"

from insight import cli  # noqa: E402
from insight.providers import ProviderError, Rates  # noqa: E402
from insight.providers.claude_code import ClaudeCodeProvider  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_small.csv"
SCHEMA = {"type": "object", "properties": {"topic": {"type": "string", "enum": ["playback", "other"]}},
          "required": ["topic"], "additionalProperties": False}


def stub_provider():
    return ClaudeCodeProvider("claude_code", "stub-haiku", "n/a", None, {"stub": True, "timeout_s": 60}, paid=False)


class TestClaudeCodeAdapter(unittest.TestCase):
    def test_structured_output_usage_and_billing(self):
        res = stub_provider().call({"system": "label", "user": "<review>crash</review>", "schema": SCHEMA,
                                    "max_output_tokens": 100})
        self.assertIn(res.data["topic"], ("playback", "other"))
        self.assertEqual(res.billing, "subscription")
        self.assertEqual(res.service_tier, "subscription")
        self.assertTrue(res.provider_request_id.startswith("cc-"))
        self.assertGreater(res.usage["input_tokens"], 0)
        self.assertEqual(res.model_reported, "stub-haiku")

    def test_usage_limit_is_systemic_and_garbage_is_transient(self):
        for fault, kind in (("limit", "systemic"), ("garbage", "transient"), ("error", "invalid_output")):
            os.environ["STUB_CLAUDE_FAULT"] = fault
            try:
                with self.assertRaises(ProviderError) as cm:
                    stub_provider().call({"system": "s", "user": "u", "schema": SCHEMA, "max_output_tokens": 10})
                self.assertEqual(cm.exception.kind, kind, fault)
            finally:
                os.environ.pop("STUB_CLAUDE_FAULT", None)

    def test_api_key_is_stripped_from_the_cli_environment(self):
        from insight.providers.claude_code import _child_env
        os.environ["ANTHROPIC_API_KEY"] = "sk-should-not-leak"
        try:
            self.assertNotIn("ANTHROPIC_API_KEY", _child_env(100))
            self.assertEqual(_child_env(100)["CLAUDE_CODE_MAX_OUTPUT_TOKENS"], "100")
        finally:
            os.environ.pop("ANTHROPIC_API_KEY")


class TestTieredRates(unittest.TestCase):
    def test_flex_cache_write_and_subscription(self):
        r = Rates()
        u = {"input_tokens": 1_000_000, "cached_input_tokens": 400_000, "cache_write_tokens": 100_000, "output_tokens": 200_000}
        std = r.cost("openai", "gpt-6-luna", u, "standard")
        self.assertAlmostEqual(std, 0.5 * 0.10 + 0.4 * 0.01 + 0.1 * 0.125 + 0.2 * 0.50)
        self.assertAlmostEqual(r.cost("openai", "gpt-6-luna", u, "flex"), std / 2)
        self.assertEqual(r.cost("claude_code", "sonnet", u, "subscription"), 0.0)
        self.assertAlmostEqual(r.api_equivalent("claude-haiku-5-5-20260915", {"input_tokens": 1_000_000, "output_tokens": 0}), 0.10)
        self.assertGreater(r.worst_case("openai", "gpt-6-luna", 1000, 100), r.cost("openai", "gpt-6-luna",
                           {"input_tokens": 1000, "output_tokens": 100}, "flex"))


class TestProjectCap(unittest.TestCase):
    def test_spend_is_summed_across_runs_and_the_cap_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            runs = Path(d) / "runs" / "old-run"
            runs.mkdir(parents=True)
            con = sqlite3.connect(runs / "state.sqlite")
            con.execute("CREATE TABLE calls (request_id TEXT, model TEXT, outcome TEXT, cost_usd REAL, reserved_usd REAL, billing TEXT)")
            con.executemany("INSERT INTO calls VALUES (?,?,?,?,?,?)", [
                ("a", "gpt-6-luna", "succeeded", 9.40, 0.5, "api"), ("b", "stub-gpt-6-luna", "succeeded", 5.0, 0, "api"),
                ("c", "sonnet", "succeeded", 0.0, 0, "subscription"), ("d", "gpt-6-luna", "unknown", None, 0.2, "api")])
            con.commit()
            con.close()
            total, per_run = cli.project_spend(runs_root=Path(d) / "runs")
            self.assertAlmostEqual(total, 9.60)
            os.environ.update({"INSIGHT_RUNS_ROOT": str(Path(d) / "runs"), "OPENAI_API_KEY": "sk-test-not-used"})
            try:
                code, out = _run("run", "--input", FIXTURE, "--run-dir", Path(d) / "runs" / "new", "--allow-paid", "--budget-usd", "0.5",
                                 "--set", "verify.provider=openai", "--set", "group.provider=openai", "--set", "memo.provider=openai",
                                 "--set", "enrich.fallback2.enabled=false", "--set", "verify.model=gpt-6-luna",
                                 "--set", "group.model=gpt-6-luna", "--set", "memo.model=gpt-6-luna")
            finally:
                os.environ.pop("INSIGHT_RUNS_ROOT")
                os.environ.pop("OPENAI_API_KEY")
            self.assertEqual(code, 2, out)
            self.assertIn("project spending cap", out)
            os.environ.update({"INSIGHT_RUNS_ROOT": str(Path(d) / "runs"), "OPENAI_API_KEY": "sk-test-not-used"})
            try:  # live runs outside the runs root are refused (their spend would escape the cap) ...
                code, out = _run("run", "--input", FIXTURE, "--run-dir", Path(d) / "elsewhere", "--allow-paid",
                                 "--budget-usd", "0.5", "--stages", "ingest,enrich", "--set", "enrich.fallback2.enabled=false")
                self.assertEqual(code, 2, out)
                self.assertIn("must be under", out)
                (Path(d) / "runs" / "broken").mkdir()  # ... and an unreadable run database fails closed, never $0
                (Path(d) / "runs" / "broken" / "state.sqlite").write_bytes(b"not a database")
                with self.assertRaises(RuntimeError):
                    cli.project_spend(runs_root=Path(d) / "runs")
            finally:
                os.environ.pop("INSIGHT_RUNS_ROOT")
                os.environ.pop("OPENAI_API_KEY")


def _run(*argv):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main([str(a) for a in argv])
    return code, buf.getvalue()


class TestAnalysisWebAndApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rd = Path(cls.tmp.name) / "run"
        code, out = _run("run", "--input", FIXTURE, "--run-dir", cls.rd, "--offline-stub")
        assert code == 0, out

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_analysis_outputs_have_denominators(self):
        with open(self.rd / "analysis" / "trends_monthly.csv", encoding="utf-8") as f:
            trends = list(csv.DictReader(f))
        self.assertTrue(all(int(t["reviews"]) >= int(t["complaints"]) for t in trends))
        ov = json.loads((self.rd / "analysis" / "overview.json").read_text())
        self.assertEqual(ov["completed"] + ov["quarantined"], 12)

    def test_trace_command(self):
        code, out = _run("trace", "--run-dir", self.rd, "--auto", "--offline-stub")
        self.assertEqual(code, 0, out)
        self.assertIn("Source row", out)

    def test_load_db_and_api_round_trip(self):
        sys.path.insert(0, str(ROOT / "web"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("load_db", ROOT / "web" / "load_db.py")
        load_db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load_db)
        db = Path(self.tmp.name) / "dash.db"
        check = load_db.load(self.rd, f"sqlite:///{db}", input_csv=FIXTURE, log=lambda *a: None)
        self.assertTrue(check["sql_ranking_equals_saved_ok"] and check["claims_equal_sql_ok"])
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi not installed")
        os.environ["DATABASE_URL"] = f"sqlite:///{db}"
        try:
            spec = importlib.util.spec_from_file_location("dash_api", ROOT / "web" / "api" / "index.py")
            api = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(api)
            c = TestClient(api.app)
            self.assertEqual(c.get("/api/overview").json()["counts"]["rows"], 12)
            self.assertTrue(c.get("/api/consistency").json()["ranking_matches"])
            self.assertTrue(c.get("/api/recommendation").json()["all_claims_match_database"])
            rid = c.get("/api/reviews?limit=1").json()["reviews"][0]["review_id"]
            self.assertEqual(c.get(f"/api/reviews/{rid}").status_code, 200)
            self.assertEqual(c.get("/api/reviews/not-a-real-id").status_code, 404)
        finally:
            os.environ.pop("DATABASE_URL")


if __name__ == "__main__":
    unittest.main()


class TestDecisionsAdapter(unittest.TestCase):
    def test_question_translation_round_trip(self):
        from insight import prompts
        from insight.providers.openai_decisions import from_decisions_answers, to_decisions_questions
        req = prompts.jev_request(prompts.load_jev_questions(), "Charged twice. Support ignored me.",
                                  ["Charged twice.", "Support ignored me."])
        qs = {q["name"]: q for q in to_decisions_questions(req["questions"])}
        self.assertEqual(set(qs), {"issue", "intent", "severity", "sentiment", "unclear", "evidence"})
        self.assertEqual(qs["intent"]["type"], "choice")
        self.assertEqual([c["value"] for c in qs["evidence"]["choices"]], ["s1", "s2"])
        self.assertEqual(qs["sentiment"]["type"], "score")
        self.assertEqual(len(qs["sentiment"]["levels"]), 5)
        self.assertEqual(qs["unclear"]["type"], "predicate")
        answers, refused = from_decisions_answers([
            {"type": "choice", "name": "intent", "choice": "complaint", "confidence": 0.9,
             "probabilities": [{"value": "complaint", "probability": 0.9}, {"value": "praise", "probability": 0.1}]},
            {"type": "score", "name": "sentiment", "score": 0.4, "confidence": 0.7, "probabilities": []},
            {"type": "predicate", "name": "unclear", "probability": 0.05},
            {"type": "refusal", "name": "issue"}])
        self.assertEqual(answers["intent"]["choice"], "complaint")
        self.assertEqual(answers["intent"]["probabilities"]["praise"], 0.1)
        self.assertEqual(answers["sentiment"]["score"], 0.4)
        self.assertEqual(answers["unclear"], {"type": "noul", "noul": 0.05})
        self.assertEqual(refused, ["issue"])
        self.assertNotIn("issue", answers)

    def test_insufficient_quota_is_systemic(self):
        import httpx2
        import openai
        from insight.providers import ProviderError
        from insight.providers.openai_responses import raise_mapped
        req = httpx2.Request("POST", "https://api.openai.com/v1/decisions")
        def err(code):
            body = {"error": {"message": "x", "type": "insufficient_quota" if code else "rate_limit", "code": code}}
            return openai.RateLimitError("x", response=httpx2.Response(429, request=req, json=body), body=body["error"])
        for code in ("insufficient_quota", "credit_balance_exhausted"):  # the second is what the live API returned
            with self.assertRaises(ProviderError) as cm:
                raise_mapped(openai, err(code))
            self.assertEqual(cm.exception.kind, "systemic")
        with self.assertRaises(ProviderError) as cm:
            raise_mapped(openai, err(None))
        self.assertEqual(cm.exception.kind, "transient")
