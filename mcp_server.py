"""
mcp_server.py – SANKALP MCP Server (fastmcp)
Exposes SANKALP defence data as MCP tools connectable from Claude.

Run (stdio — Claude Desktop):
    python mcp_server.py

Run (HTTP — URL-based connector):
    python mcp_server.py --http --port 8080

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "sankalp": {
          "command": "python",
          "args": ["/absolute/path/to/sankalp/mcp_server.py"]
        }
      }
    }
"""

import json
import os
import sqlite3
import sys
from typing import Literal

from fastmcp import FastMCP

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
IAF_GOLD  = os.path.join(BASE, "data/processed/sankalp_gold.db")
ARMY_GOLD = os.path.join(BASE, "data/processed/sankalp_army_gold.db")
NAVY_GOLD = os.path.join(BASE, "data/processed/sankalp_navy_gold.db")
RULES     = os.path.join(BASE, "data/processed/ontology_rules.json")

# ── FastMCP app ───────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="sankalp-defence",
    instructions=(
        "SANKALP Defence Ontology Platform — query live readiness data for "
        "Indian Air Force, Army, and Navy assets. Evaluate doctrine rules and "
        "get mission history across all three branches."
    ),
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sql(db: str, query: str) -> list[dict]:
    if not os.path.exists(db):
        return []
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _rules() -> dict:
    if not os.path.exists(RULES):
        return {}
    with open(RULES) as f:
        return json.load(f)


def _threshold() -> int:
    return _rules().get("__global_settings__", {}).get("operational_threshold", 5)


def _branch_op_count(db: str, table: str) -> int:
    t = _threshold()
    rows = _sql(db, f"SELECT final_readiness_score AS s FROM {table}")
    return sum(1 for r in rows if (r["s"] or 0) >= t)


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool
def get_fleet_readiness() -> str:
    """
    Returns readiness summary for IAF, Army, and Navy:
    total assets, operational, watch, critical counts, and average readiness %.
    """
    threshold = _threshold()

    def _summary(db, r_table, g_table, g_score):
        rows = _sql(db, f"SELECT final_readiness_score AS s FROM {r_table}")
        if not rows:
            rows = _sql(db, f"SELECT {g_score} AS s FROM {g_table}")
        scores = [float(r["s"] or 0) for r in rows]
        if not scores:
            return {"total": 0, "operational": 0, "watch": 0, "critical": 0, "avg_readiness": 0}
        return {
            "total":        len(scores),
            "operational":  sum(1 for s in scores if s >= threshold),
            "watch":        sum(1 for s in scores if threshold - 20 <= s < threshold),
            "critical":     sum(1 for s in scores if s < threshold - 20),
            "avg_readiness": round(sum(scores) / len(scores), 1),
        }

    return json.dumps({
        "operational_threshold": threshold,
        "iaf":  _summary(IAF_GOLD,  "aircraft_readiness", "aircraft_gold",  "readiness_base_score"),
        "army": _summary(ARMY_GOLD, "asset_readiness",    "assets_gold",    "readiness_base_score"),
        "navy": _summary(NAVY_GOLD, "vessel_readiness",   "vessels_gold",   "readiness_base_score"),
    }, indent=2)


@mcp.tool
def get_critical_assets(
    branch: Literal["iaf", "army", "navy", "all"] = "all",
    threshold: float = 40,
) -> str:
    """
    Returns assets with readiness score below threshold (default 40%).
    Filter by branch: iaf | army | navy | all.
    """
    results = []

    if branch in ("iaf", "all"):
        results.extend(_sql(IAF_GOLD, f"""
            SELECT aircraft_id AS id, 'IAF' AS branch,
                   aircraft_type AS type, squadron AS unit,
                   final_readiness_score AS score
            FROM aircraft_readiness WHERE final_readiness_score < {threshold}
            ORDER BY final_readiness_score LIMIT 20
        """))

    if branch in ("army", "all"):
        results.extend(_sql(ARMY_GOLD, f"""
            SELECT asset_id AS id, 'Army' AS branch,
                   asset_type AS type, unit,
                   final_readiness_score AS score
            FROM asset_readiness WHERE final_readiness_score < {threshold}
            ORDER BY final_readiness_score LIMIT 20
        """))

    if branch in ("navy", "all"):
        results.extend(_sql(NAVY_GOLD, f"""
            SELECT vessel_id AS id, 'Navy' AS branch,
                   vessel_type AS type, flotilla AS unit,
                   final_readiness_score AS score
            FROM vessel_readiness WHERE final_readiness_score < {threshold}
            ORDER BY final_readiness_score LIMIT 20
        """))

    results.sort(key=lambda x: x.get("score", 0))
    return json.dumps(results, indent=2) if results else "No critical assets found."


