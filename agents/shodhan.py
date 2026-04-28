"""
Shodhan (शोधन) – Sankalp Transformation Agent
DRDO requirement: Standardise and enrich raw defence data into Gold-quality tables.
"""

import sqlite3
import pandas as pd
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Shodhan] %(message)s")
logger = logging.getLogger("shodhan")

RAW_DB = "data/processed/sankalp_raw.db"
GOLD_DB = "data/processed/sankalp_gold.db"


def _base_readiness(flight_hours: float) -> float:
    """
    Simple heuristic: aircraft with more flight hours are closer to maintenance window.
    Indian Air Force threshold: 1000 hours triggers mandatory depot-level maintenance.
    """
    score = 100 - (flight_hours / 10)
    return max(0.0, min(100.0, round(score, 2)))


def transform(raw_db: str = RAW_DB) -> str:
    raw_conn = sqlite3.connect(raw_db)
    gold_conn = sqlite3.connect(GOLD_DB)
    created_tables = []

    # --- aircraft_gold ---
    aircraft = pd.read_sql("SELECT * FROM aircraft", raw_conn)

    # Normalise column name: CSV uses 'aircraft_type', legacy data may use 'type'
    if "aircraft_type" not in aircraft.columns and "type" in aircraft.columns:
        aircraft = aircraft.rename(columns={"type": "aircraft_type"})
    elif "aircraft_type" not in aircraft.columns:
        aircraft["aircraft_type"] = "Unknown"

    aircraft["last_maintenance_date"] = pd.to_datetime(
        aircraft["last_maintenance_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    aircraft["flight_hours"] = pd.to_numeric(aircraft["flight_hours"], errors="coerce").fillna(0)
    aircraft["readiness_base_score"] = aircraft["flight_hours"].apply(_base_readiness)

    # Keep only the columns we need for the gold table
    gold_cols = ["aircraft_id", "aircraft_type", "squadron",
                 "last_maintenance_date", "flight_hours", "readiness_base_score"]
    # Include any extra columns that exist
    extra = [c for c in aircraft.columns if c not in gold_cols]
    aircraft = aircraft[gold_cols + extra]

    aircraft.to_sql("aircraft_gold", gold_conn, if_exists="replace", index=False)
    created_tables.append("aircraft_gold")
    logger.info(f"aircraft_gold: {len(aircraft)} rows.")

    # --- crew_gold ---
    crew = pd.read_sql("SELECT * FROM crew", raw_conn)
    crew.to_sql("crew_gold", gold_conn, if_exists="replace", index=False)
    created_tables.append("crew_gold")
    logger.info(f"crew_gold: {len(crew)} rows.")

    # --- missions_gold ---
    missions = pd.read_sql("SELECT * FROM missions", raw_conn)
    missions["date"] = pd.to_datetime(missions["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    missions["fuel_used"] = pd.to_numeric(missions["fuel_used"], errors="coerce").fillna(0)
    missions.to_sql("missions_gold", gold_conn, if_exists="replace", index=False)
    created_tables.append("missions_gold")
    logger.info(f"missions_gold: {len(missions)} rows.")

    raw_conn.close()
    gold_conn.close()
    logger.info(f"Gold store ready: {GOLD_DB}")
    return GOLD_DB


if __name__ == "__main__":
    result = transform()
    print(f"Gold DB: {result}")