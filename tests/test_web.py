"""Dashboard database + API tests (web/load_db.py, web/api/index.py) on a local SQLite file.

A small offline-stub run of the pipeline is loaded with the real loader, then the read-only API is queried
through FastAPI's TestClient. No network, no model calls.
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ["INSIGHT_NO_DOTENV"] = "1"

from insight import cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_small.csv"


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _ApiCase(unittest.TestCase):
    """Builds one offline-stub run and loads it into a SQLite dashboard database once per class."""
    db_name = "dash.db"

    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            raise unittest.SkipTest("fastapi not installed")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.rd = Path(cls.tmp.name) / "run"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["run", "--input", str(FIXTURE), "--run-dir", str(cls.rd), "--offline-stub"])
        assert code == 0, buf.getvalue()
        cls.db = Path(cls.tmp.name) / cls.db_name
        load_db = _module("load_db_under_test", ROOT / "web" / "load_db.py")
        cls.check = load_db.load(cls.rd, f"sqlite:///{cls.db}", input_csv=FIXTURE, log=lambda *a: None)
        cls.prepare_db()
        cls._saved_env = os.environ.get("DATABASE_URL_READONLY")
        os.environ["DATABASE_URL_READONLY"] = f"sqlite:///{cls.db}"
        cls.api = _module(f"dash_api_{cls.__name__}", ROOT / "web" / "api" / "index.py")
        cls.c = TestClient(cls.api.app)

    @classmethod
    def prepare_db(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "api", None) and cls.api._conn["c"] is not None:
            cls.api._conn["c"].close()
        if cls._saved_env is None:
            os.environ.pop("DATABASE_URL_READONLY", None)
        else:
            os.environ["DATABASE_URL_READONLY"] = cls._saved_env
        cls.tmp.cleanup()

    def get(self, path, status=200):
        r = self.c.get(path)
        self.assertEqual(r.status_code, status, f"{path}: {r.text[:300]}")
        return r.json()


class TestDashboardApi(_ApiCase):
    def test_loader_stores_token_index_and_trimmed_verification(self):
        con = sqlite3.connect(self.db)
        try:
            docs = dict(con.execute("SELECT name, body FROM documents").fetchall())
            evidence = [json.loads(e) for (e,) in con.execute("SELECT evidence_json FROM issues")]
        finally:
            con.close()
        memo = json.loads((self.rd / "memo.json").read_text())
        self.assertEqual(json.loads(docs["memo_tokens"]), memo["token_index"])
        if (self.rd / "verification" / "report.json").exists():
            self.assertNotIn("disagreements", json.loads(docs["verification_summary"]))
        self.assertTrue(all(isinstance(q.get("misfit"), bool) for pack in evidence for q in pack))

    def test_recommendation_returns_token_index_for_every_token(self):
        r = self.get("/api/recommendation")
        index = {t["token_id"]: t for t in r["token_index"]}
        self.assertEqual(set(index), set(r["tokens"]))
        for tid, t in index.items():
            self.assertEqual(str(t["value"]), str(r["tokens"][tid]), tid)
            self.assertTrue(t["measure"] and t["source"], tid)
        used = set()
        out = r["output"]
        for text in [out["recommendation"], *out["rationale"], *out["limitations"],
                     *[a["why_not_first"] for a in out["alternatives"]]]:
            used |= set(re.findall(r"\{([CAST]\d{2,3})\}", text))
        self.assertTrue(used <= set(index), used - set(index))
        self.assertIsInstance(r["limitations_code"], list)
        self.assertEqual(r["headline"]["area"], r["recommended_area"])
        self.assertIn("decision_areas", r["notes"])

    def test_code_written_limitations_come_from_memo_md(self):
        r = self.get("/api/recommendation")
        section = r["memo_md"].split("## Limitations", 1)[1].split("\n## ", 1)[0]
        bullets = [x[2:].strip() for x in section.splitlines() if x.startswith("- ")]
        self.assertEqual(len(bullets), len(r["output"]["limitations"]) + len(r["limitations_code"]))
        self.assertEqual(bullets[len(r["output"]["limitations"]):], r["limitations_code"])

    def test_consistency_rechecks_area_and_scope_tokens_in_sql(self):
        cons = self.get("/api/consistency")
        self.assertTrue(cons["ranking_matches"] and cons["claims_match"])
        checks = cons["token_checks"]
        self.assertEqual(cons["tokens_checked"], len(checks))
        bad = {k: v for k, v in checks.items() if not v["matches"]}
        self.assertEqual(bad, {})
        self.assertTrue(cons["tokens_match"])
        kinds = {k[0] for k in checks}
        index = self.get("/api/recommendation")["token_index"]
        if any(t["token_id"].startswith("A") for t in index):
            self.assertIn("A", kinds)

    def test_evals_payload_is_trimmed(self):
        r = self.c.get("/api/evals")
        self.assertEqual(r.status_code, 200)
        e = r.json()
        self.assertEqual(set(e), {"verification_sql", "verification_report", "golden", "golden_error_analysis",
                                  "golden_candidates", "quote_support",
                                  "planted_error", "injection", "rank_check", "self_check", "self_check_full"})
        if e["verification_report"]:
            self.assertNotIn("disagreements", e["verification_report"])
            self.assertIn("agreement", e["verification_report"])
            self.assertIn("top_confusions", e["verification_report"])
        for k in ("golden",):
            if isinstance(e[k], dict):
                self.assertNotIn("cases_detail", e[k])
        for d in (e["golden_candidates"] or {}).values():
            self.assertNotIn("cases_detail", d)
        for k in ("self_check", "self_check_full"):
            if isinstance(e[k], dict):
                self.assertNotIn("calculated_ranking", e[k])
        self.assertLess(len(r.content), 100_000)

    def test_issue_filter_counts_ranked_complaints_like_the_ranking(self):
        ranking = self.get("/api/ranking")
        self.assertEqual(ranking["total_complaints"], sum(i["complaint_count"] for i in ranking["issues"]))
        for i in ranking["issues"]:
            only = self.get(f"/api/reviews?issue_id={i['issue_id']}&limit=1")
            every = self.get(f"/api/reviews?issue_id={i['issue_id']}&complaints_only=false&limit=1")
            self.assertEqual(only["total"], i["complaint_count"], i["issue_id"])
            self.assertGreaterEqual(every["total"], only["total"], i["issue_id"])

    def test_issue_detail_puts_the_naming_evidence_first(self):
        ranking = self.get("/api/ranking")["issues"]
        d = self.get(f"/api/issues/{ranking[0]['issue_id']}")
        pack = [e["review_id"] for e in d["issue"]["evidence_json"]]
        self.assertEqual(sorted(e["review_id"] for e in d["representative"]), sorted(pack))
        self.assertFalse({e["review_id"] for e in d["evidence"]} & set(pack))
        if d["evidence"] and d["modal_severity"] is not None:
            gaps = [abs(e["severity"] - d["modal_severity"]) for e in d["evidence"]]
            self.assertEqual(gaps, sorted(gaps))
        self.assertTrue(all("month_reviews" in m for m in d["monthly"]))

    def test_review_lookup_accepts_a_unique_prefix_and_explains_misses(self):
        rid = self.get("/api/reviews?limit=1")["reviews"][0]["review_id"]
        self.assertEqual(self.get(f"/api/reviews/{rid[:13]}")["review"]["review_id"], rid)
        miss = self.get("/api/reviews/not-a-real-id", status=404)
        self.assertIn("analysed scope", miss["detail"])

    def test_run_exposes_final_run_cost_shape_and_api_is_read_only(self):
        run = self.get("/api/run")
        self.assertIn("recording_meta", run)
        self.assertIn("final_run", run["cost"] or {"final_run": None})
        spec = self.get("/api/openapi.json")
        self.assertEqual({m for p in spec["paths"].values() for m in p}, {"get"})
        self.assertEqual(self.c.post("/api/overview").status_code, 405)
        self.assertEqual(self.c.get("/docs", follow_redirects=False).status_code, 307)
        self.assertEqual(self.c.get("/api/docs").status_code, 200)


class TestDashboardApiOlderDatabase(_ApiCase):
    """A database loaded before the token index / verification summary existed still serves every route."""
    db_name = "old.db"

    @classmethod
    def prepare_db(cls):
        con = sqlite3.connect(cls.db)
        try:
            con.execute("DELETE FROM documents WHERE name IN ('memo_tokens', 'verification_summary')")
            con.commit()
        finally:
            con.close()

    def test_routes_fall_back(self):
        r = self.get("/api/recommendation")
        self.assertEqual(r["token_index"], [])
        self.assertEqual(self.get("/api/consistency")["token_checks"], {})
        e = self.get("/api/evals")
        if e["verification_report"]:
            self.assertNotIn("disagreements", e["verification_report"])
        self.get("/api/overview")


if __name__ == "__main__":
    unittest.main()
