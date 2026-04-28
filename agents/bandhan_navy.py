"""
Bandhan-Navy (बंधन) – Sankalp Ontology Agent (Indian Navy)
DRDO requirement: Build knowledge graph for Naval vessels, crew, and sorties.
"""

import sqlite3
import logging
import os
import time
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Bandhan-Navy] %(message)s")
logger = logging.getLogger("bandhan_navy")

GOLD_DB    = "data/processed/sankalp_navy_gold.db"
NEO4J_URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sankalp123")


def _get_status(score):
    import json
    threshold = 5
    try:
        with open("data/processed/ontology_rules.json", "r") as f:
            rules = json.load(f)
            threshold = rules.get("__global_settings__", {}).get("operational_threshold", 5)
    except Exception:
        pass
    if score >= threshold: return "Operational"
    if score >= (threshold - 20): return "Watch"
    return "Critical"

def get_driver(retries: int = 5, delay: int = 2):
    from neo4j import GraphDatabase
    for attempt in range(retries):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
            driver.verify_connectivity()
            logger.info("✓ Connected to Neo4j")
            return driver
        except Exception as e:
            if attempt < retries - 1:
                wait_time = delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1}/{retries} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.warning(f"Neo4j not reachable after {retries} attempts. Offline mode.")
                return None
    return None


def build_ontology(gold_db: str = GOLD_DB) -> dict:
    import pandas as pd
    driver = get_driver()
    conn = sqlite3.connect(gold_db)

    vessels_df  = pd.read_sql("SELECT * FROM vessels_gold", conn)
    crew_df     = pd.read_sql("SELECT * FROM navy_crew_gold", conn)
    sorties_df  = pd.read_sql("SELECT * FROM sorties_gold", conn)

    # Merge readiness scores if available
    try:
        readiness_df = pd.read_sql("SELECT vessel_id, final_readiness_score FROM vessel_readiness", conn)
        vessels_df = vessels_df.merge(readiness_df, on="vessel_id", how="left")
    except Exception:
        vessels_df["final_readiness_score"] = vessels_df.get("readiness_base_score", 0)

    conn.close()

    stats = {
        "vessels": len(vessels_df),
        "crew": len(crew_df),
        "sorties": len(sorties_df),
        "relationships": 0,
        "mode": "online",
    }

    if driver is None:
        stats["mode"] = "offline"
        logger.warning("Neo4j unavailable – Navy ontology not persisted.")
        return stats

    with driver.session() as session:
        # :Vessel nodes
        for _, row in vessels_df.iterrows():
            v_type = str(row.get("vessel_type", row.get("type", "Unknown")))
            # sea_hours may be "NA" string in raw data for aircraft assets
            try:
                sea_hours = float(row.get("sea_hours", 0))
            except (ValueError, TypeError):
                sea_hours = 0.0
            session.run(
                """
                MERGE (v:Vessel {vessel_id: $vessel_id})
                SET v.vessel_type          = $vessel_type,
                    v.flotilla             = $flotilla,
                    v.last_refit_date      = $last_refit_date,
                    v.sea_hours            = $sea_hours,
                    v.readiness_base_score = $readiness_base_score,
                    v.final_readiness_score = $final_readiness_score,
                    v.operational_status   = $operational_status
                """,
                vessel_id=str(row["vessel_id"]),
                vessel_type=v_type,
                flotilla=str(row.get("flotilla", "")),
                last_refit_date=str(row.get("last_refit_date", "")),
                sea_hours=sea_hours,
                readiness_base_score=float(row.get("readiness_base_score", 0)),
                final_readiness_score=float(row.get("final_readiness_score", row.get("readiness_base_score", 0))),
                operational_status=_get_status(float(row.get("readiness_base_score", 0))),
            )
        logger.info(f"Upserted {len(vessels_df)} :Vessel nodes.")

        # :NavyCrew nodes
        for _, row in crew_df.iterrows():
            session.run(
                """
                MERGE (c:NavyCrew {crew_id: $crew_id})
                SET c.name              = $name,
                    c.rank              = $rank,
                    c.vessel_qualified  = $vessel_qualified
                """,
                crew_id=str(row["crew_id"]),
                name=str(row.get("name", "")),
                rank=str(row.get("rank", "")),
                vessel_qualified=str(row.get("vessel_qualified", "")),
            )
        logger.info(f"Upserted {len(crew_df)} :NavyCrew nodes.")

        # :Sortie nodes + relationships
        rel_count = 0
        for _, row in sorties_df.iterrows():
            try:
                fuel = float(row.get("fuel_consumed_tons", 0))
            except (ValueError, TypeError):
                fuel = 0.0
            session.run(
                """
                MERGE (s:Sortie {sortie_id: $sortie_id})
                SET s.date                = $date,
                    s.sortie_type         = $sortie_type,
                    s.fuel_consumed_tons  = $fuel_consumed_tons
                WITH s
                MATCH (v:Vessel {vessel_id: $vessel_id})
                MERGE (v)-[:SAILED_FOR]->(s)
                WITH s
                MATCH (c:NavyCrew {crew_id: $crew_id})
                MERGE (c)-[:ASSIGNED_TO]->(s)
                """,
                sortie_id=str(row["sortie_id"]),
                date=str(row.get("date", "")),
                sortie_type=str(row.get("sortie_type", "")),
                fuel_consumed_tons=fuel,
                vessel_id=str(row["vessel_id"]),
                crew_id=str(row["crew_id"]),
            )
            rel_count += 2

        stats["relationships"] = rel_count
        logger.info(f"Upserted {len(sorties_df)} :Sortie nodes, {rel_count} relationships.")

    driver.close()
    return stats


if __name__ == "__main__":
    result = build_ontology()
    print(result)
