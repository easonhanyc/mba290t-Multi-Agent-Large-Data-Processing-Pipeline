"""Tests for the second-review pipeline fixes: memo token sources, positive-only spike lists, the premium-only
sensitivity and unallocated-complaint limitations, prompt rules, calculator provenance and invalid-output
reconciliation, manifest paths under a symlinked dataset folder, and the closed run lock file."""

import contextlib
import csv
import fcntl
import gc
import gzip
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
import warnings
from pathlib import Path

os.environ["INSIGHT_NO_DOTENV"] = "1"

from insight import analysis, cli, memo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_small.csv"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def period_doc():
    areas = ("access/onboarding", "billing/support", "general/unspecified", "playback/performance", "usability")
    shares = {"2022": {"access/onboarding": 0.009, "billing/support": 0.045, "general/unspecified": 0.025,
                       "playback/performance": 0.096, "usability": 0.105},
              "2023": {"access/onboarding": 0.018, "billing/support": 0.154, "general/unspecified": 0.217,
                       "playback/performance": 0.047, "usability": 0.113}}
    periods = {f"{y} Jun-Oct": {"reviews": 1000, "complaint_share": 0.4,
                                "areas": {a: {"share_of_reviews": shares[y][a]} for a in areas}} for y in ("2022", "2023")}
    change = {a: {"2022": shares["2022"][a], "2023": shares["2023"][a],
                  "pp_change": round((shares["2023"][a] - shares["2022"][a]) * 100, 3)} for a in areas}
    return {"periods": periods, "change_in_share_of_reviews": change, "method": "m",
            "largest_increase": {"among_the_four_decision_areas": "billing/support", "among_all_areas": "general/unspecified"}}


def sensitivity_doc():
    return {"issue_id": "billing.premium_only", "area": "billing/support", "issue_records": 100, "issue_severity_sum": 300,
            "decision_area_severity_sums": {"billing/support": 600, "usability": 550, "playback/performance": 500,
                                            "access/onboarding": 100},
            "decision_area_order": ["billing/support", "usability", "playback/performance", "access/onboarding"],
            "without_payment_word": {"words": ["premium", "pay/paid/paying", "free"], "records": 40, "severity_sum": 120,
                                     "billing_support_severity_sum_without_them": 480,
                                     "decision_area_order_without_them": ["usability", "playback/performance",
                                                                          "billing/support", "access/onboarding"],
                                     "decision_areas_above_billing_support_without_them": ["usability",
                                                                                            "playback/performance"]},
            "interpretation": "Upper bound, not a relabelling."}


def build(analysis_doc):
    ranking = [{"issue_id": "billing.premium_only", "complaint_count": 100, "severity_sum": 300,
                "mean_severity": "3.000000", "priority_score": 300}]
    issues = {"issues": [{"issue_id": "billing.premium_only", "name": "Premium-only restrictions", "evidence": []}]}
    areas = {"areas": [
        {"area": "billing/support", "decision_option": True, "complaint_count": 200, "severity_sum": 600,
         "share_of_complaints": "0.250000"},
        {"area": "usability", "decision_option": True, "complaint_count": 220, "severity_sum": 550,
         "share_of_complaints": "0.275000"},
        {"area": "playback/performance", "decision_option": True, "complaint_count": 150, "severity_sum": 500,
         "share_of_complaints": "0.187500"},
        {"area": "general/unspecified", "decision_option": False, "complaint_count": 200, "severity_sum": 400,
         "share_of_complaints": "0.250000"},
        {"area": "access/onboarding", "decision_option": True, "complaint_count": 30, "severity_sum": 100,
         "share_of_complaints": "0.037500"}]}
    return memo.build_payload(ranking, issues, areas, [("Reviews in scope", 2000, "ingestion_report.json")],
                              1, 1, 10, analysis_doc)


def render(payload, tokens, data=None):
    data = data or {"recommended_area": "billing/support", "recommendation": "Premium-only {C02}.", "rationale": ["x"],
                    "alternatives": [], "limitations": ["Model limitation."], "cited_reviews": []}
    meta = {"scope": "test", "run_id": "r", "input": "in.csv", "input_sha256": "0" * 64, "offline_stub": False,
            "mandatory_limitations": ["Mandatory limitation."]}
    return memo.MemoStage.render(None, data, payload, tokens, meta, "model")


