"""
Darshan (दर्शन) v2 – Sankalp Defence Digital Twin Ontology Platform
Multi-branch: IAF · Army · Navy
Palantir Foundry-style Ontology Platform
"""

import streamlit as st
import sqlite3
import pandas as pd
import os
import random
import string
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

STYLES = "assets/styles/style.css"

# ── DB paths ────────────────────────────────────────────────────────────────
IAF_DB   = "sankalp_gold.db"
ARMY_DB  = "sankalp_army_gold.db"
NAVY_DB  = "sankalp_navy_gold.db"

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sankalp – Defence Digital Twin",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), STYLES)
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        st.warning(f"Stylesheet not found: {css_path}")

load_css()


# ── Session defaults ─────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "branch":       "iaf",   # iaf | army | navy
        "tab":          0,
        "sel_asset":    None,
        "metric_panel": None,    # None | "critical" | "crew" | "missions" | "ops" | "sorties" etc.
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── DB helpers ────────────────────────────────────────────────────────────────
def _conn(db): return sqlite3.connect(db, check_same_thread=False)

@st.cache_data(ttl=30)
def load_iaf():
    try:
        df_a = pd.read_sql("SELECT * FROM aircraft_readiness", _conn(IAF_DB))
    except Exception:
        df_a = pd.read_sql("SELECT *, readiness_base_score as final_readiness_score FROM aircraft_gold", _conn(IAF_DB))
    df_c = pd.read_sql("SELECT * FROM crew_gold",     _conn(IAF_DB))
    df_m = pd.read_sql("SELECT * FROM missions_gold", _conn(IAF_DB))
    return df_a, df_c, df_m

@st.cache_data(ttl=30)
def load_army():
    c = _conn(ARMY_DB)
    try:
        df_a = pd.read_sql("SELECT * FROM asset_readiness", c)
    except Exception:
        df_a = pd.read_sql("SELECT * FROM assets_gold", c)
        df_a["final_readiness_score"] = df_a["readiness_base_score"]
    df_c = pd.read_sql("SELECT * FROM army_crew_gold", c)
    df_o = pd.read_sql("SELECT * FROM ops_gold",       c)
    return df_a, df_c, df_o

@st.cache_data(ttl=30)
def load_navy():
    c = _conn(NAVY_DB)
    try:
        df_v = pd.read_sql("SELECT * FROM vessel_readiness", c)
    except Exception:
        df_v = pd.read_sql("SELECT * FROM vessels_gold", c)
        df_v["final_readiness_score"] = df_v["readiness_base_score"]
    df_c = pd.read_sql("SELECT * FROM navy_crew_gold",  c)
    df_s = pd.read_sql("SELECT * FROM sorties_gold",    c)
    return df_v, df_c, df_s


def _score_color(s):
    if s >= 60: return "#00e676"
    if s >= 40: return "#ff9800"
    return "#ff4b4b"

def _score_badge(s):
    if s >= 60: return "🟢 Operational"
    if s >= 40: return "🟡 Needs Attention"
    return "🔴 Critical"


# ── Left sidebar ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<a href="/" target="_self" style="text-decoration:none;">'
        '<img src="https://upload.wikimedia.org/wikipedia/commons/5/55/Emblem_of_India.svg" '
        'width="60" style="display:block;margin:0 auto 8px;">'
        '<div style="text-align:center;font-family:\'Share Tech Mono\',monospace;'
        'color:#00e5ff;font-size:18px;letter-spacing:2px;">SANKALP</div>'
        '</a>'
        '<div style="text-align:center;color:#7a9bb5;font-size:10px;margin-bottom:16px;">'
        'DEFENCE ONTOLOGY PLATFORM</div><div style="text-align:center;color:#00e5ff;font-size:12px;margin-bottom:12px;letter-spacing:1px;">DATA + LOGIC + ACTION</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown('<div style="color:#7a9bb5;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">BRANCHES</div>', unsafe_allow_html=True)

    branches = [
        ("iaf",   "✈️", "Indian Air Force", "IAF"),
        ("army",  "🪖", "Indian Army",       "ARMY"),
        ("navy",  "⚓", "Indian Navy",       "NAVY"),
    ]
    for key, icon, label, short in branches:
        active = "active" if st.session_state.branch == key else ""
        if st.button(f"{icon}  {label}", key=f"branch_{key}", use_container_width=True):
            st.session_state.branch = key
            st.session_state.tab = 0
            st.session_state.sel_asset = None
            st.rerun()

    st.markdown("---")

    # Live stats per branch
    branch = st.session_state.branch
    try:
        if branch == "iaf":
            df_a, df_c, df_m = load_iaf()
            st.markdown(f"**✈️ Aircraft:** {len(df_a)}")
            st.markdown(f"**👤 Crew:** {len(df_c)}")
            st.markdown(f"**🎯 Missions:** {len(df_m)}")
        elif branch == "army":
            df_a, df_c, df_m = load_army()
            st.markdown(f"**🛡️ Assets:** {len(df_a)}")
            st.markdown(f"**👤 Personnel:** {len(df_c)}")
            st.markdown(f"**⚔️ Operations:** {len(df_m)}")
        else:
            df_v, df_c, df_s = load_navy()
            st.markdown(f"**⚓ Vessels:** {len(df_v)}")
            st.markdown(f"**👤 Crew:** {len(df_c)}")
            st.markdown(f"**🌊 Sorties:** {len(df_s)}")
    except Exception:
        st.caption("Loading data…")

    st.markdown("---")
    st.caption("Agents: Ganana · Shodhan · Bandhan · Bhavishyavani · Darshan")
    st.caption("v2.0 | Palantir-style Ontology")


