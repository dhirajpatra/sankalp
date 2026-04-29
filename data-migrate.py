import sqlite3
import pandas as pd
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def migrate_iaf():
    print("Migrating IAF...")
    if not os.path.exists("data/processed/sankalp_gold.db"):
        print("sankalp_gold.db not found")
        return
    conn = sqlite3.connect("data/processed/sankalp_gold.db")
    df_a = pd.read_sql("SELECT * FROM aircraft_gold", conn)
    df_c = pd.read_sql("SELECT * FROM crew_gold", conn)
    df_m = pd.read_sql("SELECT * FROM missions_gold", conn)
    
    with driver.session() as session:
        for _, row in df_a.iterrows():
            ac_type = row.get("type", row.get("aircraft_type", "Unknown"))
            session.run("""
            MERGE (a:Aircraft {aircraft_id: $id})
            SET a.aircraft_type = $type, a.squadron = $squadron, a.last_maintenance_date = $date, a.flight_hours = $fh, a.readiness_base_score = $score
            """, id=row["aircraft_id"], type=ac_type, squadron=row["squadron"], date=row["last_maintenance_date"], fh=row["flight_hours"], score=row["readiness_base_score"])
            
        for _, row in df_c.iterrows():
            session.run("""
            MERGE (c:Crew {crew_id: $id})
            SET c.name = $name, c.rank = $rank, c.aircraft_type_qualified = $qual
            """, id=row["crew_id"], name=row["name"], rank=row["rank"], qual=row["aircraft_type_qualified"])
            
        for _, row in df_m.iterrows():
            session.run("""
            MERGE (m:Mission {mission_id: $id})
            SET m.date = $date, m.mission_type = $type, m.fuel_used = $fuel
            WITH m
            MATCH (a:Aircraft {aircraft_id: $ac_id})
            MERGE (a)-[:EXECUTED]->(m)
            WITH m
            MATCH (c:Crew {crew_id: $cr_id})
            MERGE (c)-[:PARTICIPATED_IN]->(m)
            """, id=row["mission_id"], date=row["date"], type=row["mission_type"], fuel=row["fuel_used"], ac_id=row["aircraft_id"], cr_id=row["crew_id"])
    print("IAF migrated.")

def migrate_army():
    print("Migrating Army...")
    if not os.path.exists("data/processed/sankalp_army_gold.db"):
        print("sankalp_army_gold.db not found")
        return
    conn = sqlite3.connect("data/processed/sankalp_army_gold.db")
    df_a = pd.read_sql("SELECT * FROM assets_gold", conn)
    df_c = pd.read_sql("SELECT * FROM army_crew_gold", conn)
    df_o = pd.read_sql("SELECT * FROM ops_gold", conn)
    
    with driver.session() as session:
        for _, row in df_a.iterrows():
            a_type = row.get("type", row.get("asset_type", "Unknown"))
            session.run("""
            MERGE (a:ArmyAsset {asset_id: $id})
            SET a.asset_type = $type, a.unit = $unit, a.last_service_date = $date, a.operational_hours = $oh, a.readiness_base_score = $score
            """, id=row["asset_id"], type=a_type, unit=row["unit"], date=row["last_service_date"], oh=row["operational_hours"], score=row["readiness_base_score"])
            
        for _, row in df_c.iterrows():
            session.run("""
            MERGE (c:ArmyPersonnel {crew_id: $id})
            SET c.name = $name, c.rank = $rank, c.vehicle_qualified = $qual
            """, id=row["crew_id"], name=row["name"], rank=row["rank"], qual=row.get("vehicle_qualified", "Unknown"))
            
        for _, row in df_o.iterrows():
            session.run("""
            MERGE (o:ArmyOperation {op_id: $id})
            SET o.date = $date, o.op_type = $type, o.ammo_expended = $ammo
            WITH o
            MATCH (a:ArmyAsset {asset_id: $ac_id})
            MERGE (a)-[:DEPLOYED_FOR]->(o)
            WITH o
            MATCH (c:ArmyPersonnel {crew_id: $cr_id})
            MERGE (c)-[:ENGAGED_IN]->(o)
            """, id=row["op_id"], date=row["date"], type=row["op_type"], ammo=row["ammo_expended"], ac_id=row["asset_id"], cr_id=row["crew_id"])
    print("Army migrated.")

def migrate_navy():
    print("Migrating Navy...")
    if not os.path.exists("data/processed/sankalp_navy_gold.db"):
        print("sankalp_navy_gold.db not found")
        return
    conn = sqlite3.connect("data/processed/sankalp_navy_gold.db")
    df_v = pd.read_sql("SELECT * FROM vessels_gold", conn)
    df_c = pd.read_sql("SELECT * FROM navy_crew_gold", conn)
    df_s = pd.read_sql("SELECT * FROM sorties_gold", conn)
    
    with driver.session() as session:
        for _, row in df_v.iterrows():
            v_type = row.get("type", row.get("vessel_type", "Unknown"))
            session.run("""
            MERGE (v:Vessel {vessel_id: $id})
            SET v.vessel_type = $type, v.flotilla = $flotilla, v.last_refit_date = $date, v.sea_hours = $sh, v.readiness_base_score = $score
            """, id=row["vessel_id"], type=v_type, flotilla=row["flotilla"], date=row["last_refit_date"], sh=row["sea_hours"], score=row["readiness_base_score"])
            
        for _, row in df_c.iterrows():
            session.run("""
            MERGE (c:NavyCrew {crew_id: $id})
            SET c.name = $name, c.rank = $rank, c.vessel_qualified = $qual
            """, id=row["crew_id"], name=row["name"], rank=row["rank"], qual=row.get("vessel_qualified", "Unknown"))
            
        for _, row in df_s.iterrows():
            session.run("""
            MERGE (s:Sortie {sortie_id: $id})
            SET s.date = $date, s.sortie_type = $type, s.fuel_consumed_tons = $fuel
            WITH s
            MATCH (v:Vessel {vessel_id: $v_id})
            MERGE (v)-[:SAILED_FOR]->(s)
            WITH s
            MATCH (c:NavyCrew {crew_id: $cr_id})
            MERGE (c)-[:ASSIGNED_TO]->(s)
            """, id=row["sortie_id"], date=row["date"], type=row["sortie_type"], fuel=row["fuel_consumed_tons"], v_id=row["vessel_id"], cr_id=row["crew_id"])
    print("Navy migrated.")

migrate_iaf()
migrate_army()
migrate_navy()
driver.close()
