import streamlit as st
import random
import string
from datetime import date
from darshan_db_helper import load_army, _get_neo4j_driver, _score_color, _score_badge
from darshan_branch_renders import clickable_metrics_row, render_metric_detail, render_readiness_chart
from agents.ontology_engine import get_operational_threshold

# ────────────────────────────────────────────────────────────────────────────
#  ARMY BRANCH
# ────────────────────────────────────────────────────────────────────────────
def render_army():
    st.markdown("## 🪖 Indian Army — भारतीय थलसेना")
    st.caption("Army Asset Intelligence | Vehicle Readiness & Operational Ontology")

    tabs = ["📊 Asset Overview", "🛡️ Asset Detail", "⚔️ Log Operation", "⚠️ Readiness Alert"]
    cols = st.columns(len(tabs))
    for i, (col, label) in enumerate(zip(cols, tabs)):
        with col:
            if st.button(label, key=f"army_tab_{i}", use_container_width=True):
                st.session_state.tab = i
                st.rerun()
    st.markdown("---")

    try:
        assets_df, crew_df, ops_df = load_army()
    except Exception as e:
        st.error(f"Army data not loaded. Run `python agents/ganana_army.py` first. ({e})")
        _show_army_setup_hint()
        return

    score_col = "final_readiness_score" if "final_readiness_score" in assets_df.columns else "readiness_base_score"
    tab = st.session_state.tab

    if tab == 0:
        op   = (assets_df[score_col] >= 5).sum()
        warn = ((assets_df[score_col] >= 40) & (assets_df[score_col] < 5)).sum()
        crit = (assets_df[score_col] < 40).sum()

        # Reset panel if switching from another branch
        if st.session_state.metric_panel not in (None, "critical", "watch", "operational", "army_crew", "ops"):
            st.session_state.metric_panel = None

        clickable_metrics_row([
            ("Total Assets",    len(assets_df), "total",       False),
            ("🟢 Operational",  int(op),        "operational", True),
            ("🟡 Watch",        int(warn),      "watch",       True),
            ("🔴 Critical",     int(crit),      "critical",    True),
            ("Personnel",       len(crew_df),   "army_crew",   True),
            ("Operations",      len(ops_df),    "ops",         True),
        ], key_prefix="army_m")

        # Re-map army-specific keys to generic render_metric_detail keys
        panel = st.session_state.metric_panel
        mapped_panel = {"army_crew": "crew", "ops": "missions"}.get(panel, panel)

        # Adapt DataFrames to the generic renderer column names
        assets_adapted = assets_df.rename(columns={
            "asset_id": "aircraft_id", "unit": "squadron",
            "last_service_date": "last_maintenance_date",
            "operational_hours": "flight_hours",
        })
        crew_adapted = crew_df.rename(columns={"vehicle_qualified": "aircraft_type_qualified"})
        ops_adapted  = ops_df.rename(columns={"op_id": "mission_id", "op_type": "mission_type"})

        st.session_state.metric_panel = mapped_panel
        render_metric_detail(
            mapped_panel,
            assets_adapted, crew_adapted, ops_adapted,
            score_col, "asset_type",
            asset_label="Asset", mission_label="Operation",
        )
        # Restore original key so button toggle works correctly
        if mapped_panel in ("crew", "missions"):
            reverse = {"crew": "army_crew", "missions": "ops"}
            st.session_state.metric_panel = reverse.get(mapped_panel, mapped_panel)

        st.markdown("<br>", unsafe_allow_html=True)
        chart, _ = render_readiness_chart(assets_df, "asset_id", "asset_type", "unit", score_col)
        event = st.altair_chart(chart, use_container_width=True, on_select="rerun")
        if event and event.selection.get("sel"):
            st.session_state.sel_asset = event.selection["sel"][0]["asset_id"]
            st.session_state.tab = 1
            st.rerun()
        st.markdown("---")
        d = assets_df[["asset_id","asset_type","unit","operational_hours","last_service_date", score_col]].copy()
        d.columns = ["ID","Type","Unit","Op Hrs","Last Service","Readiness %"]
        d["Readiness %"] = d["Readiness %"].round(1)
        st.dataframe(d, use_container_width=True)

    elif tab == 1:
        ids = assets_df["asset_id"].tolist()
        def_idx = 0
        if st.session_state.sel_asset and st.session_state.sel_asset in ids:
            def_idx = ids.index(st.session_state.sel_asset)
        sel = st.selectbox("Select Asset", ids, index=def_idx)
        row = assets_df[assets_df["asset_id"] == sel].iloc[0]
        score = float(row.get(score_col, 0))
        color = _score_color(score)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Type",            row.get("asset_type","Unknown"))
        c2.metric("Unit",            row.get("unit","N/A"))
        c3.metric("Operational Hrs", f"{float(row.get('operational_hours',0)):.0f} hrs")
        c4.metric("Readiness",       f"{score:.1f}%", delta=_score_badge(score))
        st.markdown(
            f'<div class="score-bar-outer"><div class="score-bar-inner" '
            f'style="width:{min(score,100):.0f}%;background:{color};"></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("**Operation History**")
        ac_ops = ops_df[ops_df["asset_id"] == sel].copy()
        if not ac_ops.empty:
            ac_ops = ac_ops.merge(crew_df[["crew_id","name","rank"]], on="crew_id", how="left")
            st.dataframe(ac_ops[["op_id","date","op_type","ammo_expended","name","rank"]].rename(
                columns={"op_id":"Op ID","date":"Date","op_type":"Type","ammo_expended":"Ammo","name":"Crew","rank":"Rank"}
            ), use_container_width=True)
        else:
            st.info("No operations logged for this asset.")

    elif tab == 2:
        st.subheader("Log New Operation")
        c1, c2 = st.columns(2)
        with c1:
            as_id    = st.selectbox("Asset",      assets_df["asset_id"].tolist())
            crew_id  = st.selectbox("Personnel",  crew_df["crew_id"].tolist(),
                                    format_func=lambda x: f"{x} – {crew_df[crew_df['crew_id']==x]['name'].values[0]}")
            op_type  = st.selectbox("Operation Type", ["Patrol","Live Fire Exercise","Border Vigil","Counter-Insurgency","Strike Mission","Recon","Logistics","Training"])
        with c2:
            op_date  = st.date_input("Operation Date", value=date.today())
            ammo     = st.number_input("Ammo Expended (rounds)", 0, 5000, 0, 50)

        if st.button("⚔️ Submit Operation Log", type="primary"):
            new_id = "OP-" + "".join(random.choices(string.digits, k=4))
            driver = _get_neo4j_driver()
            with driver.session() as session:
                session.run("""
                MERGE (o:ArmyOperation {op_id: $op_id})
                SET o.date = $date, o.op_type = $type, o.ammo_expended = $ammo
                WITH o
                MATCH (a:ArmyAsset {asset_id: $as_id})
                SET a.operational_hours = coalesce(a.operational_hours, 0) + 1
                MERGE (a)-[:DEPLOYED_FOR]->(o)
                WITH o
                MATCH (p:ArmyPersonnel {crew_id: $crew_id})
                MERGE (p)-[:ENGAGED_IN]->(o)
                """, op_id=new_id, date=str(op_date), type=op_type, ammo=ammo, as_id=as_id, crew_id=crew_id)
            driver.close()
            st.cache_data.clear()
            st.success(f"Operation {new_id} logged.")

    elif tab == 3:
        st.subheader("⚠️ Bottom-5 Army Assets by Readiness")
        at_risk = assets_df.sort_values(score_col).head(5)
        for _, row in at_risk.iterrows():
            score = float(row.get(score_col, 0))
            label = "🔴 CRITICAL" if score < 40 else "🟡 WATCH"
            with st.expander(f"{label} — {row['asset_id']} ({row.get('asset_type','')}) | {score:.1f}%"):
                st.write(f"**Unit:** {row.get('unit','N/A')}")
                st.write(f"**Operational Hours:** {float(row.get('operational_hours',0)):.0f}")
                st.write(f"**Last Service:** {row.get('last_service_date','N/A')}")
                st.warning("Recommend scheduled depot maintenance per Army REME SOPs.")


def _show_army_setup_hint():
    st.info(
        "To initialize Army data, run:\n```bash\npython agents/ganana_army.py\n"
        "python agents/shodhan_army.py\n```\n\nSample data will be created in `data/raw/`."
    )