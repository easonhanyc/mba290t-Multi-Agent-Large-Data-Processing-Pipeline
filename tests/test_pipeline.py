"""Integration tests: the whole pipeline against the local stub server (no network, no spend).

These exercise the real SDK adapters, retries, ledger, cache, resume, exports and the course
checker. Labels produced by the stub are meaningless by design; only the control flow is tested.
"""

import contextlib
import csv
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ["INSIGHT_NO_DOTENV"] = "1"  # never load real keys from .env during tests

from insight import cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_small.csv"
CHECKER = ROOT / "Final Assignment - Spotify Reviews Dataset" / "check_submission.py"
PY = sys.executable


def run_cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main([str(a) for a in argv])
    return code, buf.getvalue()


def temp_config(tmp, **edits):
    """Copy config/pipeline.toml with exact-line replacements, e.g. backoff_initial_s='0.01'."""
    text = (ROOT / "config" / "pipeline.toml").read_text()
    lines = []
    for line in text.splitlines():
        key = line.split("=")[0].strip()
        if key in edits and "=" in line:
            line = f"{key} = {edits[key]}"
        lines.append(line)
    path = Path(tmp) / "pipeline.toml"
    path.write_text("\n".join(lines) + "\n")
    return path


def checker(run_dir, csv_path=FIXTURE):
    ref = Path(run_dir) / "local-reference.json"
    out = Path(run_dir) / "self-check.json"
    subprocess.run([PY, str(CHECKER), "reference", "--full", str(csv_path), "--analysis", str(csv_path), "--out", str(ref)],
                   check=True, capture_output=True)
    subprocess.run([PY, str(CHECKER), "check", "--reference", str(ref), "--submission", str(Path(run_dir) / "grading"),
                    "--out", str(out)], check=True, capture_output=True)
    return json.loads(out.read_text())


