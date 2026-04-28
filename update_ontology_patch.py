import json
import os
from neo4j import GraphDatabase

RULES_FILE = "data/processed/ontology_rules.json"

def get_operational_threshold():
    if not os.path.exists(RULES_FILE):
        return 60
    with open(RULES_FILE, "r") as f:
        rules = json.load(f)
        return rules.get("__global_settings__", {}).get("operational_threshold", 60)

def set_operational_threshold(threshold):
    rules = {}
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r") as f:
            rules = json.load(f)
    if "__global_settings__" not in rules:
        rules["__global_settings__"] = {}
    rules["__global_settings__"]["operational_threshold"] = threshold
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=4)
        
def update_neo4j_operational_status(uri, user, pwd, threshold):
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as session:
        # Aircraft
        session.run("""
            MATCH (a:Aircraft)
            SET a.operational_status = CASE 
                WHEN a.readiness_base_score >= $threshold THEN 'Operational'
                WHEN a.readiness_base_score >= ($threshold - 20) THEN 'Watch'
                ELSE 'Critical' END
        """, threshold=threshold)
        
        # ArmyAsset
        session.run("""
            MATCH (aa:ArmyAsset)
            SET aa.operational_status = CASE 
                WHEN aa.readiness_base_score >= $threshold THEN 'Operational'
                WHEN aa.readiness_base_score >= ($threshold - 20) THEN 'Watch'
                ELSE 'Critical' END
        """, threshold=threshold)
        
        # Vessel
        session.run("""
            MATCH (v:Vessel)
            SET v.operational_status = CASE 
                WHEN v.readiness_base_score >= $threshold THEN 'Operational'
                WHEN v.readiness_base_score >= ($threshold - 20) THEN 'Watch'
                ELSE 'Critical' END
        """, threshold=threshold)
    driver.close()
