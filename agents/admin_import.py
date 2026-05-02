import streamlit as st
import os
from neo4j import GraphDatabase

IMPORT_TEMPLATES = {
    "Airforce - Aircraft": {
        "clear": "MATCH (n:Aircraft) DETACH DELETE n",
        "example": "aircraft_id,aircraft_type,squadron,last_maintenance_date,flight_hours,readiness_base_score\nIAF-101,Su-30MKI,No. 20 Squadron,2025-01-15,1200,90.5",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (a:Aircraft {aircraft_id: row.aircraft_id})
SET a.aircraft_type = coalesce(row.aircraft_type, row.type, "Unknown"),
    a.squadron = row.squadron,
    a.last_maintenance_date = row.last_maintenance_date,
    a.flight_hours = toFloat(row.flight_hours),
    a.readiness_base_score = toFloat(row.readiness_base_score)"""
    },
    "Airforce - Crew": {
        "clear": "MATCH (n:Crew) DETACH DELETE n",
        "example": "crew_id,name,rank,aircraft_type_qualified\nCRW-001,Rakesh Sharma,Wing Commander,Su-30MKI",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (c:Crew {crew_id: row.crew_id})
SET c.name = row.name,
    c.rank = row.rank,
    c.aircraft_type_qualified = row.aircraft_type_qualified"""
    },
    "Airforce - Mission": {
        "clear": "MATCH (n:Mission) DETACH DELETE n",
        "example": "mission_id,date,mission_type,fuel_used,aircraft_id,crew_id\nMSN-4421,2025-02-12,Combat Air Patrol,4500,IAF-101,CRW-001",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (m:Mission {mission_id: row.mission_id})
SET m.date = row.date,
    m.mission_type = row.mission_type,
    m.fuel_used = toFloat(row.fuel_used)
WITH m, row
MATCH (a:Aircraft {aircraft_id: row.aircraft_id})
MERGE (a)-[:EXECUTED]->(m)
WITH m, row
MATCH (c:Crew {crew_id: row.crew_id})
MERGE (c)-[:PARTICIPATED_IN]->(m)"""
    },
    "Army - Asset": {
        "clear": "MATCH (n:ArmyAsset) DETACH DELETE n",
        "example": "asset_id,asset_type,unit,last_service_date,operational_hours\nARM-T90,T-90 Bhishma,43 Armoured Regiment,2024-11-05,450",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (a:ArmyAsset {asset_id: row.asset_id})
SET a.asset_type = row.asset_type,
    a.unit = row.unit,
    a.last_service_date = row.last_service_date,
    a.operational_hours = toFloat(row.operational_hours)"""
    },
    "Army - Personnel": {
        "clear": "MATCH (n:ArmyPersonnel) DETACH DELETE n",
        "example": "crew_id,name,rank,vehicle_qualified\nAP-101,Vikram Singh,Subedar,T-90 Bhishma",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (p:ArmyPersonnel {crew_id: row.crew_id})
SET p.name = row.name,
    p.rank = row.rank,
    p.vehicle_qualified = row.vehicle_qualified"""
    },
    "Army - Operation": {
        "clear": "MATCH (n:ArmyOperation) DETACH DELETE n",
        "example": "op_id,date,op_type,ammo_expended,asset_id,crew_id\nOP-998,2025-01-20,Live Fire Exercise,35,ARM-T90,AP-101",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (o:ArmyOperation {op_id: row.op_id})
SET o.date = row.date,
    o.op_type = row.op_type,
    o.ammo_expended = toFloat(row.ammo_expended)
WITH o, row
MATCH (a:ArmyAsset {asset_id: row.asset_id})
MERGE (a)-[:DEPLOYED_FOR]->(o)
WITH o, row
MATCH (p:ArmyPersonnel {crew_id: row.crew_id})
MERGE (p)-[:ENGAGED_IN]->(o)"""
    },
    "Navy - Vessel": {
        "clear": "MATCH (n:Vessel) DETACH DELETE n",
        "example": "vessel_id,vessel_type,flotilla,last_refit_date,sea_hours\nINS-VIK,Aircraft Carrier,Western Fleet,2024-05-10,3200",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (v:Vessel {vessel_id: row.vessel_id})
SET v.vessel_type = row.vessel_type,
    v.flotilla = row.flotilla,
    v.last_refit_date = row.last_refit_date,
    v.sea_hours = toFloat(row.sea_hours)"""
    },
    "Navy - Crew": {
        "clear": "MATCH (n:NavyCrew) DETACH DELETE n",
        "example": "crew_id,name,rank,vessel_qualified\nNC-505,Arjun Nair,Captain,Aircraft Carrier",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (c:NavyCrew {crew_id: row.crew_id})
SET c.name = row.name,
    c.rank = row.rank,
    c.vessel_qualified = row.vessel_qualified"""
    },
    "Navy - Sortie": {
        "clear": "MATCH (n:Sortie) DETACH DELETE n",
        "example": "sortie_id,date,sortie_type,fuel_consumed_tons,vessel_id,crew_id\nSRT-702,2025-02-01,Fleet Exercise,150,INS-VIK,NC-505",
        "query": """LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row
MERGE (s:Sortie {sortie_id: row.sortie_id})
SET s.date = row.date,
    s.sortie_type = row.sortie_type,
    s.fuel_consumed_tons = toFloat(row.fuel_consumed_tons)
WITH s, row
MATCH (v:Vessel {vessel_id: row.vessel_id})
MERGE (v)-[:SAILED_FOR]->(s)
WITH s, row
MATCH (c:NavyCrew {crew_id: row.crew_id})
MERGE (c)-[:ASSIGNED_TO]->(s)"""
    }
}