def records(run_dir):
    with open(Path(run_dir) / "grading" / "records.jsonl", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def calls(run_dir):
    with open(Path(run_dir) / "grading" / "calls.jsonl", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


@unittest.skipUnless(CHECKER.exists(), "course checker not present")
class TestOfflinePipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.fast = temp_config(self.tmp.name, backoff_initial_s="0.01", backoff_max_s="0.05", llm_batch_size="4")

    def tearDown(self):
        self.tmp.cleanup()

    def test_interrupt_resume_warm_rerun_and_checker_pass(self):
        rd = self.dir / "run"
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub", "--stop-after", "3")
        self.assertEqual(code, 3, out)
        before = json.loads((rd / "grading" / "checkpoint_before.json").read_text())["completed_ids"]
        self.assertTrue(before)
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")
        self.assertEqual(code, 0, out)
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")
        self.assertEqual(code, 0, out)
        latest = json.loads((rd / "run_summary.json").read_text())["latest"]
        self.assertEqual(latest["calls_this_invocation"], {}, "warm rerun must make zero model calls")
        after = json.loads((rd / "grading" / "checkpoint_after.json").read_text())["completed_ids"]
        self.assertTrue(set(before) < set(after))
        phases = {(c["role"], c["phase"]) for c in calls(rd)}
        self.assertIn(("enrich", "initial"), phases)
        self.assertIn(("enrich", "resume"), phases)
        resume_ids = {i for c in calls(rd) if c["role"] == "enrich" and c["phase"] == "resume" for i in c["review_ids"]}
        self.assertFalse(resume_ids & set(before), "completed IDs must not be re-sent after resume")
        report = checker(rd)
        self.assertEqual(report["status"], "pass", report["issue_counts"])
        self.assertEqual(report["coverage"]["valid_cache_reuses"], 2)
        self.assertEqual(report["coverage"]["quarantined"], 2)
        code, out = run_cli("rank", "--run-dir", rd, "--check", "--offline-stub")
        self.assertEqual(code, 0, out)
        self.assertIn('"identical": true', out)
        code, out = run_cli("planted-error", "--run-dir", rd, "--offline-stub")
        self.assertEqual(json.loads((rd / "evals" / "planted_error.json").read_text())["status"], "detected")

    def test_ignored_columns_and_metadata_never_reach_a_model(self):
        rd = self.dir / "leak"
        cap = self.dir / "bodies.txt"
        os.environ["INSIGHT_STUB_CAPTURE"] = str(cap)
        try:
            code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")
        finally:
            os.environ.pop("INSIGHT_STUB_CAPTURE", None)
        self.assertEqual(code, 0, out)
        bodies = cap.read_text(encoding="utf-8")
        self.assertIn("crashing", bodies)  # review text does reach the models
        self.assertNotIn("HUMAN-LABEL-MUST-BE-IGNORED", bodies)
        self.assertNotIn("2023-01-05", bodies)  # timestamps never sent
        for line in bodies.splitlines():
            body = json.loads(line)
            if "state" in body:
                self.assertEqual(set(body["state"]), {"review_text"})

    def test_transient_faults_retry_and_invalid_output_retry_once(self):
        rd = self.dir / "faults"
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub",
                            "--stub-faults", "openai:1=429,openai:2=500,openai:3=malformed")
        self.assertEqual(code, 0, out)
        cs = calls(rd)
        self.assertTrue(any(c["attempt"] == 2 and c["role"] == "enrich" for c in cs), "transient errors are retried")
        failed = [c for c in cs if c["outcome"] == "failed"]
        self.assertTrue(any("rate limited" in (c["error"] or "") for c in failed))
        self.assertTrue(any("server error" in (c["error"] or "") for c in failed))
        self.assertTrue(any((c["error"] or "").startswith("invalid_output") for c in failed))
        self.assertTrue(any(c["task_attempt"] == 2 for c in cs), "invalid output gets exactly one retry")
        self.assertFalse(any(c["task_attempt"] > 2 for c in cs))
        self.assertEqual(checker(rd)["issue_counts"].keys() - {"resume_call_evidence", "resume_snapshot_mismatch"}, set())

    def test_timeout_is_logged_with_unknown_charge(self):
        rd = self.dir / "timeout"
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub",
                            "--stub-faults", "openai:1=timeout", "--timeout-s", "0.5", "--stub-timeout-sleep", "1.0")
        self.assertEqual(code, 0, out)
        t = [c for c in calls(rd) if (c["error"] or "").startswith("transient: timeout")]
        self.assertEqual(len(t), 1)
        self.assertFalse(t[0]["usage_reported"])

    def test_circuit_breaker_stops_and_exports_unfinished(self):
        rd = self.dir / "breaker"
        cfg = temp_config(self.tmp.name, backoff_initial_s="0.01", backoff_max_s="0.02", max_attempts="2",
                          circuit_breaker_failures="3", llm_batch_size="2")
        code, out = run_cli("--config", cfg, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub",
                            "--stub-faults", "openai:1-200=500")
        self.assertEqual(code, 3, out)
        self.assertIn("circuit_breaker", out)
        recs = records(rd)
        self.assertEqual(len(recs), 12, "every source ID is still exported")
        self.assertTrue(any(r.get("reason", "").startswith("unfinished:") for r in recs))

    def test_budget_cap_stops_admission_then_resume_finishes(self):
        rd = self.dir / "budget"
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub",
                            "--shadow-rates", "--budget-usd", "0.0009")
        self.assertEqual(code, 3, out)
        self.assertIn("budget_cap", out)
        latest = json.loads((rd / "run_summary.json").read_text())["latest"]
        self.assertGreater(latest["ledger"]["denials"], 0)
        self.assertLessEqual(latest["ledger"]["spent_usd"], 0.0009)
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub",
                            "--shadow-rates", "--budget-usd", "1.0")
        self.assertEqual(code, 0, out)
        self.assertEqual(checker(rd)["status"], "pass")

    def test_two_workers_give_identical_labels(self):
        one, two = self.dir / "w1", self.dir / "w2"
        self.assertEqual(run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", one, "--offline-stub")[0], 0)
        self.assertEqual(run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", two, "--offline-stub",
                                 "--workers", "2")[0], 0)
        key = lambda rs: {r["review_id"]: (r.get("topic"), r.get("intent"), r.get("severity"), r.get("evidence_quote"))
                          for r in rs}
        self.assertEqual(key(records(one)), key(records(two)))

    def test_interrupted_and_resumed_run_gives_same_labels_as_uninterrupted(self):
        whole, split = self.dir / "whole", self.dir / "split"
        self.assertEqual(run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", whole, "--offline-stub")[0], 0)
        self.assertEqual(run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", split, "--offline-stub",
                                 "--stop-after", "2", "--workers", "2")[0], 3)
        self.assertEqual(run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", split, "--offline-stub",
                                 "--workers", "2")[0], 0)
        key = lambda rs: {r["review_id"]: (r["status"], r.get("topic"), r.get("intent"), r.get("severity"),
                                           r.get("labeled_by"), r.get("evidence_quote")) for r in rs}
        self.assertEqual(key(records(whole)), key(records(split)))

    def test_llm_backend_batches(self):
        rd = self.dir / "llm"
        cfg = temp_config(self.tmp.name, backend='"llm"', backoff_initial_s="0.01", llm_batch_size="4")
        code, out = run_cli("--config", cfg, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")
        self.assertEqual(code, 0, out)
        enrich = [c for c in calls(rd) if c["role"] == "enrich" and c["tier"] == "primary"]
        self.assertTrue(all(1 <= len(c["review_ids"]) <= 4 for c in enrich))
        self.assertEqual(checker(rd)["issue_counts"].keys() - {"resume_call_evidence", "resume_snapshot_mismatch"}, set())

    def test_live_calls_refused_without_allow_paid(self):
        code, out = run_cli("run", "--input", FIXTURE, "--run-dir", self.dir / "live")
        self.assertEqual(code, 2)
        self.assertIn("--allow-paid", out)

    def test_missing_keys_fail_before_any_work(self):
        env = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
        env["INSIGHT_NO_DOTENV"] = "1"
        p = subprocess.run([PY, "-m", "insight", "run", "--input", str(FIXTURE), "--run-dir", str(self.dir / "nokeys"),
                            "--allow-paid", "--budget-usd", "0.10"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("Missing API keys", p.stdout)

    def test_real_sigint_then_resume(self):
        rd = self.dir / "sigint"
        one = temp_config(self.tmp.name, backoff_initial_s="0.01", backoff_max_s="0.05", llm_batch_size="1")
        proc = subprocess.Popen([PY, "-m", "insight", "--config", str(one), "run", "--input", str(FIXTURE),
                                 "--run-dir", str(rd), "--offline-stub", "--stub-faults", "openai:1-50=slow",
                                 "--stub-timeout-sleep", "0.4"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
        time.sleep(1.5)
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 130, out)
        summary = json.loads((rd / "run_summary.json").read_text())["latest"]
        self.assertEqual(summary["status"], "interrupted")
        self.assertGreater(summary["results"]["unfinished"], 0)
        code, out = run_cli("--config", one, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")
        self.assertEqual(code, 0, out)
        self.assertEqual(checker(rd)["status"], "pass")

    def test_second_invocation_on_same_run_dir_is_refused(self):
        rd = self.dir / "locked"
        one = temp_config(self.tmp.name, backoff_initial_s="0.01", backoff_max_s="0.05", llm_batch_size="1")
        proc = subprocess.Popen([PY, "-m", "insight", "--config", str(one), "run", "--input", str(FIXTURE),
                                 "--run-dir", str(rd), "--offline-stub", "--stub-faults", "openai:1-50=slow",
                                 "--stub-timeout-sleep", "0.5"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(1.5)
        code, out = run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")
        proc.communicate(timeout=60)
        self.assertEqual(code, 2, out)
        self.assertIn("Another invocation is already running", out)

    def test_label_config_change_needs_a_new_run_dir(self):
        rd = self.dir / "cfgchange"
        self.assertEqual(run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")[0], 0)
        changed = temp_config(self.tmp.name, backoff_initial_s="0.01", llm_batch_size="4",
                              max_output_tokens_per_review="61")
        code, out = run_cli("--config", changed, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")
        self.assertEqual(code, 2, out)
        self.assertIn("different label_config", out)

    def test_golden_scoring_on_synthetic_labels(self):
        rd = self.dir / "golden"
        self.assertEqual(run_cli("--config", self.fast, "run", "--input", FIXTURE, "--run-dir", rd, "--offline-stub")[0], 0)
        labelled = self.dir / "golden_labels.csv"
        with open(FIXTURE, encoding="utf-8", newline="") as f, open(labelled, "w", encoding="utf-8", newline="") as g:
            reader = csv.DictReader(f)
            fields = ["review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp",
                      "topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review"]
            w = csv.DictWriter(g, fieldnames=fields)
            w.writeheader()
            for r in reader:
                row = {k: r[k] for k in fields[:6]}
                row.update({"topic": "playback|other", "intent": "complaint", "sentiment": "-0.5", "severity": "3|4",
                            "entities": "", "evidence_quote": "", "needs_review": "false"})
                w.writerow(row)
        code, out = run_cli("golden", "--labels", labelled, "--run-dir", rd, "--offline-stub", "--out", self.dir / "g.json")
        self.assertEqual(code, 0, out)
        res = json.loads((self.dir / "g.json").read_text())
        self.assertEqual(res["cases"], 12)
        self.assertEqual(res["ambiguous_cases"], 12)
        self.assertEqual(res["missing_or_quarantined_predictions"], 2)  # the two empty texts are quarantined


if __name__ == "__main__":
    unittest.main()
