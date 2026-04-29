import streamlit as st
import random
import string
from datetime import date
from darshan_db_helper import load_navy, _get_neo4j_driver, _score_color, _score_badge
from darshan_branch_renders import clickable_metrics_row, render_metric_detail, render_readiness_chart
from agents.ontology_engine import get_operational_threshold

# ────────────────────────────────────────────────────────────────────────────
#  NAVY BRANCH
# ────────────────────────────────────────────────────────────────────────────
def render_navy():
    st.markdown("## ⚓ Indian Navy — भारतीय नौसेना")
    st.caption("Naval Asset Intelligence | Fleet Readiness & Sortie Ontology")

    tabs = ["📊 Fleet Overview", "⚓ Vessel Detail", "🌊 Log Sortie", "⚠️ Readiness Alert"]
    cols = st.columns(len(tabs))
    for i, (col, label) in enumerate(zip(cols, tabs)):
        with col:
            if st.button(label, key=f"navy_tab_{i}", use_container_width=True):
                st.session_state.tab = i
                st.rerun()
    st.markdown("---")

    try:
        vessels_df, crew_df, sorties_df = load_navy()
    except Exception as e:
        st.error(f"Navy data not loaded. Run `python agents/ganana_navy.py` first. ({e})")
        _show_navy_setup_hint()
        return

    score_col = "final_readiness_score" if "final_readiness_score" in vessels_df.columns else "readiness_base_score"
    tab = st.session_state.tab

    if tab == 0:
        op   = (vessels_df[score_col] >= 5).sum()
        warn = ((vessels_df[score_col] >= 40) & (vessels_df[score_col] < 5)).sum()
        crit = (vessels_df[score_col] < 40).sum()

        if st.session_state.metric_panel not in (None, "critical", "watch", "operational", "navy_crew", "sorties"):
            st.session_state.metric_panel = None

        clickable_metrics_row([
            ("Total Vessels",  len(vessels_df), "total",       False),
            ("🟢 Seaworthy",   int(op),         "operational", True),
            ("🟡 Watch",       int(warn),        "watch",       True),
            ("🔴 Critical",    int(crit),        "critical",    True),
            ("Naval Crew",     len(crew_df),     "navy_crew",   True),
            ("Sorties",        len(sorties_df),  "sorties",     True),
        ], key_prefix="navy_m")

        panel = st.session_state.metric_panel
        mapped_panel = {"navy_crew": "crew", "sorties": "missions"}.get(panel, panel)

        vessels_adapted = vessels_df.rename(columns={
            "vessel_id": "aircraft_id", "flotilla": "squadron",
            "last_refit_date": "last_maintenance_date",
            "sea_hours": "flight_hours",
        })
        sorties_adapted = sorties_df.rename(columns={"sortie_id": "mission_id", "sortie_type": "mission_type",
                                                      "fuel_consumed_tons": "fuel_used"})

        st.session_state.metric_panel = mapped_panel
        render_metric_detail(
            mapped_panel,
            vessels_adapted, crew_df, sorties_adapted,
            score_col, "vessel_type",
            asset_label="Vessel", mission_label="Sortie",
        )
        if mapped_panel in ("crew", "missions"):
            reverse = {"crew": "navy_crew", "missions": "sorties"}
            st.session_state.metric_panel = reverse.get(mapped_panel, mapped_panel)

        st.markdown("<br>", unsafe_allow_html=True)
        chart, _ = render_readiness_chart(vessels_df, "vessel_id", "vessel_type", "flotilla", score_col)
        event = st.altair_chart(chart, use_container_width=True, on_select="rerun")
        if event and event.selection.get("sel"):
            st.session_state.sel_asset = event.selection["sel"][0]["asset_id"]
            st.session_state.tab = 1
            st.rerun()
        st.markdown("---")
        d = vessels_df[["vessel_id","vessel_type","flotilla","sea_hours","last_refit_date", score_col]].copy()
        d.columns = ["ID","Type","Flotilla","Sea Hrs","Last Refit","Readiness %"]
        d["Readiness %"] = d["Readiness %"].round(1)
        st.dataframe(d, use_container_width=True)

    elif tab == 1:
        ids = vessels_df["vessel_id"].tolist()
        def_idx = 0
        if st.session_state.sel_asset and st.session_state.sel_asset in ids:
            def_idx = ids.index(st.session_state.sel_asset)
        sel = st.selectbox("Select Vessel", ids, index=def_idx)
        row = vessels_df[vessels_df["vessel_id"] == sel].iloc[0]
        score = float(row.get(score_col, 0))
        color = _score_color(score)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Type",         row.get("vessel_type","Unknown"))
        c2.metric("Flotilla",     row.get("flotilla","N/A"))
        c3.metric("Sea Hours",    f"{float(row.get('sea_hours',0)):.0f} hrs")
        c4.metric("Readiness",    f"{score:.1f}%", delta=_score_badge(score))
        st.markdown(
            f'<div class="score-bar-outer"><div class="score-bar-inner" '
            f'style="width:{min(score,100):.0f}%;background:{color};"></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("**Sortie History**")
        v_s = sorties_df[sorties_df["vessel_id"] == sel].copy()
        if not v_s.empty:
            v_s = v_s.merge(crew_df[["crew_id","name","rank"]], on="crew_id", how="left")
            st.dataframe(v_s[["sortie_id","date","sortie_type","fuel_consumed_tons","name","rank"]].rename(
                columns={"sortie_id":"Sortie","date":"Date","sortie_type":"Type",
                         "fuel_consumed_tons":"Fuel(T)","name":"Crew","rank":"Rank"}
            ), use_container_width=True)
        else:
            st.info("No sorties logged for this vessel.")

    elif tab == 2:
        st.subheader("Log New Sortie")
        c1, c2 = st.columns(2)
        with c1:
            v_id     = st.selectbox("Vessel",    vessels_df["vessel_id"].tolist())
            crew_id  = st.selectbox("Crew",      crew_df["crew_id"].tolist(),
                                    format_func=lambda x: f"{x} – {crew_df[crew_df['crew_id']==x]['name'].values[0]}")
            s_type   = st.selectbox("Sortie Type", ["Patrol","Anti-Submarine Warfare","Humanitarian Aid","Fleet Exercise","Strike","ISR","Escort","Port Visit"])
        with c2:
            s_date   = st.date_input("Sortie Date", value=date.today())
            fuel_t   = st.number_input("Fuel Consumed (tons)", 5, 1000, 50, 5)

        if st.button("🌊 Submit Sortie Log", type="primary"):
            new_id = "SRT-" + "".join(random.choices(string.digits, k=4))
            driver = _get_neo4j_driver()
            with driver.session() as session:
                session.run("""
                MERGE (s:Sortie {sortie_id: $sortie_id})
                SET s.date = $date, s.sortie_type = $type, s.fuel_consumed_tons = $fuel
                WITH s
                MATCH (v:Vessel {vessel_id: $v_id})
                SET v.sea_hours = coalesce(v.sea_hours, 0) + 1
                MERGE (v)-[:SAILED_FOR]->(s)
                WITH s
                MATCH (c:NavyCrew {crew_id: $crew_id})
                MERGE (c)-[:ASSIGNED_TO]->(s)
                """, sortie_id=new_id, date=str(s_date), type=s_type, fuel=fuel_t, v_id=v_id, crew_id=crew_id)
            driver.close()
            st.cache_data.clear()
            st.success(f"Sortie {new_id} logged.")

    elif tab == 3:
        st.subheader("⚠️ Bottom-5 Vessels by Readiness")
        at_risk = vessels_df.sort_values(score_col).head(5)
        for _, row in at_risk.iterrows():
            score = float(row.get(score_col, 0))
            label = "🔴 CRITICAL" if score < 40 else "🟡 WATCH"
            with st.expander(f"{label} — {row['vessel_id']} ({row.get('vessel_type','')}) | {score:.1f}%"):
                st.write(f"**Flotilla:** {row.get('flotilla','N/A')}")
                st.write(f"**Sea Hours:** {float(row.get('sea_hours',0)):.0f}")
                st.write(f"**Last Refit:** {row.get('last_refit_date','N/A')}")
                st.warning("Recommend scheduled dockyard refit per IN maintenance schedule.")


def _show_navy_setup_hint():
    st.info(
        "To initialize Navy data, run:\n```bash\npython agents/ganana_navy.py\n"
        "python agents/shodhan_navy.py\n```\n\nSample data will be created in `data/raw/`."
    )