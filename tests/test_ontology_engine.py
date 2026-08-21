"""
tests/test_ontology_engine.py
==============================
Run with:  python -m pytest tests/test_ontology_engine.py -v
Or:        python tests/test_ontology_engine.py

Runs fully offline: no live Neo4j connection is attempted (get_current_capabilities
is monkeypatched per-test) and no GROQ_API_KEY is required, since these tests only
exercise the deterministic rule CRUD / evaluation paths.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Allow importing from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agents"))

# Neo4j driver must never be dialed during these tests.
os.environ.setdefault("NEO4J_PASSWORD", "test-only-not-a-real-secret")

from agents import ontology_engine as oe  # noqa: E402
import ontology_rag  # noqa: E402 — imported so we can neutralize its side effect below


# ════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════════════════

_TMP_DIR = tempfile.mkdtemp()
_RULES_FILE = os.path.join(_TMP_DIR, "test_ontology_rules.json")

_STANDARD_RULE = {
    "description": "Requires all three branches at minimum strength.",
    "iaf_min_operational": 5,
    "army_min_operational": 5,
    "navy_min_operational": 5,
    "iaf_sufficient_alone": False,
    "army_enhances": False,
    "army_enhancement_threshold": 0,
    "logic_mode": "standard",
}

_TIERED_RULE = {
    "description": "IAF alone handles it; Army >=10 upgrades to SUPERIOR.",
    "iaf_min_operational": 3,
    "army_min_operational": 0,
    "navy_min_operational": 0,
    "iaf_sufficient_alone": True,
    "army_enhances": True,
    "army_enhancement_threshold": 10,
    "logic_mode": "iaf_primary_army_superior",
}


def _write_rules(rules: dict):
    os.makedirs(os.path.dirname(_RULES_FILE), exist_ok=True)
    with open(_RULES_FILE, "w") as f:
        json.dump(rules, f)


def _reset_rules():
    _write_rules({
        "__global_settings__": {"operational_threshold": 5},
        "standard action": dict(_STANDARD_RULE),
        "tiered action": dict(_TIERED_RULE),
    })


# ════════════════════════════════════════════════════════════════════════════
#  TEST CASES
# ════════════════════════════════════════════════════════════════════════════

class TestRuleCRUD(unittest.TestCase):
    def setUp(self):
        _reset_rules()
        self._patch = patch.object(oe, "RULES_FILE", _RULES_FILE)
        self._patch.start()
        # save_rules() -> invalidate_index() resolves its own INDEX/META
        # paths from config.yml independently of RULES_FILE, so without this
        # it deletes the *real* data/processed/ontology_rag* files on disk.
        # Neutralize it here so the test suite has zero side effects outside
        # its own temp directory.
        self._rag_patch = patch.object(ontology_rag, "invalidate_index")
        self._rag_patch.start()

    def tearDown(self):
        self._patch.stop()
        self._rag_patch.stop()

    def test_add_rule(self):
        ok, msg = oe.add_rule(
            "new action", "desc", iaf_min=1, army_min=2, navy_min=3,
        )
        self.assertTrue(ok, msg)
        rules = oe.load_rules()
        self.assertIn("new action", rules)
        self.assertEqual(rules["new action"]["iaf_min_operational"], 1)
        self.assertEqual(rules["new action"]["logic_mode"], "standard")

    def test_add_rule_tiered_logic_mode(self):
        ok, _ = oe.add_rule(
            "air superiority", "desc", iaf_min=3, army_min=0, navy_min=0,
            iaf_sufficient_alone=True, army_enhances=True,
            army_enhancement_threshold=10,
        )
        self.assertTrue(ok)
        rules = oe.load_rules()
        self.assertEqual(rules["air superiority"]["logic_mode"], "iaf_primary_army_superior")

    def test_add_rule_empty_name_fails(self):
        ok, msg = oe.add_rule("   ", "desc", 1, 1, 1)
        self.assertFalse(ok)

    def test_add_rule_duplicate_fails(self):
        ok, msg = oe.add_rule("standard action", "dup", 1, 1, 1)
        self.assertFalse(ok)
        self.assertIn("already exists", msg)

    def test_add_rule_lowercases_and_strips_name(self):
        ok, _ = oe.add_rule("  Mixed CASE Name  ", "desc", 1, 1, 1)
        self.assertTrue(ok)
        rules = oe.load_rules()
        self.assertIn("mixed case name", rules)

    def test_delete_rule(self):
        ok, msg = oe.delete_rule("standard action")
        self.assertTrue(ok, msg)
        self.assertNotIn("standard action", oe.load_rules())

    def test_delete_missing_rule_fails(self):
        ok, msg = oe.delete_rule("does not exist")
        self.assertFalse(ok)
        self.assertIn("not found", msg)

    def test_cannot_delete_global_settings(self):
        ok, msg = oe.delete_rule("__global_settings__")
        self.assertFalse(ok)
        self.assertIn("global settings", msg)


class TestThreshold(unittest.TestCase):
    def setUp(self):
        _reset_rules()
        self._patch = patch.object(oe, "RULES_FILE", _RULES_FILE)
        self._patch.start()
        self._rag_patch = patch.object(ontology_rag, "invalidate_index")
        self._rag_patch.start()

    def tearDown(self):
        self._patch.stop()
        self._rag_patch.stop()

    def test_get_default_threshold(self):
        self.assertEqual(oe.get_operational_threshold(), 5)

    @patch.object(oe, "update_neo4j_operational_status")
    def test_set_threshold_persists(self, _mock_neo4j):
        oe.set_operational_threshold(8)
        self.assertEqual(oe.get_operational_threshold(), 8)
        _mock_neo4j.assert_called_once_with(8)


class TestEvaluateAction(unittest.TestCase):
    """
    evaluate_action() calls get_current_capabilities(), which normally hits
    Neo4j. We patch it directly so these tests are deterministic and never
    touch a live database.
    """

    def setUp(self):
        _reset_rules()
        self._rules_patch = patch.object(oe, "RULES_FILE", _RULES_FILE)
        self._rules_patch.start()

    def tearDown(self):
        self._rules_patch.stop()

    def test_unknown_action_is_insufficient(self):
        can_execute, reasons, tier = oe.evaluate_action("nonexistent action")
        self.assertFalse(can_execute)
        self.assertEqual(tier, "INSUFFICIENT")

    @patch.object(oe, "get_current_capabilities",
                  return_value={"iaf_op": 5, "army_op": 5, "navy_op": 5})
    def test_standard_mode_all_minimums_met(self, _mock_caps):
        can_execute, reasons, tier = oe.evaluate_action("standard action")
        self.assertTrue(can_execute)
        self.assertEqual(tier, "ADEQUATE")

    @patch.object(oe, "get_current_capabilities",
                  return_value={"iaf_op": 5, "army_op": 1, "navy_op": 5})
    def test_standard_mode_one_branch_short(self, _mock_caps):
        can_execute, reasons, tier = oe.evaluate_action("standard action")
        self.assertFalse(can_execute)
        self.assertEqual(tier, "INSUFFICIENT")
        self.assertTrue(any("Army" in r and "BELOW" in r for r in reasons))

    @patch.object(oe, "get_current_capabilities",
                  return_value={"iaf_op": 3, "army_op": 0, "navy_op": 0})
    def test_tiered_mode_iaf_only_is_adequate(self, _mock_caps):
        can_execute, reasons, tier = oe.evaluate_action("tiered action")
        self.assertTrue(can_execute)
        self.assertEqual(tier, "ADEQUATE")

    @patch.object(oe, "get_current_capabilities",
                  return_value={"iaf_op": 3, "army_op": 12, "navy_op": 0})
    def test_tiered_mode_iaf_and_army_is_superior(self, _mock_caps):
        can_execute, reasons, tier = oe.evaluate_action("tiered action")
        self.assertTrue(can_execute)
        self.assertEqual(tier, "SUPERIOR")

    @patch.object(oe, "get_current_capabilities",
                  return_value={"iaf_op": 0, "army_op": 12, "navy_op": 0})
    def test_tiered_mode_iaf_below_min_is_insufficient(self, _mock_caps):
        can_execute, reasons, tier = oe.evaluate_action("tiered action")
        self.assertFalse(can_execute)
        self.assertEqual(tier, "INSUFFICIENT")


class TestGetCurrentCapabilitiesOffline(unittest.TestCase):
    """get_current_capabilities() must fail safe (not raise) when Neo4j is unreachable."""

    @patch.object(oe, "get_neo4j_driver", side_effect=ConnectionError("no neo4j in CI"))
    def test_returns_zeroed_caps_on_connection_failure(self, _mock_driver):
        caps = oe.get_current_capabilities()
        self.assertEqual(caps, {"iaf_op": 0, "army_op": 0, "navy_op": 0})


# ════════════════════════════════════════════════════════════════════════════
#  RUNNER
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  SANKALP Ontology Engine — Test Suite")
    print("=" * 60)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
