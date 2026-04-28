"""
Bandhan-Army (बंधन) – Sankalp Ontology Agent (Indian Army)
DRDO requirement: Build knowledge graph for Army assets, personnel, and operations.
"""

import sqlite3
import logging
import os
import time
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Bandhan-Army] %(message)s")
logger = logging.getLogger("bandhan_army")

GOLD_DB   = "data/processed/sankalp_army_gold.db"
NEO4J_URI  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sankalp123")


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

    assets_df  = pd.read_sql("SELECT * FROM assets_gold", conn)
    crew_df    = pd.read_sql("SELECT * FROM army_crew_gold", conn)
    ops_df     = pd.read_sql("SELECT * FROM ops_gold", conn)

    # Also read readiness scores if available
    try:
        readiness_df = pd.read_sql("SELECT asset_id, final_readiness_score FROM asset_readiness", conn)
        assets_df = assets_df.merge(readiness_df, on="asset_id", how="left")
    except Exception:
        assets_df["final_readiness_score"] = assets_df.get("readiness_base_score", 0)

    conn.close()

    stats = {
        "assets": len(assets_df),
        "crew": len(crew_df),
        "ops": len(ops_df),
        "relationships": 0,
        "mode": "online",
    }

    if driver is None:
        stats["mode"] = "offline"
        logger.warning("Neo4j unavailable – Army ontology not persisted.")
        return stats

    with driver.session() as session:
        # :ArmyAsset nodes
        for _, row in assets_df.iterrows():
            a_type = str(row.get("asset_type", row.get("type", "Unknown")))
            session.run(
                """
                MERGE (a:ArmyAsset {asset_id: $asset_id})
                SET a.asset_type           = $asset_type,
                    a.unit                 = $unit,
                    a.last_service_date    = $last_service_date,
                    a.operational_hours    = $operational_hours,
                    a.readiness_base_score = $readiness_base_score,
                    a.final_readiness_score = $final_readiness_score
                """,
                asset_id=str(row["asset_id"]),
                asset_type=a_type,
                unit=str(row.get("unit", "")),
                last_service_date=str(row.get("last_service_date", "")),
                operational_hours=float(row.get("operational_hours", 0)),
                readiness_base_score=float(row.get("readiness_base_score", 0)),
                final_readiness_score=float(row.get("final_readiness_score", row.get("readiness_base_score", 0))),
            )
        logger.info(f"Upserted {len(assets_df)} :ArmyAsset nodes.")

        # :ArmyPersonnel nodes
        for _, row in crew_df.iterrows():
            session.run(
                """
                MERGE (p:ArmyPersonnel {crew_id: $crew_id})
                SET p.name              = $name,
                    p.rank              = $rank,
                    p.vehicle_qualified = $vehicle_qualified
                """,
                crew_id=str(row["crew_id"]),
                name=str(row.get("name", "")),
                rank=str(row.get("rank", "")),
                vehicle_qualified=str(row.get("vehicle_qualified", "")),
            )
        logger.info(f"Upserted {len(crew_df)} :ArmyPersonnel nodes.")

        # :ArmyOperation nodes + relationships
        rel_count = 0
        for _, row in ops_df.iterrows():
            session.run(
                """
                MERGE (o:ArmyOperation {op_id: $op_id})
                SET o.date          = $date,
                    o.op_type       = $op_type,
                    o.ammo_expended = $ammo_expended
                WITH o
                MATCH (a:ArmyAsset {asset_id: $asset_id})
                MERGE (a)-[:DEPLOYED_FOR]->(o)
                WITH o
                MATCH (p:ArmyPersonnel {crew_id: $crew_id})
                MERGE (p)-[:ENGAGED_IN]->(o)
                """,
                op_id=str(row["op_id"]),
                date=str(row.get("date", "")),
                op_type=str(row.get("op_type", "")),
                ammo_expended=float(row.get("ammo_expended", 0)),
                asset_id=str(row["asset_id"]),
                crew_id=str(row["crew_id"]),
            )
            rel_count += 2

        stats["relationships"] = rel_count
        logger.info(f"Upserted {len(ops_df)} :ArmyOperation nodes, {rel_count} relationships.")

    driver.close()
    return stats


if __name__ == "__main__":
    result = build_ontology()
    print(result)
