"""
tests/test_automation_engine.py
================================
Run with:  python -m pytest tests/test_automation_engine.py -v
Or:        python tests/test_automation_engine.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Allow importing from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agents"))

# ── override DB path to a temp file for tests ─────────────────────────────────
_TMP_DIR  = tempfile.mkdtemp()
_AUTO_DB  = os.path.join(_TMP_DIR, "test_automation.db")
_GOLD_IAF = os.path.join(_TMP_DIR, "test_iaf_gold.db")

os.environ["AUTOMATION_DB"] = _AUTO_DB
os.environ["IAF_GOLD_DB"]   = _GOLD_IAF
os.environ["ARMY_GOLD_DB"]  = os.path.join(_TMP_DIR, "test_army_gold.db")
os.environ["NAVY_GOLD_DB"]  = os.path.join(_TMP_DIR, "test_navy_gold.db")

# Import AFTER env vars are set
from agents.automation_engine import (  # noqa: E402
    _now, _cooldown_ok, _log_event, _eval_score_below, _eval_score_above,
    _eval_days_since_maintenance, add_rule, delete_rule, get_rule,
    list_rules, update_rule, list_events, run_evaluation_cycle, init_db,
    _DEFAULT_RULES,
)


# ════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════════════════

def _seed_iaf_gold(scores: list[tuple[str, float, str]]):
    """seed aircraft_readiness table — (aircraft_id, score, maint_date)"""
    conn = sqlite3.connect(_GOLD_IAF)
    conn.execute("DROP TABLE IF EXISTS aircraft_readiness")
    conn.execute("""
        CREATE TABLE aircraft_readiness (
            aircraft_id TEXT, final_readiness_score REAL,
            last_maintenance_date TEXT,
            aircraft_type TEXT, squadron TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO aircraft_readiness VALUES (?,?,?,?,?)",
        [(ac, sc, dt, "Su-30MKI", "Tigers") for ac, sc, dt in scores],
    )
    conn.commit(); conn.close()


_SAMPLE_RULE = {
    "name":          "Test score_below rule",
    "description":   "Unit test rule",
    "branch":        "iaf",
    "trigger_type":  "score_below",
    "trigger_value": 40.0,
    "action_type":   "log_event",
    "action_payload": {"severity": "WARNING", "message": "Test {entity_id} val={actual_value:.1f}"},
    "cooldown_min":  0,
    "enabled":       True,
}


# ════════════════════════════════════════════════════════════════════════════
#  TEST CASES
# ════════════════════════════════════════════════════════════════════════════

class TestDatabaseInit(unittest.TestCase):
    def test_init_creates_tables(self):
        init_db()
        conn = sqlite3.connect(_AUTO_DB)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        self.assertIn("automation_rules", tables)
        self.assertIn("automation_events", tables)

    def test_default_rules_seeded(self):
        init_db()
        rules = list_rules()
        ids = {r["rule_id"] for r in rules}
        for d in _DEFAULT_RULES:
            self.assertIn(d["rule_id"], ids, f"Default rule {d['rule_id']} not seeded")


class TestRuleCRUD(unittest.TestCase):
    def setUp(self):
        init_db()

    def test_add_and_get_rule(self):
        ok, rule_id = add_rule(_SAMPLE_RULE)
        self.assertTrue(ok, f"add_rule failed: {rule_id}")
        rule = get_rule(rule_id)
        self.assertIsNotNone(rule)
        self.assertEqual(rule["name"], _SAMPLE_RULE["name"])
        self.assertAlmostEqual(rule["trigger_value"], 40.0)
        self.assertIsInstance(rule["action_payload"], dict)
        # cleanup
        delete_rule(rule_id)

    def test_add_rule_missing_name_fails_gracefully(self):
        bad = dict(_SAMPLE_RULE)
        del bad["name"]
        ok, err = add_rule(bad)
        self.assertFalse(ok)

    def test_update_rule(self):
        ok, rule_id = add_rule(_SAMPLE_RULE)
        self.assertTrue(ok)
        ok2, _ = update_rule(rule_id, {"trigger_value": 99.0, "enabled": 0})
        self.assertTrue(ok2)
        rule = get_rule(rule_id)
        self.assertAlmostEqual(rule["trigger_value"], 99.0)
        self.assertEqual(rule["enabled"], 0)
        delete_rule(rule_id)

    def test_delete_rule(self):
        ok, rule_id = add_rule(_SAMPLE_RULE)
        self.assertTrue(ok)
        ok2, _ = delete_rule(rule_id)
        self.assertTrue(ok2)
        self.assertIsNone(get_rule(rule_id))

    def test_list_rules_enabled_only(self):
        ok, rid = add_rule({**_SAMPLE_RULE, "enabled": False})
        self.assertTrue(ok)
        enabled_rules = list_rules(enabled_only=True)
        ids = [r["rule_id"] for r in enabled_rules]
        self.assertNotIn(rid, ids)
        delete_rule(rid)


class TestCooldown(unittest.TestCase):
    def setUp(self):
        init_db()
        ok, self.rule_id = add_rule(_SAMPLE_RULE)

    def tearDown(self):
        delete_rule(self.rule_id)

    def test_no_prior_event_passes(self):
        rule = get_rule(self.rule_id)
        self.assertTrue(_cooldown_ok(self.rule_id, "TEST-001", 60))

    def test_recent_event_blocks(self):
        rule = get_rule(self.rule_id)
        _log_event(rule, "iaf", "TEST-002", "Aircraft", 40.0, 25.0, "test")
        self.assertFalse(_cooldown_ok(self.rule_id, "TEST-002", 120))

    def test_zero_cooldown_always_passes(self):
        rule = get_rule(self.rule_id)
        _log_event(rule, "iaf", "TEST-003", "Aircraft", 40.0, 25.0, "test")
        self.assertTrue(_cooldown_ok(self.rule_id, "TEST-003", 0))


