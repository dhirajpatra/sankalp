"""
yojana.py – SANKALP Mission Planning Agent (योजना — Plan / Resolve)
Forward-looking agent: recommends optimal asset-crew pairings for upcoming missions.

Usage:
    from agents.yojana import MissionPlanner
    planner = MissionPlanner()
    plan = planner.plan(branch="iaf", mission_type="Strike", top_n=3)
"""

import sqlite3
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger("yojana")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
IAF_GOLD  = os.path.join(BASE, "../data/processed/sankalp_gold.db")
ARMY_GOLD = os.path.join(BASE, "../data/processed/sankalp_army_gold.db")
NAVY_GOLD = os.path.join(BASE, "../data/processed/sankalp_navy_gold.db")

# ── Mission type → required qualifications mapping ────────────────────────────
# Extend this dict to support new mission types without changing agent logic.
MISSION_QUALIFICATIONS: dict[str, dict] = {
    # IAF
    "Strike":            {"branch": "iaf",  "preferred_types": ["Su-30MKI", "Tejas", "MiG-29"],      "min_readiness": 60},
    "Combat Air Patrol": {"branch": "iaf",  "preferred_types": ["Su-30MKI", "MiG-29", "Tejas"],      "min_readiness": 55},
    "Reconnaissance":    {"branch": "iaf",  "preferred_types": ["MiG-25", "Heron UAV", "Tejas"],     "min_readiness": 50},
    "Air Defence":       {"branch": "iaf",  "preferred_types": ["Su-30MKI", "MiG-21", "Tejas"],      "min_readiness": 65},
    "CAS":               {"branch": "iaf",  "preferred_types": ["Su-30MKI", "Tejas", "Mirage 2000"], "min_readiness": 60},
    "Intercept":         {"branch": "iaf",  "preferred_types": ["Su-30MKI", "MiG-29"],               "min_readiness": 70},
    "Logistics":         {"branch": "iaf",  "preferred_types": ["C-17", "AN-32", "IL-76"],           "min_readiness": 40},
    "Training":          {"branch": "iaf",  "preferred_types": [],                                   "min_readiness": 30},

    # Army
    "Patrol":            {"branch": "army", "preferred_types": ["BMP-2 Sarath", "T-90 Bhishma"],     "min_readiness": 40},
    "Border Vigil":      {"branch": "army", "preferred_types": ["T-90 Bhishma", "BMP-2 Sarath"],     "min_readiness": 45},
    "Live Fire Exercise":{"branch": "army", "preferred_types": ["K9 Vajra", "M777 Howitzer"],        "min_readiness": 50},
    "Strike Mission":    {"branch": "army", "preferred_types": ["Pinaka MLRS", "K9 Vajra"],          "min_readiness": 65},
    "Counter-Insurgency":{"branch": "army", "preferred_types": ["BMP-2 Sarath", "ALH Dhruv"],        "min_readiness": 55},
    "Recon":             {"branch": "army", "preferred_types": ["HAL Rudra", "ALH Dhruv"],           "min_readiness": 50},

    # Navy
    "Anti-Submarine Warfare": {"branch": "navy", "preferred_types": ["Kalvari-class Sub", "Sindhughosh-class Sub", "P-8I Poseidon"], "min_readiness": 60},
    "Fleet Exercise":    {"branch": "navy", "preferred_types": ["INS Vikrant (Carrier)", "INS Kolkata (Destroyer)"],  "min_readiness": 55},
    "Escort":            {"branch": "navy", "preferred_types": ["INS Shivalik (Frigate)", "INS Kolkata (Destroyer)"], "min_readiness": 50},
    "ISR":               {"branch": "navy", "preferred_types": ["P-8I Poseidon", "HAL Sea King"],    "min_readiness": 50},
    "Sortie Patrol":     {"branch": "navy", "preferred_types": ["INS Sukanya (OPV)"],                "min_readiness": 40},
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AssetRec:
    asset_id: str
    asset_type: str
    unit: str            # squadron / unit / flotilla
    readiness: float
    hours: float         # flight / operational / sea hours
    last_maintenance: str
    suitability_score: float  # composite score for ranking


@dataclass
class CrewRec:
    crew_id: str
    name: str
    rank: str
    qualified_on: str
    suitability_score: float


@dataclass
class MissionPlan:
    mission_type: str
    branch: str
    planned_date: str
    asset: AssetRec
    crew: CrewRec
    confidence: str      # "HIGH" | "MEDIUM" | "LOW"
    rationale: list[str]
    warnings: list[str]
    rank: int            # 1 = best recommendation

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["asset"] = self.asset.__dict__
        d["crew"]  = self.crew.__dict__
        return d


# ── Planner ───────────────────────────────────────────────────────────────────

class MissionPlanner:
    """
    Recommends optimal asset-crew pairings for an upcoming mission.
    Works purely from SQLite gold stores — no Neo4j required.
    """

    def plan(
        self,
        branch: str,
        mission_type: str,
        planned_date: Optional[str] = None,
        top_n: int = 3,
    ) -> list[MissionPlan]:
        """
        Return top_n ranked mission plans for the given branch + mission type.
        planned_date: ISO date string (defaults to tomorrow).
        """
        if planned_date is None:
            from datetime import timedelta
            planned_date = (date.today() + timedelta(days=1)).isoformat()

        spec = MISSION_QUALIFICATIONS.get(mission_type)
        if spec is None:
            raise ValueError(
                f"Unknown mission type '{mission_type}'. "
                f"Supported: {list(MISSION_QUALIFICATIONS.keys())}"
            )

        assets = self._load_assets(branch, spec["min_readiness"])
        crews  = self._load_crew(branch)

        if not assets:
            return []

        # Score assets
        for a in assets:
            a.suitability_score = self._score_asset(a, spec)

        assets.sort(key=lambda x: x.suitability_score, reverse=True)

        # Score crew
        for c in crews:
            c.suitability_score = self._score_crew(c, spec, branch)

        crews.sort(key=lambda x: x.suitability_score, reverse=True)

        # Pair top assets with top crew (greedy, no repeat crew)
        plans = []
        used_crew = set()
        for rank, asset in enumerate(assets[:top_n * 2], start=1):
            crew = next((c for c in crews if c.crew_id not in used_crew), None)
            if crew is None:
                break
            used_crew.add(crew.crew_id)

            rationale, warnings = self._build_rationale(asset, crew, spec, mission_type)
            confidence = self._confidence(asset, crew, spec)

            plans.append(MissionPlan(
                mission_type  = mission_type,
                branch        = branch,
                planned_date  = planned_date,
                asset         = asset,
                crew          = crew,
                confidence    = confidence,
                rationale     = rationale,
                warnings      = warnings,
                rank          = len(plans) + 1,
            ))

            if len(plans) >= top_n:
                break

        return plans

    def available_mission_types(self, branch: Optional[str] = None) -> list[str]:
        if branch:
            return [k for k, v in MISSION_QUALIFICATIONS.items() if v["branch"] == branch]
        return list(MISSION_QUALIFICATIONS.keys())

    # ── Loaders ───────────────────────────────────────────────────────────────

    def _load_assets(self, branch: str, min_readiness: float) -> list[AssetRec]:
        cfg = {
            "iaf":  (IAF_GOLD,  "aircraft_readiness", "aircraft_id", "aircraft_type",
                     "squadron", "final_readiness_score", "flight_hours", "last_maintenance_date"),
            "army": (ARMY_GOLD, "asset_readiness",    "asset_id",    "asset_type",
                     "unit",     "final_readiness_score", "operational_hours", "last_service_date"),
            "navy": (NAVY_GOLD, "vessel_readiness",   "vessel_id",   "vessel_type",
                     "flotilla", "final_readiness_score", "sea_hours", "last_refit_date"),
        }
        db, table, id_col, type_col, unit_col, score_col, hours_col, maint_col = cfg[branch]
        rows = _sql(db, f"""
            SELECT {id_col} AS asset_id, {type_col} AS asset_type, {unit_col} AS unit,
                   {score_col} AS readiness, {hours_col} AS hours, {maint_col} AS last_maintenance
            FROM {table}
            WHERE {score_col} >= {min_readiness}
            ORDER BY {score_col} DESC
        """)
        return [AssetRec(
            asset_id=r["asset_id"], asset_type=r["asset_type"], unit=r["unit"],
            readiness=float(r["readiness"] or 0), hours=float(r["hours"] or 0),
            last_maintenance=r["last_maintenance"] or "Unknown",
            suitability_score=0.0,
        ) for r in rows]

    def _load_crew(self, branch: str) -> list[CrewRec]:
        cfg = {
            "iaf":  (IAF_GOLD,  "crew_gold",       "crew_id", "name", "rank", "aircraft_type_qualified"),
            "army": (ARMY_GOLD, "army_crew_gold",   "crew_id", "name", "rank", "vehicle_qualified"),
            "navy": (NAVY_GOLD, "navy_crew_gold",   "crew_id", "name", "rank", "vessel_qualified"),
        }
        db, table, id_col, name_col, rank_col, qual_col = cfg[branch]
        rows = _sql(db, f"""
            SELECT {id_col} AS crew_id, {name_col} AS name, {rank_col} AS rank,
                   {qual_col} AS qualified_on
            FROM {table}
        """)
        return [CrewRec(
            crew_id=r["crew_id"], name=r["name"], rank=r["rank"],
            qualified_on=r["qualified_on"] or "",
            suitability_score=0.0,
        ) for r in rows]

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score_asset(self, asset: AssetRec, spec: dict) -> float:
        score = asset.readiness  # base: 0-100

        # Bonus if asset type matches preferred list
        preferred = spec.get("preferred_types", [])
        if any(p.lower() in asset.asset_type.lower() for p in preferred):
            score += 20

        # Penalise very high hours (fatigue)
        if asset.hours > 1200:
            score -= 15
        elif asset.hours > 800:
            score -= 5

        return round(min(score, 100), 2)

    def _score_crew(self, crew: CrewRec, spec: dict, branch: str) -> float:
        score = 50.0  # neutral base

        # Rank seniority bonus
        rank_bonus = {
            "Air Marshal": 30, "Air Vice Marshal": 25, "Air Commodore": 22,
            "Group Captain": 20, "Wing Commander": 18, "Squadron Leader": 15,
            "Flight Lieutenant": 10, "Flying Officer": 5,
            "General": 30, "Lieutenant General": 27, "Major General": 24,
            "Brigadier": 21, "Colonel": 18, "Lieutenant Colonel": 15,
            "Major": 12, "Captain": 9, "Lieutenant": 6,
            "Vice Admiral": 30, "Rear Admiral": 27, "Commodore": 22,
            "Commander": 18, "Lieutenant Commander": 14,
        }
        for title, bonus in rank_bonus.items():
            if title.lower() in crew.rank.lower():
                score += bonus
                break

        # Qualification match bonus
        preferred = spec.get("preferred_types", [])
        if any(p.lower() in crew.qualified_on.lower() for p in preferred):
            score += 25

        return round(min(score, 100), 2)

    def _confidence(self, asset: AssetRec, crew: CrewRec, spec: dict) -> str:
        combined = (asset.suitability_score + crew.suitability_score) / 2
        if combined >= 75:
            return "HIGH"
        if combined >= 50:
            return "MEDIUM"
        return "LOW"

    def _build_rationale(self, asset: AssetRec, crew: CrewRec, spec: dict, mission_type: str):
        rationale, warnings = [], []
        rationale.append(f"Asset {asset.asset_id} ({asset.asset_type}) readiness: {asset.readiness:.1f}%")
        rationale.append(f"Crew {crew.name} ({crew.rank}) qualified on: {crew.qualified_on}")

        preferred = spec.get("preferred_types", [])
        if any(p.lower() in asset.asset_type.lower() for p in preferred):
            rationale.append(f"Asset type is preferred for {mission_type}")
        else:
            warnings.append(f"Asset type may not be optimal for {mission_type}")

        if any(p.lower() in crew.qualified_on.lower() for p in preferred):
            rationale.append("Crew qualification matches mission asset type")
        else:
            warnings.append("Crew qualification may not perfectly match asset type")

        if asset.hours > 1200:
            warnings.append(f"High operational hours ({asset.hours:.0f}) — monitor for fatigue")

        return rationale, warnings


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
    logging.basicConfig(level=logging.INFO)
    planner = MissionPlanner()

    print("\n=== SANKALP Yojana — Mission Planning Agent ===\n")
    for branch, mtype in [("iaf", "Strike"), ("army", "Border Vigil"), ("navy", "Anti-Submarine Warfare")]:
        try:
            plans = planner.plan(branch=branch, mission_type=mtype, top_n=2)
            print(f"\n{branch.upper()} — {mtype} ({len(plans)} recommendations):")
            for p in plans:
                print(f"  #{p.rank} [{p.confidence}] Asset: {p.asset.asset_id} | "
                      f"Crew: {p.crew.name} | Readiness: {p.asset.readiness:.1f}%")
                for w in p.warnings:
                    print(f"    ⚠️  {w}")
        except Exception as e:
            print(f"  {branch}/{mtype}: {e}")
