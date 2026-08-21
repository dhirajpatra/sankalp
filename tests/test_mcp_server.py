"""
tests/test_mcp_server.py
=========================
Run with:  python -m pytest tests/test_mcp_server.py -v
Or:        python tests/test_mcp_server.py

Runs fully offline against temp SQLite "gold" databases seeded per test — no
live Neo4j instance, Docker, or GROQ_API_KEY required. Mirrors the fixture
pattern used in tests/test_automation_engine.py.

mcp_server.py resolves its DB paths at import time from its own file location,
so these tests point the module's globals at temp files after import rather
than via env vars (mcp_server.py itself doesn't read env vars for DB paths).
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mcp_server as srv  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════════════════

_TMP_DIR = tempfile.mkdtemp()


def _seed_readiness(db_path: str, table: str, id_col: str, type_col: str,
                     unit_col: str, rows: list[tuple[str, str, str, float]]):
    """rows: list of (id, type, unit, final_readiness_score)"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(f"""
        CREATE TABLE {table} (
            {id_col} TEXT, {type_col} TEXT, {unit_col} TEXT,
            final_readiness_score REAL
        )
    """)
    conn.executemany(
        f"INSERT INTO {table} VALUES (?,?,?,?)", rows,
    )
    conn.commit()
    conn.close()


def _write_rules(rules: dict):
    os.makedirs(os.path.dirname(srv.RULES), exist_ok=True)
    with open(srv.RULES, "w") as f:
        json.dump(rules, f)


class McpServerTestBase(unittest.TestCase):
    """Points the mcp_server module's DB/rules globals at temp files."""

    def setUp(self):
        self._orig = {
            "IAF_GOLD": srv.IAF_GOLD, "ARMY_GOLD": srv.ARMY_GOLD,
            "NAVY_GOLD": srv.NAVY_GOLD, "RULES": srv.RULES,
        }
        # Fresh, uniquely-named DB files per test so state never leaks
        # between test methods (each seeds its own tables from scratch).
        case_dir = tempfile.mkdtemp(dir=_TMP_DIR)
        srv.IAF_GOLD = os.path.join(case_dir, "test_iaf_gold.db")
        srv.ARMY_GOLD = os.path.join(case_dir, "test_army_gold.db")
        srv.NAVY_GOLD = os.path.join(case_dir, "test_navy_gold.db")
        srv.RULES = os.path.join(case_dir, "test_ontology_rules.json")

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(srv, k, v)


# ════════════════════════════════════════════════════════════════════════════
#  TEST CASES
# ════════════════════════════════════════════════════════════════════════════

class TestGetFleetReadiness(McpServerTestBase):
    def test_empty_dbs_return_zeroed_summary(self):
        result = json.loads(srv.get_fleet_readiness())
        for branch in ("iaf", "army", "navy"):
            self.assertEqual(result[branch]["total"], 0)
            self.assertEqual(result[branch]["avg_readiness"], 0)

    def test_summarizes_operational_watch_critical_buckets(self):
        _write_rules({"__global_settings__": {"operational_threshold": 50}})
        _seed_readiness(
            srv.IAF_GOLD, "aircraft_readiness",
            "aircraft_id", "aircraft_type", "squadron",
            [
                ("AC-1", "Su-30MKI", "Tigers", 80.0),   # operational (>=50)
                ("AC-2", "Su-30MKI", "Tigers", 35.0),   # watch (30-49)
                ("AC-3", "Su-30MKI", "Tigers", 10.0),   # critical (<30)
            ],
        )
        result = json.loads(srv.get_fleet_readiness())
        self.assertEqual(result["operational_threshold"], 50)
        self.assertEqual(result["iaf"]["total"], 3)
        self.assertEqual(result["iaf"]["operational"], 1)
        self.assertEqual(result["iaf"]["watch"], 1)
        self.assertEqual(result["iaf"]["critical"], 1)
        self.assertAlmostEqual(result["iaf"]["avg_readiness"], (80 + 35 + 10) / 3, places=1)

    def test_army_and_navy_independent_of_iaf(self):
        _seed_readiness(
            srv.ARMY_GOLD, "asset_readiness",
            "asset_id", "asset_type", "unit",
            [("AR-1", "Tank", "1 Corps", 60.0)],
        )
        result = json.loads(srv.get_fleet_readiness())
        self.assertEqual(result["army"]["total"], 1)
        self.assertEqual(result["iaf"]["total"], 0)
        self.assertEqual(result["navy"]["total"], 0)


