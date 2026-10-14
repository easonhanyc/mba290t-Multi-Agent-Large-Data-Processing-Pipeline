"""Calculator invariants required by COST_CALCULATOR.md, checked offline.

A priced pilot is synthesised in a temporary folder from the offline-stub example by renaming
stub-* models to real model IDs. It exists only inside the test; nothing here is a measurement.
Spend-to-date tests read the run directories and committed evidence read-only; a "clean clone" is
simulated by copying runs/ without the git-ignored final-run database into a temporary folder.
"""

import contextlib
import csv
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
COST = ROOT / "cost"
EXAMPLE = COST / "offline_stub_example"
FINAL_REFRESH = COST / "refreshes" / "final_200k.json"


def load_calc():
    spec = importlib.util.spec_from_file_location("calculator", COST / "calculator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def priced_copy(tmp):
    d = Path(tmp) / "pilot"
    shutil.copytree(EXAMPLE, d)
    runs = json.loads((d / "pilot_runs.json").read_text())
    runs["offline_stub"] = False
    (d / "pilot_runs.json").write_text(json.dumps(runs))
    with open(d / "usage.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["model"] = r["model"].replace("stub-", "")
    with open(d / "usage.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(d / "pilot_calls.jsonl", encoding="utf-8") as f:
        calls = [json.loads(l) for l in f]
    with open(d / "pilot_calls.jsonl", "w", encoding="utf-8") as f:
        for c in calls:
            c["model"] = c["model"].replace("stub-", "")
            f.write(json.dumps(c) + "\n")
    return d


def doubled_rates(tmp):
    out = Path(tmp) / "rates_x2.csv"
    with open(COST / "rates.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["usd_per_million"] = str(float(r["usd_per_million"]) * 2)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return out


def runs_copy_without_final_db(tmp):
    """runs/ as a clean clone has it: every committed state database, but not runs/final-200k/state.sqlite
    (git-ignored, published only as a release asset) and not the git-ignored runs/_* folders."""
    dst = Path(tmp) / "runs"
    dst.mkdir()
    for d in sorted((ROOT / "runs").iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        t = dst / d.name
        t.mkdir()
        if (d / "invocations").is_dir():
            shutil.copytree(d / "invocations", t / "invocations")
        if (d / "run_summary.json").exists():
            shutil.copy2(d / "run_summary.json", t / "run_summary.json")
        if d.name != "final-200k":
            for f in d.glob("state.sqlite*"):
                shutil.copy2(f, t / f.name)
    return dst


def by_hand_billed(usage_csv):
    """Committed usage x rates.csv, written independently of the calculator (Claude Pro rows are $0 per call)."""
    rates, kinds = {}, {}
    with open(COST / "rates.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rates[(r["provider"], r["model"], r["tier"], r["item"])] = float(r["usd_per_million"]) / 1e6
            kinds[(r["provider"], r["model"])] = r["kind"]
    total = 0.0
    with open(usage_csv, encoding="utf-8", newline="") as f:
        for u in csv.DictReader(f):
            if u["billing"] == "subscription" or kinds.get((u["provider"], u["model"])) == "subscription" or not int(u["billed_units"]):
                continue
            key = (u["provider"], u["model"], u["tier"], u["item"])
            if key not in rates and u["item"] == "input_cache_write":
                key = (u["provider"], u["model"], u["tier"], "input_uncached")
            total += int(u["billed_units"]) * rates[key]
    return total


@unittest.skipUnless((EXAMPLE / "pilot_runs.json").exists(), "run `cost/calculator.py pilot --execute --offline-stub` first")
class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = load_calc()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_replay_needs_no_pilot_and_marks_it_unmeasured(self):
        out = Path(self.tmp.name) / "empty"
        meas, proj = self.calc.replay(COST / "rates.csv", COST / "assumptions.json", Path(self.tmp.name) / "nothing", out)
        self.assertIsNone(meas)
        self.assertIn("NOT MEASURED YET", (out / "report.md").read_text())
        self.assertIn("base_reuse", proj["scenarios"])

    def test_doubling_rates_doubles_api_cost_only(self):
        pilot = priced_copy(self.tmp.name)
        m1, p1 = self.calc.replay(COST / "rates.csv", COST / "assumptions.json", pilot, Path(self.tmp.name) / "a")
        m2, p2 = self.calc.replay(doubled_rates(self.tmp.name), COST / "assumptions.json", pilot, Path(self.tmp.name) / "b")
        for label in ("cold", "warm"):
            self.assertAlmostEqual(m2["runs"][label]["api_cost_usd"], 2 * m1["runs"][label]["api_cost_usd"], places=9)
            self.assertEqual(m2["runs"][label]["wall_clock_s"], m1["runs"][label]["wall_clock_s"])
        self.assertGreater(m1["runs"]["cold"]["api_cost_usd"], 0)
        self.assertEqual(m1["runs"]["warm"]["new_enrichment_calls"], 0)
        a = json.loads((COST / "assumptions.json").read_text())
        self.assertEqual(self.calc.local_compute_usd(a, m1["runs"]["cold"]["wall_clock_s"]),
                         self.calc.local_compute_usd(a, m2["runs"]["cold"]["wall_clock_s"]))
        self.assertAlmostEqual(p2["scenarios"]["base_reuse"]["api_cost_usd"], 2 * p1["scenarios"]["base_reuse"]["api_cost_usd"],
                               delta=0.02)

    def test_changing_projected_rows_does_not_change_measured_results(self):
        pilot = priced_copy(self.tmp.name)
        a = json.loads((COST / "assumptions.json").read_text())
        a["full_run"]["rows"] = 1_000_000
        a["full_run"]["distinct_nonempty_texts"] = 900_000
        alt = Path(self.tmp.name) / "assumptions_alt.json"
        alt.write_text(json.dumps(a))
        m1, p1 = self.calc.replay(COST / "rates.csv", COST / "assumptions.json", pilot, Path(self.tmp.name) / "a")
        m2, p2 = self.calc.replay(COST / "rates.csv", alt, pilot, Path(self.tmp.name) / "b")
        self.assertEqual(json.dumps(m1, sort_keys=True), json.dumps(m2, sort_keys=True))
        self.assertNotEqual(p1["scenarios"]["base_reuse"]["api_cost_usd"], p2["scenarios"]["base_reuse"]["api_cost_usd"])

    def test_budget_warning(self):
        _, p = self.calc.replay(COST / "rates.csv", COST / "assumptions.json", Path(self.tmp.name) / "none",
                                Path(self.tmp.name) / "c", budget=1.0)
        self.assertTrue(all(s["exceeds_budget"] for s in p["scenarios"].values()))
        _, p = self.calc.replay(COST / "rates.csv", COST / "assumptions.json", Path(self.tmp.name) / "none",
                                Path(self.tmp.name) / "d", budget=10_000.0)
        self.assertFalse(any(s["exceeds_budget"] for s in p["scenarios"].values()))

    def test_measured_cost_equals_usage_times_rates_by_hand(self):
        pilot = priced_copy(self.tmp.name)
        m, _ = self.calc.replay(COST / "rates.csv", COST / "assumptions.json", pilot, Path(self.tmp.name) / "e")
        rates, kinds = {}, {}
        with open(COST / "rates.csv", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rates[(r["provider"], r["model"], r["tier"], r["item"])] = float(r["usd_per_million"]) / 1e6
                kinds[(r["provider"], r["model"])] = r["kind"]
        total = 0.0
        with open(pilot / "usage.csv", encoding="utf-8", newline="") as f:
            for u in csv.DictReader(f):
                if u["run_label"] != "cold" or kinds.get((u["provider"], u["model"])) == "subscription":
                    continue  # Claude Pro calls are not billed per call
                key = (u["provider"], u["model"], u["tier"], u["item"])
                if key not in rates and u["item"] == "input_cache_write":
                    key = (u["provider"], u["model"], u["tier"], "input_uncached")
                total += int(u["billed_units"]) * rates[key]
        self.assertGreater(total, 0)
        self.assertAlmostEqual(m["runs"]["cold"]["api_cost_usd"], total, places=8)

    def test_subscription_calls_are_not_billed_but_have_api_equivalent(self):
        R = self.calc.load_rates(COST / "rates.csv")
        self.assertEqual(self.calc.unit_price(R, "claude_code", "haiku", "subscription", "output"), 0.0)
        self.assertAlmostEqual(self.calc.api_equiv_price(R, "claude-haiku-5-5-20260901", "output"), 0.50 / 1e6)
        self.assertAlmostEqual(self.calc.unit_price(R, "openai", "gpt-6-luna", "flex", "output"),
                               0.5 * self.calc.unit_price(R, "openai", "gpt-6-luna", "standard", "output"))

    def test_opening_the_calculator_makes_no_calls(self):
        # Importing must not execute anything; the default command only reads files.
        p = subprocess.run([sys.executable, "-c", "import importlib.util,sys;"
                            f"s=importlib.util.spec_from_file_location('c', r'{COST / 'calculator.py'}');"
                            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print('imported')"],
                           capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "imported")


@unittest.skipUnless(FINAL_REFRESH.exists() and (ROOT / "runs").is_dir(), "needs the committed final_200k refresh and runs/")
class TestSpendToDate(unittest.TestCase):
    def setUp(self):
        self.calc = load_calc()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_project_spend_reproduced_from_committed_usage_without_final_db(self):
        runs = runs_copy_without_final_db(self.tmp.name)
        self.assertFalse((runs / "final-200k" / "state.sqlite").exists())
        offline = self.calc.project_spend(runs_root=runs)
        with mock.patch.dict(os.environ, {"INSIGHT_RUNS_ROOT": str(runs)}):  # same rule as the pipeline's project cap
            self.assertEqual(self.calc.project_spend()["total_billed_usd"], offline["total_billed_usd"])
        local = self.calc.project_spend(runs_root=ROOT / "runs")  # the final DB if this checkout has it
        committed = json.loads((COST / "project_spend.json").read_text())
        self.assertEqual(offline["total_billed_usd"], local["total_billed_usd"])
        self.assertEqual(offline["total_billed_usd"], committed["total_billed_usd"])
        self.assertEqual(offline["not_reproducible_offline"], {})
        self.assertEqual(offline["cross_check"]["calls_differing_from_logged_cost"], 0)
        final = offline["per_run"]["runs/final-200k"]
        self.assertEqual((final["calls_from_state_db"], final["usage_from"]), (0, "committed usage"))
        self.assertAlmostEqual(final["billed_usd"], round(by_hand_billed(COST / "refreshes" / "final_200k_usage.csv"), 6), places=6)
        self.assertTrue(final["matches_ledger"])  # equals the run's own ledger in runs/final-200k/invocations/*.json
        # nothing is counted twice: each request ID once, whichever sources hold it
        self.assertEqual(sum(v["calls"] for v in offline["per_run"].values()), offline["calls"])
        self.assertEqual(sum(v["calls"] for v in local["per_run"].values()), local["calls"])
        self.assertEqual(offline["calls"], local["calls"])
        # end to end through the CLI, into a scratch folder
        out = Path(self.tmp.name) / "replay"
        with contextlib.redirect_stdout(io.StringIO()):
            self.calc.main(["replay", "--out-dir", str(out), "--runs-root", str(runs)])
        rep = json.loads((out / "report.json").read_text())
        self.assertEqual(rep["spend"]["total_billed_usd"], committed["total_billed_usd"])
        self.assertIn("Not reproducible offline: none", (out / "report.md").read_text())

    def test_runs_without_any_call_evidence_are_listed_not_dropped(self):
        runs = Path(self.tmp.name) / "runs"
        ghost = runs / "ghost-run" / "invocations"
        ghost.mkdir(parents=True)
        (ghost / "run-x.json").write_text(json.dumps({"run_id": "run-x", "finished_at": "2026-10-13T00:00:00Z",
                                                      "offline_stub": False, "workers": 1,
                                                      "ledger": {"spent_usd": 0.5, "unknown_usd": 0.0}}))
        stub = runs / "stub-run" / "invocations"
        stub.mkdir(parents=True)
        (stub / "run-y.json").write_text(json.dumps({"run_id": "run-y", "finished_at": "2026-10-13T00:00:00Z",
                                                     "offline_stub": True, "workers": 1}))
        s = self.calc.project_spend(runs_root=runs)
        self.assertIn("runs/ghost-run", s["not_reproducible_offline"])
        self.assertEqual(s["not_reproducible_offline"]["runs/ghost-run"]["recorded_usd"], 0.5)
        self.assertNotIn("runs/ghost-run", s["per_run"])
        self.assertNotIn("runs/stub-run", s["not_reproducible_offline"])  # stub-only runs make no billed calls
        self.assertIn("runs/final-200k", s["per_run"])  # still reproduced from cost/refreshes/
        self.assertNotIn("runs/ghost-run", json.dumps(s["per_run"]))

    def test_replay_to_another_out_dir_never_writes_committed_spend(self):
        spend = COST / "project_spend.json"
        before = (spend.read_bytes(), spend.stat().st_mtime_ns) if spend.exists() else None
        out = Path(self.tmp.name) / "scratch"
        with contextlib.redirect_stdout(io.StringIO()):
            self.calc.main(["replay", "--out-dir", str(out), "--rates", str(doubled_rates(self.tmp.name))])
        self.assertTrue((out / "report.md").exists())
        self.assertFalse((out / "project_spend.json").exists())
        self.assertEqual((spend.read_bytes(), spend.stat().st_mtime_ns) if spend.exists() else None, before)

    def test_doubling_rates_doubles_recomputed_spend(self):
        one = self.calc.project_spend()
        two = self.calc.project_spend(rates_path=doubled_rates(self.tmp.name))
        self.assertAlmostEqual(two["settled_billed_usd"], 2 * one["settled_billed_usd"], places=5)
        self.assertEqual(two["calls"], one["calls"])

    def test_enrichment_workers_come_from_enrichment_invocations(self):
        invs = [{"run_id": "a", "workers": 16, "wall_clock_s": 10.0, "stage_seconds": {"enrich": 9.0}},
                {"run_id": "b", "workers": 4, "wall_clock_s": 2.0, "stage_seconds": {"memo": 1.0}}]
        calls = [{"run_id": "a", "role": "enrich"}, {"run_id": "b", "role": "memo"}]
        summ = self.calc.invocation_summary(invs, calls)
        self.assertEqual((summ["workers"], summ["latest_invocation_workers"], summ["enrichment_invocations"]), (16, 4, 1))
        ref = json.loads(FINAL_REFRESH.read_text())
        self.assertEqual(ref["workers"], 16)
        self.assertEqual(json.loads((COST / "assumptions.json").read_text())["controls"]["max_workers"], ref["workers"])

    def test_declared_scope_time_projection_matches_measured_final_run(self):
        out = Path(self.tmp.name) / "proj"
        _, proj = self.calc.replay(COST / "rates.csv", COST / "assumptions.json", COST, out)
        chk = proj["declared_scope"]["projection_check"]
        self.assertEqual(chk["measured"]["workers"], [16, 16])
        self.assertAlmostEqual(chk["rows"]["total"]["ratio"], 1.0, delta=0.1)
        self.assertIn("## Scaling decision", (out / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