class TestMemoTokenSources(unittest.TestCase):
    def test_period_comparison_tokens_keep_their_source_file(self):
        payload, tokens, _ = build({"period_comparison": period_doc()})
        index = {r["token_id"]: r for r in memo.token_index(payload, tokens)}
        self.assertEqual(set(index), set(tokens))
        period = [r for r in index.values() if ".period_comparison." in r["measure"]]
        self.assertTrue(any("areas[billing/support].change_pp" in r["measure"] for r in period))
        for r in period:  # the nested "areas" key must not re-map to area_rollup.json
            self.assertEqual(r["source"], "analysis/period_comparison.json", r)
        self.assertEqual(index["A02"]["source"], "area_rollup.json")
        self.assertEqual(index["C02"]["source"], "claims.csv (from ranking.csv)")

    def test_trend_note_lists_non_decision_areas_with_tokens(self):
        payload, tokens, _ = build({"period_comparison": period_doc()})
        pc = payload["trends_and_robustness"]["period_comparison"]
        self.assertEqual([a["area"] for a in pc["areas"]],
                         ["access/onboarding", "billing/support", "playback/performance", "usability"])
        self.assertEqual([a["area"] for a in pc["non_decision_areas"]], ["general/unspecified"])
        self.assertEqual(pc["largest_increase_among_the_four_decision_areas"], "billing/support")
        md = render(payload, tokens)
        note = next(line for line in md.splitlines() if line.startswith("Note (code)"))
        self.assertIn("four decision areas only", note)
        self.assertIn("`analysis/period_comparison.json`", note)
        tid = pc["non_decision_areas"][0]["change_pp"]["token"].strip("{}")
        self.assertIn(f"general/unspecified 2.5% (", note)
        self.assertIn(f"+19.2 pp ({tid})", note)


class TestSpikeIncreases(unittest.TestCase):
    def test_shared_helper_drops_zero_and_negative_changes(self):
        self.assertIs(memo.positive_increases, analysis.positive_increases)
        lifts = [{"issue_id": "a", "pp_difference": 36.0}, {"issue_id": "b", "pp_difference": 0.049},
                 {"issue_id": "c", "pp_difference": 0.0}, {"issue_id": "d", "pp_difference": -0.011},
                 {"issue_id": "e", "pp_difference": 0.05}]
        self.assertEqual([l["issue_id"] for l in analysis.positive_increases(lifts)], ["a", "e"])

    def test_spike_months_json_lists_only_positive_increases(self):
        rows, monthly = [], []
        for m, n in (("2023-01", 10), ("2023-02", 10), ("2023-03", 10), ("2023-04", 10), ("2023-05", 40)):
            monthly.append({"month": m, "partial_month": "", "reviews": n})
            for i in range(n):
                if m == "2023-05":
                    issue = "x.up" if i < 20 else "x.flat" if i < 24 else "x.down" if i < 25 else None
                else:
                    issue = "x.flat" if i == 0 else "x.down" if i in (1, 2) else None
                rows.append({"month": m, "complaint": issue is not None, "issue_id": issue or "none.none"})
        sp = analysis.spike_months(rows, monthly)
        self.assertEqual([s["month"] for s in sp["spikes"]], ["2023-05"])
        self.assertEqual([l["issue_id"] for l in sp["spikes"][0]["largest_increases"]], ["x.up"])
        self.assertIn("share of reviews", sp["share_definition"])
        self.assertTrue(all(analysis.shown_pp(l["pp_difference"]) > 0 for l in sp["spikes"][0]["largest_increases"]))

    def test_memo_spike_line_says_share_of_reviews(self):
        payload, tokens, _ = build({"spikes": {"spikes": [{"month": "2023-07", "reviews": 25850,
                                                           "median_full_month_reviews": 8549, "largest_increases": [
                                                               {"issue_id": "other.general", "pp_difference": 35.976},
                                                               {"issue_id": "billing.price", "pp_difference": -0.011}]}]}})
        md = render(payload, tokens)
        self.assertIn("largest increases in share of reviews vs other months: `other.general` +36.0 pp (", md)
        self.assertNotIn("billing.price", md)
        self.assertNotIn("share of complaints vs other months", md)


