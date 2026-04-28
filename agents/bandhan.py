"""
Bandhan (बंधन) – Sankalp Ontology Agent (IAF)
DRDO requirement: Build a knowledge graph representing asset lineage across
Indian Air Force platforms, crew, and mission operations.

NOTE: Uses MERGE (upsert) instead of DETACH DELETE ALL so that Army and Navy
nodes written by bandhan_army.py / bandhan_navy.py are never wiped.
"""

import sqlite3
import logging
import os
import time
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pathlib import Path

# Walk up from agents/ to find .env in project root (local dev).
# In Docker, env vars are injected directly — no .env file needed.
def _load_env():
    candidate = Path(__file__).resolve().parent
    for _ in range(4):
        env_file = candidate / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=True)
            return
        candidate = candidate.parent

_load_env()

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Bandhan] %(message)s")
logger = logging.getLogger("bandhan")

GOLD_DB    = "data/processed/sankalp_gold.db"
NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sankalp123")


def get_driver(retries: int = 5, delay: int = 2):
    for attempt in range(retries):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            driver.verify_connectivity()
            logger.info("✓ Connected to Neo4j")
            return driver
        except Exception as e:
            if attempt < retries - 1:
                wait_time = delay * (2 ** attempt)
                logger.warning(f"Connection attempt {attempt + 1}/{retries} failed: {e}")
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.warning(f"Neo4j not reachable after {retries} attempts. Running in offline mode.")
                return None
    return None


def build_ontology(gold_db: str = GOLD_DB) -> dict:
    driver = get_driver()
    conn = sqlite3.connect(gold_db)

    import pandas as pd
    aircraft_df = pd.read_sql("SELECT * FROM aircraft_gold", conn)
    crew_df     = pd.read_sql("SELECT * FROM crew_gold", conn)
    missions_df = pd.read_sql("SELECT * FROM missions_gold", conn)
    conn.close()

    stats = {"aircraft": 0, "crew": 0, "missions": 0, "relationships": 0}

    if driver is None:
        logger.warning("Neo4j unavailable – ontology not persisted. Returning mock stats.")
        stats = {
            "aircraft":      len(aircraft_df),
            "crew":          len(crew_df),
            "missions":      len(missions_df),
            "relationships": len(missions_df) * 2,
            "mode":          "offline",
        }
        return stats

    with driver.session() as session:
        # ── Delete only IAF nodes so Army/Navy data is preserved ──────────────
        session.run("MATCH (n:Aircraft)  DETACH DELETE n")
        session.run("MATCH (n:Crew)      DETACH DELETE n")
        session.run("MATCH (n:Mission)   DETACH DELETE n")
        logger.info("Cleared existing IAF ontology nodes (Aircraft, Crew, Mission).")

        # ── :Aircraft nodes ───────────────────────────────────────────────────
        for _, row in aircraft_df.iterrows():
            session.run(
                """
                MERGE (a:Aircraft {aircraft_id: $aircraft_id})
                SET a.aircraft_type         = $aircraft_type,
                    a.squadron              = $squadron,
                    a.last_maintenance_date = $last_maintenance_date,
                    a.flight_hours          = $flight_hours,
                    a.readiness_base_score  = $readiness_base_score
                """,
                aircraft_id=str(row["aircraft_id"]),
                aircraft_type=str(row.get("aircraft_type", row.get("type", "Unknown"))),
                squadron=str(row.get("squadron", "")),
                last_maintenance_date=str(row.get("last_maintenance_date", "")),
                flight_hours=float(row.get("flight_hours", 0)),
                readiness_base_score=float(row.get("readiness_base_score", 0)),
            )
        stats["aircraft"] = len(aircraft_df)
        logger.info(f"Upserted {len(aircraft_df)} :Aircraft nodes.")

        # ── :Crew nodes ───────────────────────────────────────────────────────
        for _, row in crew_df.iterrows():
            session.run(
                """
                MERGE (c:Crew {crew_id: $crew_id})
                SET c.name                    = $name,
                    c.rank                    = $rank,
                    c.aircraft_type_qualified = $aircraft_type_qualified
                """,
                crew_id=str(row["crew_id"]),
                name=str(row.get("name", "")),
                rank=str(row.get("rank", "")),
                aircraft_type_qualified=str(row.get("aircraft_type_qualified", "")),
            )
        stats["crew"] = len(crew_df)
        logger.info(f"Upserted {len(crew_df)} :Crew nodes.")

        # ── :Mission nodes + relationships ────────────────────────────────────
        rel_count = 0
        for _, row in missions_df.iterrows():
            session.run(
                """
                MERGE (m:Mission {mission_id: $mission_id})
                SET m.date         = $date,
                    m.mission_type = $mission_type,
                    m.fuel_used    = $fuel_used
                WITH m
                MATCH (a:Aircraft {aircraft_id: $aircraft_id})
                MERGE (a)-[:EXECUTED]->(m)
                WITH m
                MATCH (c:Crew {crew_id: $crew_id})
                MERGE (c)-[:PARTICIPATED_IN]->(m)
                """,
                mission_id=str(row["mission_id"]),
                date=str(row.get("date", "")),
                mission_type=str(row.get("mission_type", "")),
                fuel_used=float(row.get("fuel_used", 0)),
                aircraft_id=str(row["aircraft_id"]),
                crew_id=str(row["crew_id"]),
            )
            rel_count += 2

        stats["missions"]      = len(missions_df)
        stats["relationships"] = rel_count
        logger.info(f"Upserted {len(missions_df)} :Mission nodes, {rel_count} relationships.")

    driver.close()
    return stats


if __name__ == "__main__":
    result = build_ontology()
    print(result)
