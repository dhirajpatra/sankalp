"""
Bandhan (बंधन) – Sankalp Ontology Agent
DRDO requirement: Build a knowledge graph representing asset lineage across
Indian Air Force platforms, crew, and mission operations.
"""

import sqlite3
import logging
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Bandhan] %(message)s")
logger = logging.getLogger("bandhan")

GOLD_DB = "sankalp_gold.db"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "sankalp123"  # set via env in production


def get_driver():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        logger.warning(f"Neo4j not reachable: {e}. Running in offline mode.")
        return None


def build_ontology(gold_db: str = GOLD_DB) -> dict:
    driver = get_driver()
    conn = sqlite3.connect(gold_db)

    import pandas as pd
    aircraft_df = pd.read_sql("SELECT * FROM aircraft_gold", conn)
    crew_df = pd.read_sql("SELECT * FROM crew_gold", conn)
    missions_df = pd.read_sql("SELECT * FROM missions_gold", conn)
    conn.close()

    stats = {"aircraft": 0, "crew": 0, "missions": 0, "relationships": 0}

    if driver is None:
        logger.warning("Neo4j unavailable – ontology not persisted. Returning mock stats.")
        stats = {
            "aircraft": len(aircraft_df),
            "crew": len(crew_df),
            "missions": len(missions_df),
            "relationships": len(missions_df) * 2,
            "mode": "offline",
        }
        return stats

    with driver.session() as session:
        # Clear existing graph
        session.run("MATCH (n) DETACH DELETE n")
        logger.info("Cleared existing ontology graph.")

        # Create :Aircraft nodes
        for _, row in aircraft_df.iterrows():
            session.run(
                """
                MERGE (a:Aircraft {aircraft_id: $aircraft_id})
                SET a.type = $type,
                    a.squadron = $squadron,
                    a.last_maintenance_date = $last_maintenance_date,
                    a.flight_hours = $flight_hours,
                    a.readiness_base_score = $readiness_base_score
                """,
                **row.to_dict(),
            )
        stats["aircraft"] = len(aircraft_df)
        logger.info(f"Created {len(aircraft_df)} :Aircraft nodes.")

        # Create :Crew nodes
        for _, row in crew_df.iterrows():
            session.run(
                """
                MERGE (c:Crew {crew_id: $crew_id})
                SET c.name = $name,
                    c.rank = $rank,
                    c.aircraft_type_qualified = $aircraft_type_qualified
                """,
                **row.to_dict(),
            )
        stats["crew"] = len(crew_df)
        logger.info(f"Created {len(crew_df)} :Crew nodes.")

        # Create :Mission nodes + relationships
        rel_count = 0
        for _, row in missions_df.iterrows():
            session.run(
                """
                MERGE (m:Mission {mission_id: $mission_id})
                SET m.date = $date,
                    m.mission_type = $mission_type,
                    m.fuel_used = $fuel_used
                WITH m
                MATCH (a:Aircraft {aircraft_id: $aircraft_id})
                MERGE (a)-[:EXECUTED]->(m)
                WITH m
                MATCH (c:Crew {crew_id: $crew_id})
                MERGE (c)-[:PARTICIPATED_IN]->(m)
                """,
                **row.to_dict(),
            )
            rel_count += 2
        stats["missions"] = len(missions_df)
        stats["relationships"] = rel_count
        logger.info(f"Created {len(missions_df)} :Mission nodes, {rel_count} relationships.")

    driver.close()
    return stats


if __name__ == "__main__":
    result = build_ontology()
    print(result)
