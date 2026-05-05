"""
threat_engine.py – SANKALP Threat Intelligence Overlay
Maps current operational capability against simulated adversary threat scenarios.
Clean, minimal, easily extensible.

Usage:
    from agents.threat_engine import ThreatEngine
    engine = ThreatEngine()
    report = engine.assess("two_front_war")
"""

import json
import os
import sqlite3
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger("threat_engine")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
IAF_GOLD  = os.path.join(BASE, "../data/processed/sankalp_gold.db")
ARMY_GOLD = os.path.join(BASE, "../data/processed/sankalp_army_gold.db")
NAVY_GOLD = os.path.join(BASE, "../data/processed/sankalp_navy_gold.db")
RULES     = os.path.join(BASE, "../data/processed/ontology_rules.json")


# ── Threat Scenario Catalogue ─────────────────────────────────────────────────
# Each scenario defines adversary pressure (what minimum assets we NEED) and
# a description for the R&D audience. Easily extend by adding new dicts.

THREAT_SCENARIOS: dict[str, dict] = {
    "northern_infiltration": {
        "label": "Northern Border Infiltration",
        "description": "Single-axis adversary push across LAC / LoC. Air superiority essential.",
        "required": {"iaf": 8, "army": 12, "navy": 0},
        "threat_level": "HIGH",
        "adversary": "Northern Neighbour",
        "primary_branch": "iaf",
    },
    "western_border_strike": {
        "label": "Western Border Strike Threat",
        "description": "Cross-border armour + air threat from western adversary. Joint response needed.",
        "required": {"iaf": 6, "army": 15, "navy": 0},
        "threat_level": "HIGH",
        "adversary": "Western Neighbour",
        "primary_branch": "army",
    },
    "two_front_war": {
        "label": "Two-Front War Simulation",
        "description": "Simultaneous pressure on northern and western borders. Maximum joint-force demand.",
        "required": {"iaf": 14, "army": 25, "navy": 5},
        "threat_level": "CRITICAL",
        "adversary": "Dual Adversary",
        "primary_branch": "all",
    },
    "southern_sea_threat": {
        "label": "Southern Sea Lane Interdiction",
        "description": "Adversary naval blockade attempt on western sea lanes. Navy + IAF response.",
        "required": {"iaf": 4, "army": 0, "navy": 10},
        "threat_level": "MEDIUM",
        "adversary": "Sea-Based Actor",
        "primary_branch": "navy",
    },
    "cyber_plus_border": {
        "label": "Hybrid Cyber + Border Intrusion",
        "description": "Low-intensity combined cyber and physical border probe. Minimal asset draw.",
        "required": {"iaf": 3, "army": 5, "navy": 2},
        "threat_level": "MEDIUM",
        "adversary": "Hybrid Actor",
        "primary_branch": "army",
    },
    "island_territory_dispute": {
        "label": "Andaman Island Territory Dispute",
        "description": "Naval power projection in Andaman Sea. Navy-led, IAF air cover.",
        "required": {"iaf": 5, "army": 0, "navy": 8},
        "threat_level": "MEDIUM",
        "adversary": "Eastern Maritime Actor",
        "primary_branch": "navy",
    },
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class BranchCapability:
    branch: str
    total: int
    operational: int
    avg_readiness: float


@dataclass
class ThreatAssessment:
    scenario_id: str
    scenario_label: str
    threat_level: str
    adversary: str
    description: str
    required: dict
    capability: dict          # {"iaf": BranchCapability, ...}
    gap: dict                 # {"iaf": int, ...}  — negative = surplus
    verdict: str              # "CAPABLE" | "MARGINAL" | "INSUFFICIENT"
    coverage_pct: float       # 0-100 overall capability coverage
    risk_factors: list[str]
    recommendations: list[str]
    assessed_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["capability"] = {k: v.__dict__ for k, v in self.capability.items()}
        return d


# ── Engine ────────────────────────────────────────────────────────────────────

class ThreatEngine:
    """
    Minimal threat intelligence engine.
    Reads from SQLite gold stores (no Neo4j dependency) for maximum reliability.
    """

    def __init__(self, threshold: Optional[int] = None):
        self.threshold = threshold or self._load_threshold()

    # ── Public API ─────────────────────────────────────────────────────────────

    def list_scenarios(self) -> list[dict]:
        """Return all scenario metadata (no assessment)."""
        return [
            {"id": sid, **{k: v for k, v in s.items() if k != "required"}}
            for sid, s in THREAT_SCENARIOS.items()
        ]

    def assess(self, scenario_id: str) -> ThreatAssessment:
        """Full assessment of a named scenario against live fleet data."""
        if scenario_id not in THREAT_SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario_id}'. "
                             f"Available: {list(THREAT_SCENARIOS.keys())}")
        scenario = THREAT_SCENARIOS[scenario_id]
        caps     = self._load_capabilities()
        required = scenario["required"]

        # Gap analysis
        gap = {
            "iaf":  caps["iaf"].operational  - required["iaf"],
            "army": caps["army"].operational - required["army"],
            "navy": caps["navy"].operational - required["navy"],
        }

        # Coverage percentage (weighted by required assets)
        total_required = sum(required.values()) or 1
        total_met      = sum(
            min(caps[b].operational, required[b]) for b in ("iaf", "army", "navy")
        )
        coverage = round((total_met / total_required) * 100, 1)

        # Verdict
        shortfalls = [b for b, g in gap.items() if g < 0 and required[b] > 0]
        if not shortfalls:
            verdict = "CAPABLE"
        elif coverage >= 70:
            verdict = "MARGINAL"
        else:
            verdict = "INSUFFICIENT"

        # Risk factors
        risks = self._build_risks(scenario, caps, gap, required)

        # Recommendations
        recs = self._build_recommendations(scenario, caps, gap, required)

        return ThreatAssessment(
            scenario_id    = scenario_id,
            scenario_label = scenario["label"],
            threat_level   = scenario["threat_level"],
            adversary      = scenario["adversary"],
            description    = scenario["description"],
            required       = required,
            capability     = caps,
            gap            = gap,
            verdict        = verdict,
            coverage_pct   = coverage,
            risk_factors   = risks,
            recommendations= recs,
        )

    def assess_all(self) -> list[ThreatAssessment]:
        """Assess every scenario and return sorted by coverage (worst first)."""
        results = []
        for sid in THREAT_SCENARIOS:
            try:
                results.append(self.assess(sid))
            except Exception as e:
                logger.error(f"Assessment failed for {sid}: {e}")
        results.sort(key=lambda x: x.coverage_pct)
        return results

    def add_scenario(self, scenario_id: str, scenario: dict) -> None:
        """Add a custom threat scenario at runtime."""
        required_keys = {"label", "description", "required", "threat_level", "adversary", "primary_branch"}
        if not required_keys.issubset(scenario.keys()):
            raise ValueError(f"Missing keys: {required_keys - scenario.keys()}")
        THREAT_SCENARIOS[scenario_id] = scenario

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_threshold(self) -> int:
        try:
            with open(RULES) as f:
                return json.load(f).get("__global_settings__", {}).get("operational_threshold", 5)
        except Exception:
            return 5

    def _load_capabilities(self) -> dict[str, BranchCapability]:
        caps = {}

        def _cap(db, readiness_table, gold_table, score_col, branch):
            rows = _sql(db, f"SELECT {score_col} AS s FROM {readiness_table}")
            if not rows:
                rows = _sql(db, f"SELECT readiness_base_score AS s FROM {gold_table}")
            scores = [r["s"] or 0 for r in rows]
            op = sum(1 for s in scores if s >= self.threshold)
            avg = round(sum(scores) / len(scores), 1) if scores else 0
            return BranchCapability(branch=branch, total=len(scores), operational=op, avg_readiness=avg)

        caps["iaf"]  = _cap(IAF_GOLD,  "aircraft_readiness", "aircraft_gold",
                            "final_readiness_score", "iaf")
        caps["army"] = _cap(ARMY_GOLD, "asset_readiness",    "assets_gold",
                            "final_readiness_score", "army")
        caps["navy"] = _cap(NAVY_GOLD, "vessel_readiness",   "vessels_gold",
                            "final_readiness_score", "navy")
        return caps

    def _build_risks(self, scenario, caps, gap, required) -> list[str]:
        risks = []
        threat = scenario["threat_level"]

        for branch in ("iaf", "army", "navy"):
            if required[branch] == 0:
                continue
            bc = caps[branch]
            if gap[branch] < 0:
                risks.append(
                    f"⚠️ {branch.upper()} shortfall of {abs(gap[branch])} assets "
                    f"(has {bc.operational}, needs {required[branch]})"
                )
            if bc.avg_readiness < 50:
                risks.append(
                    f"⚠️ {branch.upper()} avg readiness {bc.avg_readiness}% — "
                    f"fleet fatigue risk under sustained {threat} threat"
                )

        if threat == "CRITICAL" and any(gap[b] < 0 for b in ("iaf", "army", "navy")):
            risks.append("🔴 CRITICAL scenario with asset shortfall — force escalation risk is HIGH")

        return risks or ["✅ No significant risk factors identified"]

    def _build_recommendations(self, scenario, caps, gap, required) -> list[str]:
        recs = []
        for branch in ("iaf", "army", "navy"):
            if required[branch] == 0:
                continue
            if gap[branch] < 0:
                recs.append(
                    f"Prioritise {branch.upper()} maintenance to recover "
                    f"{abs(gap[branch])} additional operational assets"
                )
            elif gap[branch] < 3:
                recs.append(
                    f"Monitor {branch.upper()} readiness — surplus of only {gap[branch]} "
                    f"leaves minimal buffer for this scenario"
                )

        if not recs:
            recs.append("Current fleet posture is adequate. Maintain scheduled readiness cycles.")

        return recs


# ── SQLite helper ─────────────────────────────────────────────────────────────

def _sql(db_path: str, sql: str) -> list[dict]:
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"SQL error on {db_path}: {e}")
        return []


# ── Standalone run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pprint
    logging.basicConfig(level=logging.INFO)
    engine = ThreatEngine()

    print("\n=== SANKALP Threat Intelligence Engine ===\n")
    print(f"Available scenarios: {[s['id'] for s in engine.list_scenarios()]}\n")

    for sid in THREAT_SCENARIOS:
        try:
            a = engine.assess(sid)
            verdict_icon = {"CAPABLE": "✅", "MARGINAL": "🟡", "INSUFFICIENT": "🔴"}.get(a.verdict, "")
            print(f"{verdict_icon} [{a.threat_level}] {a.scenario_label}: "
                  f"{a.verdict} ({a.coverage_pct}% coverage)")
        except Exception as e:
            print(f"  Error: {e}")