# ═══════════════════════════════════════════════════════════════════════════
#  BRANCH RENDERERS
# ═══════════════════════════════════════════════════════════════════════════

def render_readiness_chart(df, id_col, type_col, unit_col, score_col):
    """Generic stacked bar chart for any branch."""
    import altair as alt
    chart_df = df[[id_col, type_col, unit_col, score_col]].copy()
    chart_df.columns = ["asset_id", "asset_type", "unit", "Score"]
    chart_df["Status"] = chart_df["Score"].apply(
        lambda s: "Operational" if s >= 60 else "Needs Attention" if s >= 40 else "Critical"
    )
    chart_df["Count"] = 1
    color_scale = alt.Scale(
        domain=["Operational", "Needs Attention", "Critical"],
        range=["#00e676", "#ff9800", "#ff4b4b"]
    )
    selection = alt.selection_point(fields=["asset_id"], name="sel")
    chart = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X("unit:N", title="Unit / Squadron", axis=alt.Axis(labelAngle=-40)),
        y=alt.Y("Count:Q", title="Assets"),
        color=alt.Color("Status:N", scale=color_scale),
        detail="asset_id:N",
        tooltip=["asset_id", "asset_type", "unit", "Score", "Status"],
        opacity=alt.condition(selection, alt.value(1), alt.value(0.55)),
    ).properties(height=340).add_params(selection)
    return chart, chart_df


