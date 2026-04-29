# ── DB helpers ────────────────────────────────────────────────────────────────
import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(override=True)
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

def _get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def _parse_status(df, score_col="final_readiness_score"):
    if not df.empty and "operational_status" in df.columns:
        df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
        status_upper = df["operational_status"].str.upper()
        df.loc[status_upper == "OPERATIONAL", score_col] = 100
        df.loc[status_upper.isin(["WATCH", "NEEDS_ATTENTION", "NEEDS ATTENTION"]), score_col] = 50
        df.loc[status_upper.isin(["MAINTENANCE_REQUIRED", "MAINTENANCE REQUIRED", "CRITICAL"]), score_col] = 20
    return df

@st.cache_data(ttl=10)
def load_iaf():
    driver = _get_neo4j_driver()
    with driver.session() as session:
        df_a = pd.DataFrame([r.data() for r in session.run("MATCH (a:Aircraft) RETURN a.aircraft_id AS aircraft_id, coalesce(a.aircraft_type, a.type, 'Unknown') AS aircraft_type, a.squadron AS squadron, a.last_maintenance_date AS last_maintenance_date, coalesce(a.flight_hours, 0) AS flight_hours, coalesce(a.readiness_base_score, 100 - (toFloat(coalesce(a.flight_hours, 0)) * 0.8)) AS final_readiness_score, coalesce(a.operational_status, '') AS operational_status")])
        if df_a.empty: df_a = pd.DataFrame(columns=["aircraft_id", "aircraft_type", "squadron", "last_maintenance_date", "flight_hours", "final_readiness_score", "operational_status"])
        df_a = _parse_status(df_a)
        
        df_c = pd.DataFrame([r.data() for r in session.run("MATCH (c:Crew) RETURN c.crew_id AS crew_id, c.name AS name, c.rank AS rank, c.aircraft_type_qualified AS aircraft_type_qualified")])
        if df_c.empty: df_c = pd.DataFrame(columns=["crew_id", "name", "rank", "aircraft_type_qualified"])

        df_m = pd.DataFrame([r.data() for r in session.run("MATCH (m:Mission) OPTIONAL MATCH (a:Aircraft)-[:EXECUTED]->(m) OPTIONAL MATCH (c:Crew)-[:PARTICIPATED_IN]->(m) RETURN m.mission_id AS mission_id, m.date AS date, m.mission_type AS mission_type, coalesce(m.fuel_used, 0) AS fuel_used, a.aircraft_id AS aircraft_id, c.crew_id AS crew_id")])
        if df_m.empty: df_m = pd.DataFrame(columns=["mission_id", "date", "mission_type", "fuel_used", "aircraft_id", "crew_id"])
    driver.close()
    return df_a, df_c, df_m

@st.cache_data(ttl=10)
def load_army():
    driver = _get_neo4j_driver()
    with driver.session() as session:
        df_a = pd.DataFrame([r.data() for r in session.run("MATCH (a:ArmyAsset) RETURN a.asset_id AS asset_id, a.asset_type AS asset_type, a.unit AS unit, a.last_service_date AS last_service_date, coalesce(a.operational_hours, 0) AS operational_hours, coalesce(a.readiness_base_score, 100 - (toFloat(coalesce(a.operational_hours, 0)) * 0.5)) AS final_readiness_score, coalesce(a.operational_status, '') AS operational_status")])
        if df_a.empty: df_a = pd.DataFrame(columns=["asset_id", "asset_type", "unit", "last_service_date", "operational_hours", "final_readiness_score", "operational_status"])
        df_a = _parse_status(df_a)
        
        df_c = pd.DataFrame([r.data() for r in session.run("MATCH (c:ArmyPersonnel) RETURN c.crew_id AS crew_id, c.name AS name, c.rank AS rank, c.vehicle_qualified AS vehicle_qualified")])
        if df_c.empty: df_c = pd.DataFrame(columns=["crew_id", "name", "rank", "vehicle_qualified"])

        df_o = pd.DataFrame([r.data() for r in session.run("MATCH (o:ArmyOperation) OPTIONAL MATCH (a:ArmyAsset)-[:DEPLOYED_FOR]->(o) OPTIONAL MATCH (p:ArmyPersonnel)-[:ENGAGED_IN]->(o) RETURN o.op_id AS op_id, o.date AS date, o.op_type AS op_type, coalesce(o.ammo_expended, 0) AS ammo_expended, a.asset_id AS asset_id, p.crew_id AS crew_id")])
        if df_o.empty: df_o = pd.DataFrame(columns=["op_id", "date", "op_type", "ammo_expended", "asset_id", "crew_id"])
    driver.close()
    return df_a, df_c, df_o

@st.cache_data(ttl=10)
def load_navy():
    driver = _get_neo4j_driver()
    with driver.session() as session:
        df_v = pd.DataFrame([r.data() for r in session.run("MATCH (v:Vessel) RETURN v.vessel_id AS vessel_id, v.vessel_type AS vessel_type, v.flotilla AS flotilla, v.last_refit_date AS last_refit_date, coalesce(v.sea_hours, 0) AS sea_hours, coalesce(v.readiness_base_score, 100 - (toFloat(coalesce(v.sea_hours, 0)) * 0.2)) AS final_readiness_score, coalesce(v.operational_status, '') AS operational_status")])
        if df_v.empty: df_v = pd.DataFrame(columns=["vessel_id", "vessel_type", "flotilla", "last_refit_date", "sea_hours", "final_readiness_score", "operational_status"])
        df_v = _parse_status(df_v)
        
        df_c = pd.DataFrame([r.data() for r in session.run("MATCH (c:NavyCrew) RETURN c.crew_id AS crew_id, c.name AS name, c.rank AS rank, c.vessel_qualified AS vessel_qualified")])
        if df_c.empty: df_c = pd.DataFrame(columns=["crew_id", "name", "rank", "vessel_qualified"])

        df_s = pd.DataFrame([r.data() for r in session.run("MATCH (s:Sortie) OPTIONAL MATCH (v:Vessel)-[:SAILED_FOR]->(s) OPTIONAL MATCH (c:NavyCrew)-[:ASSIGNED_TO]->(s) RETURN s.sortie_id AS sortie_id, s.date AS date, s.sortie_type AS sortie_type, coalesce(s.fuel_consumed_tons, 0) AS fuel_consumed_tons, v.vessel_id AS vessel_id, c.crew_id AS crew_id")])
        if df_s.empty: df_s = pd.DataFrame(columns=["sortie_id", "date", "sortie_type", "fuel_consumed_tons", "vessel_id", "crew_id"])
    driver.close()
    return df_v, df_c, df_s


def _score_color(s):
    try:
        from agents.ontology_engine import get_operational_threshold
        t = get_operational_threshold()
    except Exception:
        t = 5
    if s >= t: return "#00e676"
    if s >= max(0, t - 20): return "#ff9800"
    return "#ff4b4b"

def _score_badge(s):
    try:
        from agents.ontology_engine import get_operational_threshold
        t = get_operational_threshold()
    except Exception:
        t = 5
    if s >= t: return "🟢 Operational"
    if s >= max(0, t - 20): return "🟡 Needs Attention"
    return "🔴 Critical"