@mcp.tool
def evaluate_doctrine(action_name: str) -> str:
    """
    Evaluates if the current fleet can execute a named doctrine action.
    Partial name matching supported.
    Returns: SUPERIOR / ADEQUATE / INSUFFICIENT verdict with reasons.
    """
    rules = _rules()
    matched = next(
        (k for k in rules if action_name.lower() in k.lower() and k != "__global_settings__"),
        None,
    )
    if not matched:
        available = [k for k in rules if k != "__global_settings__"]
        return json.dumps({"error": f"No match for '{action_name}'", "available": available})

    rule = rules[matched]
    caps = {
        "iaf":  _branch_op_count(IAF_GOLD,  "aircraft_readiness"),
        "army": _branch_op_count(ARMY_GOLD, "asset_readiness"),
        "navy": _branch_op_count(NAVY_GOLD, "vessel_readiness"),
    }

    mode  = rule.get("logic_mode", "standard")
    tier  = "INSUFFICIENT"

    if mode == "iaf_primary_army_superior":
        iaf_ok  = caps["iaf"]  >= rule["iaf_min_operational"]
        army_ok = caps["army"] >= rule.get("army_enhancement_threshold", 0)
        tier    = "SUPERIOR" if (iaf_ok and army_ok) else "ADEQUATE" if iaf_ok else "INSUFFICIENT"
        reasons = [
            f"IAF:  {caps['iaf']}  op (min {rule['iaf_min_operational']})  {'OK' if iaf_ok else 'FAIL'}",
            f"Army: {caps['army']} op (threshold {rule.get('army_enhancement_threshold',0)}) {'OK' if army_ok else 'FAIL'}",
            "Navy: not required",
        ]
    else:
        iaf_ok  = caps["iaf"]  >= rule["iaf_min_operational"]
        army_ok = caps["army"] >= rule["army_min_operational"]
        navy_ok = caps["navy"] >= rule["navy_min_operational"]
        tier    = "ADEQUATE" if (iaf_ok and army_ok and navy_ok) else "INSUFFICIENT"
        reasons = [
            f"IAF:  {caps['iaf']}  op (need {rule['iaf_min_operational']})  {'OK' if iaf_ok else 'FAIL'}",
            f"Army: {caps['army']} op (need {rule['army_min_operational']}) {'OK' if army_ok else 'FAIL'}",
            f"Navy: {caps['navy']} op (need {rule['navy_min_operational']}) {'OK' if navy_ok else 'FAIL'}",
        ]

    return json.dumps({
        "action": matched, "verdict": tier,
        "description": rule.get("description", ""),
        "reasons": reasons, "live_caps": caps,
    }, indent=2)


@mcp.tool
def list_doctrine_rules() -> str:
    """Lists all defined doctrine rules with minimum asset requirements."""
    rules = _rules()
    return json.dumps([
        {
            "action":      k,
            "description": v.get("description", ""),
            "iaf_min":     v.get("iaf_min_operational", 0),
            "army_min":    v.get("army_min_operational", 0),
            "navy_min":    v.get("navy_min_operational", 0),
            "logic_mode":  v.get("logic_mode", "standard"),
        }
        for k, v in rules.items() if k != "__global_settings__"
    ], indent=2)


