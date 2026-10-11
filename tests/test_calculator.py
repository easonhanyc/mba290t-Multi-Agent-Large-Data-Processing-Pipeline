"""Calculator invariants required by COST_CALCULATOR.md, checked offline.

A priced pilot is synthesised in a temporary folder from the offline-stub example by renaming
stub-* models to real model IDs. It exists only inside the test; nothing here is a measurement.
"""

import csv
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COST = ROOT / "cost"
EXAMPLE = COST / "offline_stub_example"


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


if __name__ == "__main__":
    unittest.main()
