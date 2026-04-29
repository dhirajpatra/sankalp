import sqlite3
import pandas as pd
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

try:
    conn_a = sqlite3.connect('data/processed/sankalp_army_gold.db')
    df_a = pd.read_sql('SELECT * FROM assets_gold', conn_a)

    with driver.session() as session:
        for _, row in df_a.iterrows():
            session.run('''
            MATCH (a:ArmyAsset {asset_id: $id})
            SET a.readiness_base_score = $score, a.operational_hours = $oh
            ''', id=str(row['asset_id']), score=float(row['readiness_base_score']), oh=int(row['operational_hours']))

    conn_n = sqlite3.connect('data/processed/sankalp_navy_gold.db')
    df_n = pd.read_sql('SELECT * FROM vessels_gold', conn_n)

    with driver.session() as session:
        for _, row in df_n.iterrows():
            session.run('''
            MATCH (v:Vessel {vessel_id: $id})
            SET v.readiness_base_score = $score, v.sea_hours = $sh
            ''', id=str(row['vessel_id']), score=float(row['readiness_base_score']), sh=int(row['sea_hours']))

    print('Updated scores in Neo4j!')
except Exception as e:
    print(f"Error: {e}")
finally:
    driver.close()