class FakeStore:
    def __init__(self, records):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE results (review_id TEXT, label_config TEXT, status TEXT, topic TEXT, subtopic TEXT)")
        self.conn.execute("CREATE TABLE reviews (review_id TEXT, review_text TEXT, duplicate_id INTEGER)")
        for rid, topic, subtopic, text in records:
            self.conn.execute("INSERT INTO results VALUES (?, 'lc', 'completed', ?, ?)", (rid, topic, subtopic))
            self.conn.execute("INSERT INTO reviews VALUES (?, ?, 0)", (rid, text))


class TestPremiumOnlySensitivity(unittest.TestCase):
    def test_counts_records_without_a_payment_word_row_weighted(self):
        recs = [("p1", "billing", "premium_only", "Only 6 skips now, and shuffle is forced"),       # no word
                ("p2", "billing", "premium_only", "Only 6 skips now, and shuffle is forced"),       # same text, own row
                ("p3", "billing", "premium_only", "You have to buy PREMIUM to repeat a song"),       # case-insensitive
                ("p4", "billing", "premium_only", "The payment page is fine but I cannot rewind"),   # 'payment' is not 'pay'
                ("p5", "billing", "premium_only", "free users lose the queue"),
                ("p6", "billing", "premium_only", "great app"),                                      # praise: not a complaint
                ("u1", "usability", "ads", "too many ads"),
                ("b1", "playback", "crash", "crashes")]
        sev = {"p1": 3, "p2": 3, "p3": 3, "p4": 2, "p5": 3, "p6": 1, "u1": 7, "b1": 9}
        rows = [{"review_id": rid, "issue_id": f"{t}.{s}", "area": analysis.labels.AREA_OF_TOPIC[t], "severity": sev[rid],
                 "complaint": rid != "p6"} for rid, t, s, _ in recs]
        rollup = {"areas": [{"area": "billing/support", "severity_sum": 14}, {"area": "usability", "severity_sum": 7},
                            {"area": "playback/performance", "severity_sum": 9}, {"area": "access/onboarding", "severity_sum": 0}]}
        out = analysis.premium_only_sensitivity(FakeStore(recs), "lc", rows, rollup)
        self.assertTrue(out["matches_area_rollup"])
        self.assertEqual((out["issue_records"], out["issue_severity_sum"]), (5, 14))
        w = out["without_payment_word"]
        self.assertEqual((w["records"], w["severity_sum"]), (3, 8))  # p1, p2, p4
        self.assertEqual(w["billing_support_severity_sum_without_them"], 6)
        self.assertEqual(w["decision_area_order_without_them"][:3], ["playback/performance", "usability", "billing/support"])
        self.assertEqual(w["decision_areas_above_billing_support_without_them"], ["playback/performance", "usability"])
        self.assertIn("premium", w["words"])
        self.assertTrue(w["case_insensitive"])
        self.assertEqual(out["broader_word_list_check"]["records"], 2)  # the broader list also matches 'payment'
        self.assertIn("not a relabelling", out["interpretation"])

    def test_same_pattern_as_the_manual_disagreement_analysis(self):
        import re
        manual = re.compile(r"premium|subscri|\bpa(y|id|ying)\b|\bfree\b|\bbuy\b|money|trial|\$", re.I)
        ours = re.compile("|".join(p for _, p in analysis.PAYMENT_WORDS), re.I)
        for text in ("Premium only", "subscription", "I paid", "paying more", "pay", "payment", "free tier", "freedom",
                     "buy it", "buying", "money", "trial", "$5", "skip limit", "Paisa"):
            self.assertEqual(bool(manual.search(text)), bool(ours.search(text)), text)

    def test_no_members_is_reported_not_raised(self):
        out = analysis.premium_only_sensitivity(FakeStore([]), "lc", [], None)
        self.assertIn("status", out)