class TestGetCriticalAssets(McpServerTestBase):
    def setUp(self):
        super().setUp()
        _seed_readiness(
            srv.IAF_GOLD, "aircraft_readiness",
            "aircraft_id", "aircraft_type", "squadron",
            [
                ("AC-LOW", "Su-30MKI", "Tigers", 15.0),
                ("AC-HIGH", "Su-30MKI", "Tigers", 90.0),
            ],
        )
        _seed_readiness(
            srv.ARMY_GOLD, "asset_readiness",
            "asset_id", "asset_type", "unit",
            [("AR-LOW", "Tank", "1 Corps", 20.0)],
        )

    def test_filters_below_default_threshold(self):
        result = json.loads(srv.get_critical_assets(branch="iaf"))
        ids = [r["id"] for r in result]
        self.assertIn("AC-LOW", ids)
        self.assertNotIn("AC-HIGH", ids)

    def test_branch_all_includes_every_branch(self):
        result = json.loads(srv.get_critical_assets(branch="all"))
        ids = {r["id"] for r in result}
        self.assertIn("AC-LOW", ids)
        self.assertIn("AR-LOW", ids)

    def test_no_critical_assets_returns_message(self):
        result = srv.get_critical_assets(branch="iaf", threshold=1)
        self.assertEqual(result, "No critical assets found.")

    def test_results_sorted_ascending_by_score(self):
        _seed_readiness(
            srv.IAF_GOLD, "aircraft_readiness",
            "aircraft_id", "aircraft_type", "squadron",
            [
                ("AC-A", "Su-30MKI", "Tigers", 25.0),
                ("AC-B", "Su-30MKI", "Tigers", 5.0),
            ],
        )
        result = json.loads(srv.get_critical_assets(branch="iaf"))
        scores = [r["score"] for r in result]
        self.assertEqual(scores, sorted(scores))


class TestEvaluateDoctrine(McpServerTestBase):
    def test_no_match_lists_available_actions(self):
        _write_rules({
            "__global_settings__": {"operational_threshold": 5},
            "protect northern border": {"description": "d", "iaf_min_operational": 1,
                                          "army_min_operational": 1, "navy_min_operational": 1,
                                          "logic_mode": "standard"},
        })
        result = json.loads(srv.evaluate_doctrine("nonexistent"))
        self.assertIn("error", result)
        self.assertIn("protect northern border", result["available"])

    def test_partial_name_match_and_verdict(self):
        _write_rules({
            "__global_settings__": {"operational_threshold": 5},
            "protect northern border": {"description": "d", "iaf_min_operational": 1,
                                          "army_min_operational": 0, "navy_min_operational": 0,
                                          "logic_mode": "standard"},
        })
        _seed_readiness(
            srv.IAF_GOLD, "aircraft_readiness",
            "aircraft_id", "aircraft_type", "squadron",
            [("AC-1", "Su-30MKI", "Tigers", 90.0)],
        )
        result = json.loads(srv.evaluate_doctrine("northern"))
        self.assertEqual(result["action"], "protect northern border")
        self.assertEqual(result["verdict"], "ADEQUATE")


class TestListDoctrineRules(McpServerTestBase):
    def test_excludes_global_settings(self):
        _write_rules({
            "__global_settings__": {"operational_threshold": 5},
            "action one": {"description": "d", "iaf_min_operational": 1,
                            "army_min_operational": 1, "navy_min_operational": 1,
                            "logic_mode": "standard"},
        })
        result = json.loads(srv.list_doctrine_rules())
        names = [r["action"] for r in result]
        self.assertIn("action one", names)
        self.assertNotIn("__global_settings__", names)


# ════════════════════════════════════════════════════════════════════════════
#  RUNNER
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  SANKALP MCP Server — Test Suite")
    print("=" * 60)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