def metrics_row(items):
    """Render a row of plain (non-clickable) metric boxes. items = list of (label, value)"""
    cols = st.columns(len(items))
    for col, (lbl, val) in zip(cols, items):
        with col:
            st.markdown(
                f'<div class="metric-box">'
                f'<div class="metric-val">{val}</div>'
                f'<div class="metric-lbl">{lbl}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def clickable_metrics_row(items, key_prefix="m"):
    """
    Render metric boxes as clickable Streamlit buttons.
    items = list of (label, value, panel_key, clickable:bool)
    Clicking a box toggles st.session_state.metric_panel.
    Returns nothing – callers read st.session_state.metric_panel.
    """
    cols = st.columns(len(items))
    for i, (col, (lbl, val, panel_key, clickable)) in enumerate(zip(cols, items)):
        with col:
            if clickable:
                active = st.session_state.metric_panel == panel_key
                border_color = "#00e5ff" if active else "#1e3a5f"
                bg_color     = "#0d1f30" if active else "#0a1520"
                # Render as a styled button via markdown label + Streamlit button
                st.markdown(
                    f'<div style="background:{bg_color};border:1px solid {border_color};'
                    f'border-radius:6px;padding:2px 4px;text-align:center;margin-bottom:-8px;">'
                    f'<div style="font-size:26px;font-weight:700;color:#00e5ff;'
                    f'font-family:\'Share Tech Mono\',monospace;">{val}</div>'
                    f'<div style="font-size:10px;color:#7a9bb5;text-transform:uppercase;'
                    f'letter-spacing:1px;padding-bottom:4px;">{lbl} ▾</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("", key=f"{key_prefix}_{i}_{panel_key}",
                             use_container_width=True,
                             help=f"Click to see {lbl} details"):
                    st.session_state.metric_panel = None if active else panel_key
                    st.rerun()
            else:
                st.markdown(
                    f'<div class="metric-box">'
                    f'<div class="metric-val">{val}</div>'
                    f'<div class="metric-lbl">{lbl}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def render_metric_detail(panel_key, aircraft_df, crew_df, missions_df,
                         score_col, type_col,
                         asset_label="Aircraft", mission_label="Mission"):
    """
    Render the expandable detail panel beneath the metrics row.
    panel_key: 'critical' | 'watch' | 'operational' | 'crew' | 'missions'
    """
    if st.session_state.metric_panel is None:
        return

    key = st.session_state.metric_panel

    # ── Critical aircraft ──────────────────────────────────────────────────
    if key == "critical":
        crit_df = aircraft_df[aircraft_df[score_col] < 40].copy()
        st.markdown(
            f'<div class="detail-panel">'
            f'<div class="detail-panel-title">🔴 CRITICAL {asset_label.upper()}S'
            f' &nbsp;–&nbsp; {len(crit_df)} requiring immediate attention</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if crit_df.empty:
            st.success("No critical assets. All units above threshold.")
        else:
            display = crit_df[["aircraft_id", type_col, "squadron", score_col,
                                "flight_hours", "last_maintenance_date"]].copy()
            display.columns = ["ID", "Type", "Squadron/Unit", "Readiness %", "Flight Hrs", "Last Maint."]
            display["Readiness %"] = display["Readiness %"].round(1)
            display = display.sort_values("Readiness %")
            st.dataframe(display, use_container_width=True, hide_index=True)
            # Bar mini-chart
            import altair as alt
            bar = alt.Chart(display).mark_bar(color="#ff4b4b").encode(
                x=alt.X("Readiness %:Q", scale=alt.Scale(domain=[0, 100])),
                y=alt.Y("ID:N", sort="-x"),
                tooltip=["ID", "Type", "Squadron/Unit", "Readiness %"],
            ).properties(height=min(40 * len(display) + 40, 320))
            st.altair_chart(bar, use_container_width=True)

    # ── Watch aircraft ─────────────────────────────────────────────────────
    elif key == "watch":
        watch_df = aircraft_df[
            (aircraft_df[score_col] >= 40) & (aircraft_df[score_col] < 60)
        ].copy()
        st.markdown(
            f'<div class="detail-panel">'
            f'<div class="detail-panel-title">🟡 WATCH {asset_label.upper()}S'
            f' &nbsp;–&nbsp; {len(watch_df)} under monitoring</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if watch_df.empty:
            st.success("No assets in watch state.")
        else:
            display = watch_df[["aircraft_id", type_col, "squadron", score_col,
                                 "flight_hours", "last_maintenance_date"]].copy()
            display.columns = ["ID", "Type", "Squadron/Unit", "Readiness %", "Flight Hrs", "Last Maint."]
            display["Readiness %"] = display["Readiness %"].round(1)
            st.dataframe(display.sort_values("Readiness %"), use_container_width=True, hide_index=True)

    # ── Operational aircraft ───────────────────────────────────────────────
    elif key == "operational":
        op_df = aircraft_df[aircraft_df[score_col] >= 60].copy()
        st.markdown(
            f'<div class="detail-panel">'
            f'<div class="detail-panel-title">🟢 OPERATIONAL {asset_label.upper()}S'
            f' &nbsp;–&nbsp; {len(op_df)} mission-ready</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        display = op_df[["aircraft_id", type_col, "squadron", score_col,
                          "flight_hours", "last_maintenance_date"]].copy()
        display.columns = ["ID", "Type", "Squadron/Unit", "Readiness %", "Flight Hrs", "Last Maint."]
        display["Readiness %"] = display["Readiness %"].round(1)
        st.dataframe(display.sort_values("Readiness %", ascending=False),
                     use_container_width=True, hide_index=True)

    # ── Crew roster ───────────────────────────────────────────────────────
    elif key == "crew":
        st.markdown(
            f'<div class="detail-panel">'
            f'<div class="detail-panel-title">👤 CREW ROSTER'
            f' &nbsp;–&nbsp; {len(crew_df)} personnel</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        # Rank breakdown
        rank_counts = crew_df["rank"].value_counts().reset_index()
        rank_counts.columns = ["Rank", "Count"]
        c1, c2 = st.columns([1, 2])
        with c1:
            import altair as alt
            pie = alt.Chart(rank_counts).mark_arc(innerRadius=40).encode(
                theta=alt.Theta("Count:Q"),
                color=alt.Color("Rank:N", scale=alt.Scale(scheme="blues")),
                tooltip=["Rank", "Count"],
            ).properties(height=200, title="By Rank")
            st.altair_chart(pie, use_container_width=True)
        with c2:
            qual_col = [c for c in crew_df.columns if "qualif" in c.lower() or "type" in c.lower()]
            show_cols = ["crew_id", "name", "rank"] + qual_col[:1]
            display = crew_df[show_cols].copy()
            display.columns = ["ID", "Name", "Rank"] + (["Qualified On"] if qual_col else [])
            st.dataframe(display, use_container_width=True, hide_index=True, height=220)

    # ── Missions / Operations / Sorties ───────────────────────────────────
    elif key in ("missions", "ops", "sorties"):
        label_map = {"missions": "MISSIONS", "ops": "OPERATIONS", "sorties": "SORTIES"}
        panel_title = label_map.get(key, key.upper())

        # Detect date col
        date_col = next((c for c in missions_df.columns if "date" in c.lower()), None)
        type_col2 = next((c for c in missions_df.columns
                          if any(k in c.lower() for k in ["mission_type","op_type","sortie_type"])), None)

        st.markdown(
            f'<div class="detail-panel">'
            f'<div class="detail-panel-title">🎯 {panel_title}'
            f' &nbsp;–&nbsp; {len(missions_df)} logged</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([1, 2])
        with c1:
            if type_col2:
                import altair as alt
                mc = missions_df[type_col2].value_counts().reset_index()
                mc.columns = ["Type", "Count"]
                bar = alt.Chart(mc).mark_bar().encode(
                    x=alt.X("Count:Q"),
                    y=alt.Y("Type:N", sort="-x"),
                    color=alt.value("#00e5ff"),
                    tooltip=["Type", "Count"],
                ).properties(height=200, title="By Type")
                st.altair_chart(bar, use_container_width=True)
        with c2:
            if date_col:
                import altair as alt
                try:
                    ts = missions_df.copy()
                    ts[date_col] = pd.to_datetime(ts[date_col], errors="coerce")
                    ts = ts.dropna(subset=[date_col])
                    ts["Month"] = ts[date_col].dt.to_period("M").astype(str)
                    monthly = ts.groupby("Month").size().reset_index(name="Count")
                    line = alt.Chart(monthly).mark_line(color="#00e5ff", point=True).encode(
                        x=alt.X("Month:O", axis=alt.Axis(labelAngle=-40)),
                        y=alt.Y("Count:Q"),
                        tooltip=["Month", "Count"],
                    ).properties(height=200, title="Monthly Activity")
                    st.altair_chart(line, use_container_width=True)
                except Exception:
                    pass
        # Full table (last 20)
        st.caption(f"Latest 20 {panel_title.lower()}")
        st.dataframe(missions_df.tail(20), use_container_width=True, hide_index=True)


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
            conn = _conn(IAF_DB)
            conn.execute("INSERT INTO missions_gold VALUES (?,?,?,?,?,?)",
                         (new_id, ac_id, crew_id, str(msn_date), msn_type, fuel))
            conn.execute("UPDATE aircraft_gold SET flight_hours = flight_hours + 1 WHERE aircraft_id = ?", (ac_id,))
            conn.commit(); conn.close()
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
        op   = (assets_df[score_col] >= 60).sum()
        warn = ((assets_df[score_col] >= 40) & (assets_df[score_col] < 60)).sum()
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
            conn = _conn(ARMY_DB)
            conn.execute("INSERT INTO ops_gold VALUES (?,?,?,?,?,?)",
                         (new_id, as_id, crew_id, str(op_date), op_type, ammo))
            conn.execute("UPDATE assets_gold SET operational_hours = operational_hours + 1 WHERE asset_id = ?", (as_id,))
            conn.commit(); conn.close()
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
        op   = (vessels_df[score_col] >= 60).sum()
        warn = ((vessels_df[score_col] >= 40) & (vessels_df[score_col] < 60)).sum()
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
            conn = _conn(NAVY_DB)
            conn.execute("INSERT INTO sorties_gold VALUES (?,?,?,?,?,?)",
                         (new_id, v_id, crew_id, str(s_date), s_type, fuel_t))
            conn.execute("UPDATE vessels_gold SET sea_hours = sea_hours + 1 WHERE vessel_id = ?", (v_id,))
            conn.commit(); conn.close()
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


# ── Route to branch ──────────────────────────────────────────────────────────
branch = st.session_state.branch
if branch == "iaf":
    render_iaf()
elif branch == "army":
    render_army()
elif branch == "navy":
    render_navy()