class TestCodeWrittenLimitations(unittest.TestCase):
    def test_sensitivity_and_unallocated_limitations_are_rendered_with_token_ids(self):
        payload, tokens, _ = build({"premium_only_sensitivity": sensitivity_doc()})
        self.assertEqual(payload["unallocated_complaints"]["share_of_complaints_percent"]["value"], "25.0%")
        lims = [memo.fill_cited(x, tokens) for x in memo.code_limitations(payload)]
        self.assertEqual(len(lims), 2)
        self.assertIn("are general/unspecified", lims[0])
        self.assertIn("25.0% (A16)", lims[0])  # A01..A15 are the area table's own tokens
        self.assertIn("200 (A10)", lims[0])
        s = lims[1]
        self.assertIn("upper bound, not a relabelling", s)
        self.assertIn("100 (C01)", s)
        self.assertIn("would fall from 600 (A02) to 480 (", s)
        self.assertIn("below usability 550 (A05) and playback/performance 500 (A08)", s)
        index = {r["token_id"]: r for r in memo.token_index(payload, tokens)}
        self.assertEqual(set(index), set(tokens))
        sens = [r for r in index.values() if "premium_only_sensitivity" in r["measure"]]
        self.assertEqual({r["value"] for r in sens}, {"40", "120", "480"})
        self.assertTrue(all(r["source"] == "analysis/premium_only_sensitivity.json" for r in sens))
        self.assertEqual(index["A16"]["source"], "area_rollup.json")
        md = render(payload, tokens)
        body = md.split("## Limitations")[1]
        order = [body.index(x) for x in ("Model limitation.", "Unallocated complaints", "Premium-only boundary",
                                         "Mandatory limitation.")]
        self.assertEqual(order, sorted(order))
        # every number the code limitations print carries a token ID that memo_tokens.csv lists
        import re
        for value, tid in re.findall(r"(\S+) \(([CAST]\d{2,3})\)", body):
            self.assertIn(tid, index)


