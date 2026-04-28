import streamlit as st
import random
import string
from datetime import date
from darshan_db_helper import load_iaf, _get_neo4j_driver, _score_color, _score_badge
from darshan_branch_renders import clickable_metrics_row, render_metric_detail, render_readiness_chart

# ────────────────────────────────────────────────────────────────────────────
#  IAF BRANCH
# ────────────────────────────────────────────────────────────────────────────
def render_iaf():
    st.markdown("## ✈️ Indian Air Force — भारतीय वायु सेना")
    st.caption("IAF Asset Intelligence | Fleet Readiness & Mission Ontology")

    tabs = ["📊 Asset Overview", "✈️ Aircraft Detail", "🎯 Log Mission", "⚠️ Readiness Alert"]
    cols = st.columns(len(tabs))
    for i, (col, label) in enumerate(zip(cols, tabs)):
        with col:
            if st.button(label, key=f"iaf_tab_{i}", use_container_width=True):
                st.session_state.tab = i
                st.rerun()
    st.markdown("---")

    try:
        aircraft_df, crew_df, missions_df = load_iaf()
    except Exception as e:
        st.error(f"IAF data not loaded. Run the pipeline first. ({e})")
        return

    tab = st.session_state.tab

    # ── Overview ──
    if tab == 0:
        score_col = "final_readiness_score" if "final_readiness_score" in aircraft_df.columns else "readiness_base_score"
        type_col  = "aircraft_type" if "aircraft_type" in aircraft_df.columns else "type"

        scores = aircraft_df[score_col]
        op   = int((scores >= 60).sum())
        warn = int(((scores >= 40) & (scores < 60)).sum())
        crit = int((scores < 40).sum())

        # Reset panel if branch changed
        if st.session_state.metric_panel not in (None, "critical", "watch", "operational", "crew", "missions"):
            st.session_state.metric_panel = None

        clickable_metrics_row([
            ("Total Aircraft",  len(aircraft_df), "total",       False),
            ("🟢 Operational",  op,               "operational", True),
            ("🟡 Watch",        warn,             "watch",       True),
            ("🔴 Critical",     crit,             "critical",    True),
            ("Total Crew",      len(crew_df),     "crew",        True),
            ("Total Missions",  len(missions_df), "missions",    True),
        ], key_prefix="iaf_m")

        # Detail panel (renders if a metric box is active)
        render_metric_detail(
            st.session_state.metric_panel,
            aircraft_df, crew_df, missions_df,
            score_col, type_col,
            asset_label="Aircraft", mission_label="Mission",
        )

        st.markdown("<br>", unsafe_allow_html=True)

        chart, _ = render_readiness_chart(aircraft_df, "aircraft_id", type_col, "squadron", score_col)
        event = st.altair_chart(chart, use_container_width=True, on_select="rerun")
        if event and event.selection.get("sel"):
            st.session_state.sel_asset = event.selection["sel"][0]["asset_id"]
            st.session_state.tab = 1
            st.rerun()

        st.markdown("---")
        display_df = aircraft_df[["aircraft_id", type_col, "squadron", "flight_hours", "last_maintenance_date", score_col]].copy()
        display_df.columns = ["ID", "Type", "Squadron", "Flight Hrs", "Last Maint.", "Readiness %"]
        display_df["Readiness %"] = display_df["Readiness %"].round(1)
        st.dataframe(display_df, use_container_width=True)

    # ── Aircraft Detail ──
    elif tab == 1:
        type_col = "aircraft_type" if "aircraft_type" in aircraft_df.columns else "type"
        score_col = "final_readiness_score" if "final_readiness_score" in aircraft_df.columns else "readiness_base_score"
        ids = aircraft_df["aircraft_id"].tolist()
        def_idx = 0
        if st.session_state.sel_asset and st.session_state.sel_asset in ids:
            def_idx = ids.index(st.session_state.sel_asset)
        sel = st.selectbox("Select Aircraft", ids, index=def_idx)
        st.session_state.sel_asset = sel

        row = aircraft_df[aircraft_df["aircraft_id"] == sel].iloc[0]
        score = float(row.get(score_col, 0))
        color = _score_color(score)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Type",         row.get(type_col, "Unknown"))
        c2.metric("Squadron",     row.get("squadron", "N/A"))
        c3.metric("Flight Hours", f"{float(row.get('flight_hours',0)):.0f} hrs")
        c4.metric("Readiness",    f"{score:.1f}%", delta=_score_badge(score))

        st.markdown(
            f'<div class="score-bar-outer"><div class="score-bar-inner" '
            f'style="width:{min(score,100):.0f}%;background:{color};"></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("**Mission History**")
        ac_m = missions_df[missions_df["aircraft_id"] == sel].copy()
        if not ac_m.empty:
            ac_m = ac_m.merge(crew_df[["crew_id","name","rank"]], on="crew_id", how="left")
            st.dataframe(
                ac_m[["mission_id","date","mission_type","fuel_used","name","rank"]].rename(
                    columns={"mission_id":"Mission","date":"Date","mission_type":"Type",
                             "fuel_used":"Fuel(L)","name":"Crew","rank":"Rank"}
                ), use_container_width=True
            )
        else:
            st.info("No missions logged for this aircraft.")

    # ── Log Mission ──
    elif tab == 2:
        st.subheader("Log New Mission")
        type_col = "aircraft_type" if "aircraft_type" in aircraft_df.columns else "type"
        c1, c2 = st.columns(2)
        with c1:
            ac_id    = st.selectbox("Aircraft",    aircraft_df["aircraft_id"].tolist())
            crew_id  = st.selectbox("Crew Member", crew_df["crew_id"].tolist(),
                                    format_func=lambda x: f"{x} – {crew_df[crew_df['crew_id']==x]['name'].values[0]}")
            msn_type = st.selectbox("Mission Type", ["Combat Air Patrol","Strike","Intercept","Reconnaissance","Air Defence","CAS","Logistics","Training"])
        with c2:
            msn_date = st.date_input("Mission Date", value=date.today())
            fuel     = st.number_input("Fuel Used (L)", 500, 8000, 3000, 100)

        if st.button("🎯 Submit Mission Log", type="primary"):
            new_id = "MSN-" + "".join(random.choices(string.digits, k=4))
            driver = _get_neo4j_driver()
            with driver.session() as session:
                session.run("""
                MERGE (m:Mission {mission_id: $mission_id})
                SET m.date = $date, m.mission_type = $type, m.fuel_used = $fuel
                WITH m
                MATCH (a:Aircraft {aircraft_id: $ac_id})
                SET a.flight_hours = coalesce(a.flight_hours, 0) + 1
                MERGE (a)-[:EXECUTED]->(m)
                WITH m
                MATCH (c:Crew {crew_id: $crew_id})
                MERGE (c)-[:PARTICIPATED_IN]->(m)
                """, mission_id=new_id, date=str(msn_date), type=msn_type, fuel=fuel, ac_id=ac_id, crew_id=crew_id)
            driver.close()
            st.cache_data.clear()
            st.success(f"Mission {new_id} logged. Ontology updated.")
            st.balloons()

    # ── Readiness Alert ──
    elif tab == 3:
        score_col = "final_readiness_score" if "final_readiness_score" in aircraft_df.columns else "readiness_base_score"
        type_col  = "aircraft_type" if "aircraft_type" in aircraft_df.columns else "type"
        at_risk = aircraft_df.sort_values(score_col).head(5)
        st.subheader("⚠️ Bottom-5 Aircraft by Readiness")
        for _, row in at_risk.iterrows():
            score = float(row.get(score_col, 0))
            label = "🔴 CRITICAL" if score < 40 else "🟡 WATCH"
            with st.expander(f"{label} — {row['aircraft_id']} ({row.get(type_col,'')}) | {score:.1f}%"):
                st.write(f"**Squadron:** {row.get('squadron','N/A')}")
                st.write(f"**Flight Hours:** {float(row.get('flight_hours',0)):.0f}")
                st.write(f"**Last Maintenance:** {row.get('last_maintenance_date','N/A')}")
                st.warning("Recommend depot-level inspection per IAF SOPs.")
