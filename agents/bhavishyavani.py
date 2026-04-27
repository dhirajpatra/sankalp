"""
Bhavishyavani (भविष्यवाणी) – Sankalp ML Readiness Agent
DRDO requirement: Predict aircraft readiness scores to pre-empt maintenance
failures in Indian Air Force operational planning.
"""

import sqlite3
import logging
from datetime import date, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Bhavishyavani] %(message)s")
logger = logging.getLogger("bhavishyavani")

GOLD_DB = "sankalp_gold.db"


def _days_since(date_str: str) -> int:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return 365  # assume worst case if date missing


def compute_readiness(gold_db: str = GOLD_DB) -> list:
    """
    Compute final_readiness_score for each aircraft using:
    - base_readiness_score (from Shodhan)
    - days_since_last_mission (staleness penalty)
    - mission_count (operational currency bonus)

    Returns top-3 aircraft requiring attention (lowest scores).
    """
    conn = sqlite3.connect(gold_db)

    import pandas as pd
    aircraft_df = pd.read_sql("SELECT * FROM aircraft_gold", conn)
    missions_df = pd.read_sql("SELECT * FROM missions_gold", conn)
    conn.close()

    mission_counts = missions_df.groupby("aircraft_id").size().reset_index(name="mission_count")
    last_mission = missions_df.groupby("aircraft_id")["date"].max().reset_index(name="last_mission_date")

    merged = aircraft_df.merge(mission_counts, on="aircraft_id", how="left")
    merged = merged.merge(last_mission, on="aircraft_id", how="left")
    merged["mission_count"] = merged["mission_count"].fillna(0)
    merged["last_mission_date"] = merged["last_mission_date"].fillna(merged["last_maintenance_date"])

    merged["days_since_last_mission"] = merged["last_mission_date"].apply(_days_since)

    # Readiness formula (IAF-inspired heuristic)
    merged["final_readiness_score"] = (
        merged["readiness_base_score"] * 0.6
        - merged["days_since_last_mission"] * 0.05
        + merged["mission_count"] * 0.2
    ).clip(0, 100).round(2)

    # Persist back to gold DB
    conn2 = sqlite3.connect(gold_db)
    merged.to_sql("aircraft_readiness", conn2, if_exists="replace", index=False)
    conn2.close()

    # Try to update Neo4j if available
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "sankalp123"))
        with driver.session() as session:
            for _, row in merged.iterrows():
                session.run(
                    "MATCH (a:Aircraft {aircraft_id: $aid}) SET a.final_readiness_score = $score",
                    aid=row["aircraft_id"],
                    score=float(row["final_readiness_score"]),
                )
        driver.close()
        logger.info("Readiness scores written to Neo4j.")
    except Exception as e:
        logger.warning(f"Neo4j update skipped (offline mode): {e}")

    at_risk = (
        merged[["aircraft_id", "type", "squadron", "final_readiness_score"]]
        .sort_values("final_readiness_score")
        .head(3)
        .to_dict(orient="records")
    )

    logger.info(f"Top-3 at-risk aircraft: {[r['aircraft_id'] for r in at_risk]}")
    return at_risk


if __name__ == "__main__":
    result = compute_readiness()
    for r in result:
        print(r)