@mcp.tool
def get_mission_history(
    branch: Literal["iaf", "army", "navy", "all"] = "all",
    limit: int = 10,
) -> str:
    """Returns recent missions / operations / sorties, sorted by date descending."""
    results = []

    if branch in ("iaf", "all"):
        results.extend(_sql(IAF_GOLD, f"""
            SELECT mission_id AS id, 'IAF' AS branch, date,
                   mission_type AS type, fuel_used AS resource, aircraft_id AS asset_id
            FROM missions_gold ORDER BY date DESC LIMIT {limit}
        """))

    if branch in ("army", "all"):
        results.extend(_sql(ARMY_GOLD, f"""
            SELECT op_id AS id, 'Army' AS branch, date,
                   op_type AS type, ammo_expended AS resource, asset_id
            FROM ops_gold ORDER BY date DESC LIMIT {limit}
        """))

    if branch in ("navy", "all"):
        results.extend(_sql(NAVY_GOLD, f"""
            SELECT sortie_id AS id, 'Navy' AS branch, date,
                   sortie_type AS type, fuel_consumed_tons AS resource, vessel_id AS asset_id
            FROM sorties_gold ORDER BY date DESC LIMIT {limit}
        """))

    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return json.dumps(results[:limit], indent=2)


@mcp.tool
def get_top_ready_assets(
    branch: Literal["iaf", "army", "navy"] = "iaf",
    top_n: int = 5,
) -> str:
    """Returns the top N assets by readiness score for a given branch."""
    cfg = {
        "iaf":  (IAF_GOLD,  "aircraft_readiness", "aircraft_id", "aircraft_type", "squadron"),
        "army": (ARMY_GOLD, "asset_readiness",    "asset_id",    "asset_type",    "unit"),
        "navy": (NAVY_GOLD, "vessel_readiness",   "vessel_id",   "vessel_type",   "flotilla"),
    }
    db, table, id_col, type_col, unit_col = cfg[branch]
    rows = _sql(db, f"""
        SELECT {id_col} AS id, {type_col} AS type, {unit_col} AS unit,
               final_readiness_score AS score
        FROM {table} ORDER BY final_readiness_score DESC LIMIT {top_n}
    """)
    return json.dumps(rows, indent=2) if rows else f"No data for branch '{branch}'."


@mcp.tool
def assess_threat_scenario(
    scenario: Literal[
        "northern_infiltration", "western_border_strike", "two_front_war",
        "southern_sea_threat", "cyber_plus_border", "island_territory_dispute",
    ] = "two_front_war",
) -> str:
    """
    Assesses current fleet capability against a named threat scenario.
    Returns: CAPABLE / MARGINAL / INSUFFICIENT with coverage % and branch gaps.
    """
    try:
        sys.path.insert(0, BASE)
        from agents.threat_engine import ThreatEngine
        a = ThreatEngine().assess(scenario)
        return json.dumps(a.to_dict(), indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool
def plan_mission(
    branch: Literal["iaf", "army", "navy"] = "iaf",
    mission_type: str = "Strike",
    top_n: int = 3,
) -> str:
    """
    Recommends optimal asset-crew pairings for an upcoming mission.
    Uses live readiness scores, crew qualifications, and seniority.
    Common mission_type values: Strike, Patrol, Anti-Submarine Warfare, Border Vigil, CAS.
    """
    try:
        sys.path.insert(0, BASE)
        from agents.yojana import MissionPlanner
        plans = MissionPlanner().plan(branch=branch, mission_type=mission_type, top_n=top_n)
        return json.dumps([p.to_dict() for p in plans], indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SANKALP MCP Server (fastmcp)")
    parser.add_argument("--http",  action="store_true", help="Run as HTTP/SSE server")
    parser.add_argument("--port",  type=int, default=8080)
    parser.add_argument("--host",  default="0.0.0.0")
    args = parser.parse_args()

    if args.http:
        print(f"\n🛡️  SANKALP MCP Server  (HTTP/SSE mode)")
        print(f"   Endpoint : http://{args.host}:{args.port}/sse")
        print(f"   Connect Claude connector to this URL\n")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