def render_admin_dashboard(neo4j_uri, neo4j_user, neo4j_password):
    st.markdown("## ⚙️ Admin / Data Import")
    st.caption("Upload CSV files and process directly into Neo4j")
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("### 1. Upload CSV")
        uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
        
        if uploaded_file is not None:
            docker_import_dir = "/var/lib/neo4j/import"
            local_import_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "neo4j_import")
            
            import_dir = docker_import_dir if os.path.exists("/app") else local_import_dir
            os.makedirs(import_dir, exist_ok=True)
            
            file_path = os.path.join(import_dir, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            st.success(f"✅ File saved to Neo4j import directory (`{uploaded_file.name}`).")

    with c2:
        st.markdown("### 2. Configure Import")
        data_type = st.selectbox("Select Data Type", list(IMPORT_TEMPLATES.keys()))
        st.markdown(
            "**Import Mode**<br>"
            "<span style='font-size:13px;'>🟢 Insert / Update (MERGE) &nbsp;|&nbsp; "
            "<span class='import-mode-danger'>🔴 Overwrite (DELETE ALL existing first)</span></span>",
            unsafe_allow_html=True,
        )
        import_mode = st.radio(
            "Import Mode",
            ["Insert / Update (MERGE)", "Overwrite (DELETE ALL existing first)"],
            horizontal=True,
            label_visibility="collapsed",
        )
        
        st.caption("Expected CSV Format (Headers & Example Data):")
        st.code(IMPORT_TEMPLATES[data_type]["example"], language="csv")
        
        if st.button("🚀 Execute Import", type="primary"):
            if not uploaded_file:
                st.warning("Please upload a CSV file first.")
            else:
                template = IMPORT_TEMPLATES[data_type]
                main_query = template["query"].replace("{filename}", uploaded_file.name)
                
                try:
                    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
                    
                    with driver.session() as session:
                        if import_mode.startswith("Overwrite"):
                            st.info("Clearing existing nodes...")
                            session.run(template["clear"])
                            
                        st.info("Running LOAD CSV...")
                        result = session.run(main_query)
                        summary = result.consume()
                        
                        st.success(f"✅ Import complete in {summary.result_available_after} ms.")
                        st.write(f"**Nodes Created:** {summary.counters.nodes_created}")
                        st.write(f"**Properties Set:** {summary.counters.properties_set}")
                        st.write(f"**Relationships Created:** {summary.counters.relationships_created}")
                            
                    driver.close()
                except Exception as e:
                    st.error(f"Error executing Cypher: {e}")
