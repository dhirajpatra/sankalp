"""
Darshan (दर्शन) – Sankalp Defence Dashboard
DRDO requirement: Command-level situational awareness for IAF asset management.
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

# --- Page config ---
st.set_page_config(
    page_title="Sankalp – Defence Digital Twin",
    page_icon="🛡️",
    layout="wide",
)

GOLD_DB = "sankalp_gold.db"

# --- Styling ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Exo 2', sans-serif; }
    .stApp { background: #0a0e17; color: #c8d6e5; }
    h1, h2, h3 { color: #00e5ff; font-family: 'Share Tech Mono', monospace; }
    .metric-card {
        background: #111827; border: 1px solid #1e3a5f;
        border-radius: 8px; padding: 16px; text-align: center;
    }
    .at-risk { color: #ff4b4b !important; font-weight: bold; }
    .healthy { color: #00e676 !important; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True,
)


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
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "sankalp123"))
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

# --- Main ---
st.title("🛡️ SANKALP — भारतीय वायु सेना Digital Twin")
st.caption("Open Source Ontology Platform | IAF Asset Intelligence")

tabs = st.tabs(["📊 Asset Overview", "✈️ Aircraft Detail", "🎯 Log Mission", "⚠️ Readiness Alert"])

# Tab 1: Asset Overview
with tabs[0]:
    st.subheader("Fleet Readiness Dashboard")
    cols = st.columns(len(aircraft_df))
    for i, (_, row) in enumerate(aircraft_df.iterrows()):
        score = row.get("final_readiness_score", row.get("readiness_base_score", 0))
        color = "#00e676" if score >= 60 else "#ff9800" if score >= 40 else "#ff4b4b"
        with cols[i]:
            st.markdown(
                f"""<div class="metric-card">
                <div style="font-size:11px; color:#888">{row['aircraft_id']}</div>
                <div style="font-size:14px; font-weight:bold; color:#c8d6e5">{row['type']}</div>
                <div style="font-size:28px; font-weight:bold; color:{color}">{score:.0f}%</div>
                <div style="font-size:11px; color:#555">{row['squadron']}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.dataframe(
        aircraft_df[["aircraft_id", "type", "squadron", "flight_hours", "last_maintenance_date"]].rename(
            columns={"aircraft_id": "ID", "type": "Type", "squadron": "Squadron",
                     "flight_hours": "Flight Hrs", "last_maintenance_date": "Last Maint."}
        ),
        use_container_width=True,
    )

# Tab 2: Aircraft Detail
with tabs[1]:
    st.subheader("Aircraft Intelligence View")
    selected_id = st.selectbox("Select Aircraft", aircraft_df["aircraft_id"].tolist())
    row = aircraft_df[aircraft_df["aircraft_id"] == selected_id].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Type", row["type"])
    c2.metric("Squadron", row["squadron"])
    c3.metric("Flight Hours", f"{row['flight_hours']:.0f} hrs")

    score = row.get("final_readiness_score", row.get("readiness_base_score", 0))
    st.metric("Readiness Score", f"{score:.1f}%",
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
            use_container_width=True,
        )
    else:
        st.info("No missions logged for this aircraft.")

# Tab 3: Log Mission
with tabs[2]:
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

# Tab 4: Readiness Alert
with tabs[3]:
    st.subheader("⚠️ Maintenance Alert — Bottom Readiness Aircraft")
    at_risk_df = aircraft_df.sort_values(
        "final_readiness_score" if "final_readiness_score" in aircraft_df.columns else "readiness_base_score"
    ).head(3)

    for _, row in at_risk_df.iterrows():
        score = row.get("final_readiness_score", row.get("readiness_base_score", 0))
        status = "🔴 CRITICAL" if score < 40 else "🟡 WATCH"
        with st.expander(f"{status} — {row['aircraft_id']} ({row['type']}) | Score: {score:.1f}%"):
            st.write(f"**Squadron:** {row['squadron']}")
            st.write(f"**Flight Hours:** {row['flight_hours']:.0f}")
            st.write(f"**Last Maintenance:** {row['last_maintenance_date']}")
            st.warning("Recommend scheduling depot-level inspection (IAF SOPs apply).")
