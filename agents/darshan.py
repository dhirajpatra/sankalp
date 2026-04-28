"""
Darshan (दर्शन) – Sankalp Defence Dashboard
DRDO requirement: Command-level situational awareness for IAF asset management.
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

STYLESHEET = "assets/styles/style.css"

# --- Page config ---
st.set_page_config(
    page_title="Sankalp – Defence Digital Twin",
    page_icon="🛡️",
    layout="wide",
)

GOLD_DB = "sankalp_gold.db"

# --- Styling ---
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), STYLESHEET)
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()


# --- DB helpers ---
def get_conn():
    return sqlite3.connect(GOLD_DB, check_same_thread=False)


@st.cache_data(ttl=30)
def load_aircraft():
    try:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM aircraft_readiness", conn)
        conn.close()
    except Exception:
        conn = get_conn()
        df = pd.read_sql("SELECT *, readiness_base_score as final_readiness_score FROM aircraft_gold", conn)
        conn.close()
    return df


@st.cache_data(ttl=30)
def load_crew():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM crew_gold", conn)
    conn.close()
    return df


@st.cache_data(ttl=30)
def load_missions():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM missions_gold", conn)
    conn.close()
    return df


def write_mission(aircraft_id, crew_id, mission_date, mission_type, fuel_used):
    conn = get_conn()
    import random, string
    new_id = "MSN-" + "".join(random.choices(string.digits, k=4))
    # Insert mission
    conn.execute(
        "INSERT INTO missions_gold VALUES (?, ?, ?, ?, ?, ?)",
        (new_id, aircraft_id, crew_id, str(mission_date), mission_type, fuel_used),
    )
    # Update flight hours
    conn.execute(
        "UPDATE aircraft_gold SET flight_hours = flight_hours + 1 WHERE aircraft_id = ?",
        (aircraft_id,),
    )
    try:
        conn.execute(
            "UPDATE aircraft_readiness SET flight_hours = flight_hours + 1 WHERE aircraft_id = ?",
            (aircraft_id,),
        )
    except Exception:
        pass
    conn.commit()
    conn.close()
    st.cache_data.clear()
    # Try Neo4j write-back
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            session.run(
                """
                MERGE (m:Mission {mission_id: $mid})
                SET m.date = $date, m.mission_type = $mtype, m.fuel_used = $fuel
                WITH m
                MATCH (a:Aircraft {aircraft_id: $aid})
                MERGE (a)-[:EXECUTED]->(m)
                WITH m
                MATCH (c:Crew {crew_id: $cid})
                MERGE (c)-[:PARTICIPATED_IN]->(m)
                """,
                mid=new_id, date=str(mission_date), mtype=mission_type,
                fuel=fuel_used, aid=aircraft_id, cid=crew_id,
            )
            session.run(
                "MATCH (a:Aircraft {aircraft_id: $aid}) SET a.flight_hours = a.flight_hours + 1",
                aid=aircraft_id,
            )
        driver.close()
    except Exception:
        pass
    return new_id


# --- Sidebar ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/5/55/Emblem_of_India.svg", width=80)
st.sidebar.title("🛡️ SANKALP")
st.sidebar.caption("Defence Digital Twin – MVP")

aircraft_df = load_aircraft()
crew_df = load_crew()
missions_df = load_missions()

st.sidebar.markdown("---")
st.sidebar.markdown(f"**✈️ Aircraft:** {len(aircraft_df)}")
st.sidebar.markdown(f"**👤 Crew:** {len(crew_df)}")
st.sidebar.markdown(f"**🎯 Missions:** {len(missions_df)}")
st.sidebar.markdown("---")
st.sidebar.caption("Agents: Ganana · Shodhan · Bandhan · Bhavishyavani · Darshan")

# --- Initialize session state for tabs ---
if "tab_index" not in st.session_state:
    st.session_state.tab_index = 0
if "selected_aircraft" not in st.session_state:
    st.session_state.selected_aircraft = None

# --- Main ---
st.title("🛡️ SANKALP — भारतीय वायु सेना Digital Twin")
st.caption("Open Source Ontology Platform | IAF Asset Intelligence")

# Tab selector using radio buttons (responds to session state)
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("📊 Asset Overview", use_container_width=True, key="tab_0"):
        st.session_state.tab_index = 0
        st.rerun()
with col2:
    if st.button("✈️ Aircraft Detail", use_container_width=True, key="tab_1"):
        st.session_state.tab_index = 1
        st.rerun()
with col3:
    if st.button("🎯 Log Mission", use_container_width=True, key="tab_2"):
        st.session_state.tab_index = 2
        st.rerun()
with col4:
    if st.button("⚠️ Readiness Alert", use_container_width=True, key="tab_3"):
        st.session_state.tab_index = 3
        st.rerun()

st.markdown("---")

# Conditionally render tabs based on session state
if st.session_state.tab_index == 0:
    st.subheader("Fleet Readiness Dashboard")
    st.caption("Click a bar segment or a card to view aircraft details")
    
    if not aircraft_df.empty:
        import altair as alt
        chart_df = aircraft_df.copy()
        chart_df["Score"] = chart_df.apply(lambda r: r.get("final_readiness_score", r.get("readiness_base_score", 0)), axis=1)
        chart_df["Status"] = chart_df["Score"].apply(lambda s: "Operational" if s >= 60 else "Needs Attention" if s >= 40 else "Critical")
        chart_df["Count"] = 1
        
        color_scale = alt.Scale(
            domain=["Operational", "Needs Attention", "Critical"],
            range=["#00e676", "#ff9800", "#ff4b4b"]
        )
        
        selection = alt.selection_point(fields=['aircraft_id'], name='aircraft_select')
        
        chart = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X("squadron:N", title="Squadron", axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("Count:Q", title="Number of Aircraft"),
            color=alt.Color("Status:N", scale=color_scale, legend=alt.Legend(title="Readiness")),
            detail="aircraft_id:N",
            tooltip=["aircraft_id", "aircraft_type", "squadron", "Score", "Status"],
            opacity=alt.condition(selection, alt.value(1), alt.value(0.5))
        ).properties(
            height=350
        ).add_params(
            selection
        )
        
        event = st.altair_chart(chart, use_container_width=True, on_select="rerun")
        
        if event and event.selection.get("aircraft_select"):
            selected = event.selection["aircraft_select"][0]["aircraft_id"]
            st.session_state.selected_aircraft = selected
            st.session_state.tab_index = 1
            st.rerun()

    with st.expander("Aircraft Cards View (Click to view details)", expanded=False):
        if not aircraft_df.empty:
            cols = st.columns(min(4, len(aircraft_df)))  # Max 4 columns for better layout
            for i, (_, row) in enumerate(aircraft_df.iterrows()):
                score = row.get("final_readiness_score", row.get("readiness_base_score", 0))
                aircraft_type = row.get("aircraft_type", row.get("type", "Unknown"))
                squadron = row.get("squadron", "N/A")
                aircraft_id = row.get("aircraft_id", "Unknown")
                
                col_idx = i % 4
                with cols[col_idx]:
                    # Create clickable button styled as card
                    if st.button(
                        f"{aircraft_id}\n{aircraft_type}\n{score:.0f}%\n{squadron}",
                        key=f"card_{aircraft_id}_{i}",
                        help=f"Click to view {aircraft_id} details"
                    ):
                        st.session_state.selected_aircraft = aircraft_id
                        st.session_state.tab_index = 1
                        st.rerun()

    st.markdown("---")
    st.dataframe(
        aircraft_df[["aircraft_id", "aircraft_type", "squadron", "flight_hours", "last_maintenance_date"]].rename(
            columns={"aircraft_id": "ID", "aircraft_type": "Type", "squadron": "Squadron",
                     "flight_hours": "Flight Hrs", "last_maintenance_date": "Last Maint."}
        ),
        width='stretch',
    )

if st.session_state.tab_index == 1:
    st.subheader("Aircraft Intelligence View")
    
    # Use selected aircraft from card click if available
    default_idx = 0
    if st.session_state.selected_aircraft and st.session_state.selected_aircraft in aircraft_df["aircraft_id"].values:
        default_idx = aircraft_df[aircraft_df["aircraft_id"] == st.session_state.selected_aircraft].index[0]
    
    selected_id = st.selectbox(
        "Select Aircraft", 
        aircraft_df["aircraft_id"].tolist(),
        index=default_idx,
        key="aircraft_select"
    )
    
    # Update session state with selection
    st.session_state.selected_aircraft = selected_id
    
    row = aircraft_df[aircraft_df["aircraft_id"] == selected_id].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Type", row.get("aircraft_type", row.get("type", "Unknown")))
    c2.metric("Squadron", row.get("squadron", "N/A"))
    c3.metric("Flight Hours", f"{float(row.get('flight_hours', 0)):.0f} hrs")

    score = row.get("final_readiness_score", row.get("readiness_base_score", 0))
    st.metric("Readiness Score", f"{float(score):.1f}%",
              delta="Operational" if score >= 60 else "Needs Attention")

    st.markdown("**Mission History**")
    ac_missions = missions_df[missions_df["aircraft_id"] == selected_id].copy()
    if not ac_missions.empty:
        ac_missions = ac_missions.merge(
            crew_df[["crew_id", "name", "rank"]], on="crew_id", how="left"
        )
        st.dataframe(
            ac_missions[["mission_id", "date", "mission_type", "fuel_used", "name", "rank"]].rename(
                columns={"mission_id": "Mission ID", "date": "Date", "mission_type": "Type",
                         "fuel_used": "Fuel (L)", "name": "Crew", "rank": "Rank"}
            ),
            width='stretch',
        )
    else:
        st.info("No missions logged for this aircraft.")

if st.session_state.tab_index == 2:
    st.subheader("Log New Mission — Field Entry")
    st.caption("Action writes directly to ontology graph (Neo4j) and SQLite gold store.")

    col1, col2 = st.columns(2)
    with col1:
        log_aircraft = st.selectbox("Aircraft", aircraft_df["aircraft_id"].tolist(), key="log_ac")
        log_crew = st.selectbox("Crew Member", crew_df["crew_id"].tolist(),
                                format_func=lambda x: f"{x} – {crew_df[crew_df['crew_id']==x]['name'].values[0]}")
        log_type = st.selectbox("Mission Type", [
            "Combat Air Patrol", "Strike", "Intercept", "Reconnaissance",
            "Air Defence", "CAS", "Logistics", "Training"
        ])
    with col2:
        log_date = st.date_input("Mission Date", value=date.today())
        log_fuel = st.number_input("Fuel Used (Litres)", min_value=500, max_value=8000, value=3000, step=100)

    if st.button("🎯 Submit Mission Log", type="primary"):
        new_msn = write_mission(log_aircraft, log_crew, log_date, log_type, log_fuel)
        st.success(f"Mission {new_msn} logged successfully. Ontology updated.")
        st.balloons()

if st.session_state.tab_index == 3:
    st.subheader("⚠️ Maintenance Alert — Bottom Readiness Aircraft")
    if not aircraft_df.empty:
        sort_col = "final_readiness_score" if "final_readiness_score" in aircraft_df.columns else "readiness_base_score"
        at_risk_df = aircraft_df.sort_values(sort_col).head(3)

        for _, row in at_risk_df.iterrows():
            score = row.get("final_readiness_score", row.get("readiness_base_score", 0))
            status = "🔴 CRITICAL" if score < 40 else "🟡 WATCH"
            aircraft_type = row.get("aircraft_type", row.get("type", "Unknown"))
            with st.expander(f"{status} — {row['aircraft_id']} ({aircraft_type}) | Score: {score:.1f}%"):
                st.write(f"**Squadron:** {row.get('squadron', 'N/A')}")
                st.write(f"**Flight Hours:** {float(row.get('flight_hours', 0)):.0f}")
                st.write(f"**Last Maintenance:** {row.get('last_maintenance_date', 'N/A')}")
                st.warning("Recommend scheduling depot-level inspection (IAF SOPs apply).")
    else:
        st.warning("No aircraft data available.")