class TestMemoValidator(unittest.TestCase):
    def test_key_names_in_braces_are_rejected_because_they_would_stay_unfilled(self):
        payload, tokens, _ = build({"period_comparison": period_doc()})
        data = {"recommended_area": "billing/support", "alternatives": [], "cited_reviews": [],
                "recommendation": "It grew between {earlier_period} and {T02}.", "rationale": ["Severity sum {C02}."],
                "limitations": ["Self-selected reviews."]}
        problems = memo.validate(data, tokens, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("{earlier_period}, which is not a token", problems[0])
        data["recommendation"] = "It grew between {T01} and {T02}."
        self.assertEqual(memo.validate(data, tokens, []), [])


class TestTokenFill(unittest.TestCase):
    def test_a_typed_sign_before_a_signed_value_is_not_doubled(self):
        tokens = {"T38": "+25.1 pp", "T15": "-5.0 pp", "C01": "18016"}
        self.assertEqual(memo.fill_cited("(+{T38}), {T15}, +{C01}", tokens), "(+25.1 pp (T38)), -5.0 pp (T15), +18016 (C01)")
        self.assertEqual(memo.fill("+{T38} and -{T15}", tokens), "+25.1 pp and -5.0 pp")


class TestPromptRules(unittest.TestCase):
    def test_memo_prompt_has_the_review_rules_and_keeps_the_old_ones(self):
        text = (ROOT / "prompts" / "memo_v2.md").read_text(encoding="utf-8")
        for rule in ("among the four decision areas", "never write \"any area\"", "Never call two shares \"close\"",
                     "stay within one labeler", "Never set an enricher-label value against a verifier-label value",
                     "Share of complaints and share of reviews are different measures", "premium_only_sensitivity",
                     "upper bound", "Never write a digit anywhere", "billing.premium_only", "expressed intent"):
            self.assertIn(rule, text)


class TestCalculatorProvenanceAndReconciliation(unittest.TestCase):
    def setUp(self):
        self.calc = load_module("calc_fix", ROOT / "cost" / "calculator.py")

    def call(self, **kw):
        base = {"role": "enrich", "tier": "primary", "attempt": 1, "task_attempt": 1, "outcome": "succeeded",
                "error": None, "review_ids": ["r"], "duration_s": 1.0, "valid_output": None, "finish": "complete",
                "model_reported": "gpt-6-luna"}
        base.update(kw)
        return base

    def test_invalid_output_counts_reconcile(self):
        calls = [self.call(outcome="failed", error="invalid_output: truncated", finish="truncated", valid_output=0),
                 self.call(outcome="failed", error="invalid_output: malformed", finish="malformed_json", valid_output=0),
                 self.call(valid_output=0),                                           # partly valid
                 self.call(task_attempt=2),                                           # retry of the 1st
                 self.call(task_attempt=2, outcome="failed", error="transient: 429"),  # retry of the 2nd, resent
                 self.call(task_attempt=2, attempt=2),
                 self.call(task_attempt=2, outcome="failed", error="invalid_output: malformed", finish="malformed_json",
                           valid_output=0),                                           # retry of the partial: still bad
                 self.call(role="memo", tier="memo", outcome="failed", error="invalid_output: digit", valid_output=0,
                           model_reported="claude-sonnet-5"),
                 self.call()]
        R = self.calc.load_rates(ROOT / "cost" / "rates.csv")
        stages, _ = self.calc._stage_stats(R, [], calls)
        rec = self.calc.invalid_output_reconciliation({"label": "x", "run_dir": None, "stages": stages})
        self.assertEqual((rec["whole_output_invalid"], rec["whole_output_invalid_first_try"],
                          rec["whole_output_invalid_on_retry"]), (3, 2, 1))
        self.assertEqual(rec["whole_output_invalid_by_finish"], {"malformed_json": 2, "truncated": 1})
        self.assertEqual(rec["partially_valid"], 1)
        self.assertEqual((rec["retry_tasks"], rec["retry_task_resends"], rec["retry_attempts"]), (3, 1, 4))
        self.assertEqual(rec["memo_invalid_outputs"], 1)
        self.assertIn("**3** retry tasks", rec["footnote"])
        self.assertIn("**4** attempts", rec["footnote"])
        self.assertEqual(stages["memo"]["models_reported"], ["claude-sonnet-5"])
        old = [{k: v for k, v in c.items() if k != "valid_output"} for c in calls]  # evidence saved before the fix
        stages_old, _ = self.calc._stage_stats(R, [], old)
        self.assertIsNone(self.calc.invalid_output_reconciliation({"label": "x", "stages": stages_old}))

    def test_report_shows_exact_model_ids_next_to_aliases(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            self.calc.replay(ROOT / "cost" / "rates.csv", ROOT / "cost" / "assumptions.json", ROOT / "cost", Path(d))
            md = (Path(d) / "report.md").read_text(encoding="utf-8")
        settings = md.split("### Per-stage settings")[1].split("### Cold vs warm")[0]
        self.assertIn("| Exact model ID (reported) |", settings)
        verify = next(line for line in settings.splitlines() if line.startswith("| verify |"))
        self.assertIn("`haiku`", verify)
        self.assertIn("`claude-haiku-4-5-20251001`", verify)
        self.assertIn("verify-v1", settings)
        self.assertIn("prompts/verify_v2.md", settings)
        inputs = md.split("### Per-unit inputs used")[1].split("\n\n")[1]
        memo_row = next(line for line in inputs.splitlines() if line.startswith("| memo |"))
        self.assertIn("`sonnet`", memo_row)
        self.assertIn("`claude-sonnet-5`", memo_row)


@unittest.skipUnless((ROOT / "runs" / "final-200k" / "grading" / "calls.jsonl.gz").exists(), "needs the final run export")
class TestExportModelIds(unittest.TestCase):
    def test_every_succeeded_call_has_the_reported_model_id(self):
        with gzip.open(ROOT / "runs" / "final-200k" / "grading" / "calls.jsonl.gz", "rt", encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
        ok = [c for c in lines if c["outcome"] == "succeeded"]
        self.assertTrue(ok)
        self.assertTrue(all(c.get("model_reported") for c in ok))
        self.assertTrue({c["model"] for c in ok} <= {"gpt-6-luna", "haiku", "sonnet"})  # configured aliases kept


class TestManifestPathsUnderSymlink(unittest.TestCase):
    def test_symlinked_dataset_folder_is_recorded_relative_to_the_repo(self):
        mod = load_module("subset_fix", ROOT / "scripts" / "make_analysis_subset.py")
        with tempfile.TemporaryDirectory() as d:
            repo, elsewhere = Path(d) / "repo", Path(d) / "elsewhere" / "dataset"
            repo.mkdir()
            elsewhere.mkdir(parents=True)
            (elsewhere / "full.csv").write_text("x\n")
            (repo / "Dataset").symlink_to(elsewhere, target_is_directory=True)
            mod.ROOT, mod.LOGICAL_ROOT = repo.resolve(), repo
            self.assertEqual(mod.shown(repo / "Dataset" / "full.csv"), "Dataset/full.csv")
            self.assertEqual(mod.shown(elsewhere / "full.csv"), str((elsewhere / "full.csv").resolve()))
            self.assertEqual(mod.shown(repo / "data" / "x.csv"), "data/x.csv")


class TestRunLockFile(unittest.TestCase):
    def test_lock_is_closed_and_still_excludes_a_second_invocation(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d) / "run"
            rd.mkdir()
            with open(rd / ".lock", "w") as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with warnings.catch_warnings(record=True) as caught, contextlib.redirect_stdout(io.StringIO()) as out:
                    warnings.simplefilter("always")
                    code = cli.main(["run", "--input", str(FIXTURE), "--run-dir", str(rd), "--offline-stub"])
                    gc.collect()
                self.assertEqual(code, 2)
                self.assertIn("Another invocation is already running", out.getvalue())
                self.assertFalse([w for w in caught if issubclass(w.category, ResourceWarning) and ".lock" in str(w.message)])
            # once the holder is gone, a new invocation can take the lock
            with open(rd / ".lock", "w") as again:
                fcntl.flock(again, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == "__main__":
    unittest.main()


class TestPlanLimitStopsInsteadOfDegrading(unittest.TestCase):
    """A Claude Pro plan limit ("You've hit your session limit · resets ...", HTTP 429) must stop the run with progress
    saved, never finish 'completed' with an empty verification, taxonomy names or a template memo; a resume completes it."""

    def test_session_limit_stops_then_resume_completes(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d) / "run"
            os.environ["STUB_CLAUDE_FAULT"] = "session"
            try:
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = cli.main(["run", "--input", str(FIXTURE), "--run-dir", str(rd), "--offline-stub"])
            finally:
                os.environ.pop("STUB_CLAUDE_FAULT", None)
            self.assertNotEqual(code, 0)
            self.assertIn("systemic_provider_error", out.getvalue())
            self.assertIn("session limit", out.getvalue())
            self.assertNotIn("template (model memo failed validation)", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as out2:
                self.assertEqual(cli.main(["run", "--input", str(FIXTURE), "--run-dir", str(rd), "--offline-stub"]), 0)
            memo_doc = json.loads((rd / "memo.json").read_text())
            self.assertNotIn("template", memo_doc["source"])
            self.assertGreater(json.loads((rd / "verification" / "report.json").read_text())["compared"], 0)

    def test_validator_rejects_within_sampling_error_without_overlap(self):
        payload = {"trends_and_robustness": {"area_shares_with_sampling_intervals": [
            {"area": "usability", "interval_overlaps_with": []}, {"area": "billing/support", "interval_overlaps_with": []}]}}
        data = {"recommended_area": "usability", "recommendation": "Usability leads.",
                "rationale": ["Usability's share is higher within sampling error."], "limitations": ["Self-selected."],
                "alternatives": [], "cited_reviews": []}
        problems = memo.validate(data, {}, [], payload)
        self.assertTrue(any("within sampling error" in p for p in problems))
        payload["trends_and_robustness"]["area_shares_with_sampling_intervals"][0]["interval_overlaps_with"] = ["billing/support"]
        self.assertFalse(any("within sampling error" in p for p in memo.validate(data, {}, [], payload)))
