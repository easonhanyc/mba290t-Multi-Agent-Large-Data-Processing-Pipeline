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


class TestMemoTraceability(unittest.TestCase):
    """Memo prose numbers carry token IDs, spike bullets list only real increases, golden status is never 'pending'."""

    def _payload(self, lifts):
        from insight import memo
        ranking = [{"issue_id": "billing.premium_only", "complaint_count": 18016, "severity_sum": 52577,
                    "mean_severity": "2.918350", "priority_score": 52577}]
        issues = {"issues": [{"issue_id": "billing.premium_only", "name": "Premium-only restrictions", "evidence": [],
                              "definition": "Features locked to Premium."}]}
        areas = {"areas": [{"area": "billing/support", "decision_option": True, "complaint_count": 20290,
                            "severity_sum": 59146, "share_of_complaints": "0.226042"}]}
        analysis = {"spikes": {"spikes": [{"month": "2023-07", "reviews": 25850, "median_full_month_reviews": 8549,
                                           "largest_increases": lifts}]}}
        return memo.build_payload(ranking, issues, areas, [("Reviews in scope", 200013, "ingestion_report.json")],
                                  1, 1, 10, analysis)

    def _render(self, payload, tokens, data):
        from insight import memo
        meta = {"scope": "test", "run_id": "r", "input": "in.csv", "input_sha256": "0" * 64, "offline_stub": False,
                "mandatory_limitations": []}
        return memo.MemoStage.render(None, data, payload, tokens, meta, "model")

    def test_spike_bullet_lists_only_positive_increases(self):
        payload, tokens, _ = self._payload([
            {"issue_id": "other.general", "pp_difference": 35.976}, {"issue_id": "usability.ads", "pp_difference": 0.04},
            {"issue_id": "billing.price", "pp_difference": -0.011}, {"issue_id": "support.contact", "pp_difference": -0.065}])
        spike = payload["trends_and_robustness"]["spike_months"][0]
        self.assertEqual([l["issue_id"] for l in spike["largest_increases"]], ["other.general"])  # +0.0 pp is not a rise
        data = {"recommended_area": "billing/support", "recommendation": "Premium-only {C02}.", "rationale": ["x"],
                "alternatives": [], "limitations": ["y"], "cited_reviews": []}
        md = self._render(payload, tokens, data)
        self.assertIn("`other.general` +36.0 pp (", md)
        self.assertNotIn("-0.0 pp", md)
        self.assertNotIn("billing.price", md)
        payload, tokens, _ = self._payload([{"issue_id": "billing.price", "pp_difference": -0.011}])
        md = self._render(payload, tokens, data)
        self.assertIn("no issue's share of complaints rose", md)
        self.assertNotIn("largest increases", md)

    def test_prose_numbers_carry_token_ids_and_every_token_is_indexed(self):
        from insight import memo
        payload, tokens, claims = self._payload([{"issue_id": "other.general", "pp_difference": 3.0}])
        data = {"recommended_area": "billing/support",
                "recommendation": "Premium-only restrictions lead with severity sum {C02} across {C01} reviews.",
                "rationale": ["The area totals {A02}."], "alternatives": [],
                "next_quarter_actions": ["Test free-tier controls and watch {C01}."],
                "what_would_change_the_call": ["The spike in {T01} fading."],
                "limitations": ["Only {S01} reviews in scope."], "cited_reviews": []}
        self.assertEqual(memo.validate(data, tokens, []), [])
        md = self._render(payload, tokens, data)
        for text in ("severity sum 52577 (C02) across 18016 (C01) reviews", "totals 59146 (A02)",
                     "watch 18016 (C01)", "spike in 2023-07 (T01)", "Only 200013 (S01) reviews", "## Next-quarter actions",
                     "## What would change this call", "memo_tokens.csv"):
            self.assertIn(text, md)
        index = {r["token_id"]: r for r in memo.token_index(payload, tokens)}
        self.assertEqual(set(index), set(tokens))
        self.assertEqual(index["C02"]["source"], "claims.csv (from ranking.csv)")
        self.assertEqual(index["A02"]["source"], "area_rollup.json")
        self.assertEqual(index["S01"]["source"], "ingestion_report.json")
        self.assertEqual(index["T01"]["source"], "analysis/spike_months.json")
        self.assertEqual({c["claim_id"] for c in claims}, {k for k in tokens if k.startswith("C")})
        bad = dict(data, next_quarter_actions=["Ship it in Q1."])
        self.assertTrue(any("next_quarter_actions[0]" in p and "digit" in p for p in memo.validate(bad, tokens, [])))
        req = memo.memo_request(payload, [], 100)
        self.assertTrue({"next_quarter_actions", "what_would_change_the_call"} <= set(req["schema"]["required"]))

    def test_golden_limitation_is_read_from_results_never_pending(self):
        from insight import memo
        lines = ["5 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished; the golden-set "
                 "comparison (human labels) is still pending."]
        self.assertEqual(memo.mandatory_limitations(lines, None),
                         ["5 completed records are flagged needs_review, 0 are quarantined and 0 are unfinished."])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "results.json"
            path.write_text(json.dumps({"status": "ready", "cases": 50, "label_config": "lc-1",
                                        "agreement": {"topic": 0.76, "intent": 0.74, "severity": 0.76}}))
            self.assertIsNone(memo.golden_status("another-config", path))
            golden = memo.golden_status("lc-1", path)
            out = memo.mandatory_limitations(lines, golden)
        self.assertFalse(any("pending" in x for x in out))
        self.assertIn("on 50 human-labelled reviews", out[-1])
        self.assertIn("topic 76%, intent 74% and severity 76%", out[-1])


class TestMemoTokensAndVerifiedTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rd = Path(cls.tmp.name) / "run"
        code, out = _run("run", "--input", FIXTURE, "--run-dir", cls.rd, "--offline-stub")
        assert code == 0, out

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_token_id_in_memo_is_in_memo_tokens_csv(self):
        import re
        md = (self.rd / "memo.md").read_text(encoding="utf-8")
        with open(self.rd / "memo_tokens.csv", encoding="utf-8") as f:
            index = {r["token_id"]: r["value"] for r in csv.DictReader(f)}
        cited = re.findall(r"(\S+) \(([CAST]\d{2,3})\)", md)
        self.assertTrue(cited)
        for value, tid in cited:
            self.assertIn(tid, index)
            self.assertTrue(value.endswith(index[tid].split()[-1]), (value, tid, index[tid]))
        self.assertNotIn("pending", md.split("## Limitations")[1])

    def test_trace_of_a_verified_review_shows_the_verifier_step(self):
        from insight.store import Store
        store = Store(self.rd)
        verified = [r[0] for r in store.conn.execute("SELECT review_id FROM verifications WHERE status='completed'")]
        self.assertTrue(verified)
        code, out = _run("trace", "--run-dir", self.rd, "--review-id", verified[0], "--auto", "--offline-stub")
        self.assertEqual(code, 0, out)
        self.assertIn("A. Traced review (", out)
        self.assertIn("| Field | Enricher (record) | Verifier (independent) | Code comparison |", out)
        self.assertIn("B. An ambiguous or failed case", out)


class TestMakeAnalysisSubset(unittest.TestCase):
    def test_out_outside_the_repo_does_not_crash(self):
        import contextlib
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location("make_analysis_subset", ROOT / "scripts" / "make_analysis_subset.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            full = Path(d) / "full.csv"
            with open(full, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(mod.FIELDS)
                for i in range(6):
                    w.writerow([f"id-{i}", "" if i == 5 else f"text {i}", "3", "0", "1.0", "2023-01-01 00:00:00"])
            out = Path(d) / "elsewhere" / "subset.csv"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                mod.main(["--full", str(full), "--n", "3", "--out", str(out)])
            manifest = json.loads(out.with_suffix(".manifest.json").read_text())
        self.assertEqual(manifest["file"], str(out.resolve()))
        self.assertEqual(manifest["rows"], 4)  # 3 sampled + 1 empty-text row
        self.assertIn("--out", manifest["command"])