class TestEvaluators(unittest.TestCase):
    def setUp(self):
        init_db()
        today      = datetime.now(tz=__import__("datetime").timezone.utc).date().isoformat()
        old_date   = (datetime.now(tz=__import__("datetime").timezone.utc) - timedelta(days=200)).date().isoformat()
        _seed_iaf_gold([
            ("AC-001", 20.0, old_date),   # critical — below 30 AND overdue
            ("AC-002", 60.0, today),       # fine
            ("AC-003", 35.0, today),       # below 40 but not below 30
        ])

    def _make_rule(self, trigger_type: str, threshold: float) -> dict:
        return {
            "rule_id":       f"tmp_{trigger_type}",
            "name":          "tmp",
            "branch":        "iaf",
            "trigger_type":  trigger_type,
            "trigger_value": threshold,
            "action_type":   "log_event",
            "action_payload": {"severity": "INFO", "message": "test {entity_id}"},
            "cooldown_min":  0,
            "enabled":       1,
        }

    def test_score_below_finds_critical(self):
        rule = self._make_rule("score_below", 30.0)
        hits = _eval_score_below(rule)
        ids = [h["entity_id"] for h in hits]
        self.assertIn("AC-001", ids)
        self.assertNotIn("AC-002", ids)
        self.assertNotIn("AC-003", ids)

    def test_score_below_watch_threshold(self):
        rule = self._make_rule("score_below", 40.0)
        hits = _eval_score_below(rule)
        ids = [h["entity_id"] for h in hits]
        self.assertIn("AC-001", ids)
        self.assertIn("AC-003", ids)
        self.assertNotIn("AC-002", ids)

    def test_score_above(self):
        rule = self._make_rule("score_above", 50.0)
        hits = _eval_score_above(rule)
        ids = [h["entity_id"] for h in hits]
        self.assertIn("AC-002", ids)
        self.assertNotIn("AC-001", ids)

    def test_days_since_maintenance(self):
        rule = self._make_rule("days_since_maintenance", 100.0)
        hits = _eval_days_since_maintenance(rule)
        ids = [h["entity_id"] for h in hits]
        self.assertIn("AC-001", ids)
        self.assertNotIn("AC-002", ids)


class TestEvaluationCycle(unittest.TestCase):
    """
    Cycle tests mock the Neo4j driver so they run without a live Neo4j instance.
    The mock returns None (offline), which causes _action_create_alert_node to
    fall back to a safe 'neo4j_offline | logged: …' result — still logs to SQLite.
    """

    def setUp(self):
        init_db()
        today = datetime.now(tz=__import__("datetime").timezone.utc).date().isoformat()
        _seed_iaf_gold([
            ("AC-CRIT", 15.0, today),
            ("AC-OK",   80.0, today),
        ])
        ok, self.rule_id = add_rule({
            **_SAMPLE_RULE,
            "rule_id":       "cycle_test_rule",
            "trigger_value": 30.0,
            "cooldown_min":  0,
        })

    def tearDown(self):
        delete_rule("cycle_test_rule")

    @patch("agents.automation_engine._get_neo4j_driver", return_value=None)
    def test_cycle_fires_for_critical_only(self, _mock):
        events = run_evaluation_cycle()
        entity_ids = [e["entity_id"] for e in events
                      if e["rule_id"] == "cycle_test_rule"]
        self.assertIn("AC-CRIT", entity_ids)
        self.assertNotIn("AC-OK", entity_ids)

    @patch("agents.automation_engine._get_neo4j_driver", return_value=None)
    def test_cycle_logs_event_to_db(self, _mock):
        run_evaluation_cycle()
        logged = list_events(rule_id="cycle_test_rule")
        self.assertGreater(len(logged), 0)
        ev = logged[0]
        self.assertEqual(ev["rule_id"], "cycle_test_rule")
        self.assertAlmostEqual(ev["actual_value"], 15.0, places=0)

    @patch("agents.automation_engine._get_neo4j_driver", return_value=None)
    def test_cooldown_prevents_double_fire(self, _mock):
        update_rule("cycle_test_rule", {"cooldown_min": 60})
        run_evaluation_cycle()
        events1 = list_events(rule_id="cycle_test_rule")
        run_evaluation_cycle()
        events2 = list_events(rule_id="cycle_test_rule")
        self.assertEqual(len(events1), len(events2))


class TestEventLog(unittest.TestCase):
    def setUp(self):
        init_db()
        ok, self.rule_id = add_rule(_SAMPLE_RULE)

    def tearDown(self):
        delete_rule(self.rule_id)

    def test_list_events_returns_dict_list(self):
        rule = get_rule(self.rule_id)
        _log_event(rule, "iaf", "AC-LOG", "Aircraft", 30.0, 20.0, "test_result")
        events = list_events(limit=10)
        self.assertIsInstance(events, list)
        self.assertIsInstance(events[0], dict)
        self.assertIn("entity_id", events[0])

    def test_list_events_branch_filter(self):
        rule = get_rule(self.rule_id)
        _log_event(rule, "navy", "VES-001", "Vessel", 30.0, 18.0, "test")
        iaf_events = list_events(branch="iaf")
        navy_events = list_events(branch="navy")
        for ev in iaf_events:
            self.assertEqual(ev["branch"], "iaf")
        for ev in navy_events:
            self.assertEqual(ev["branch"], "navy")


# ════════════════════════════════════════════════════════════════════════════
#  RUNNER
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  SANKALP Automation Engine — Test Suite")
    print("=" * 60)
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
