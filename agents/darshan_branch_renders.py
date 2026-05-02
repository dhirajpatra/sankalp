import streamlit as st
import pandas as pd
from config_loader import cfg

# ═══════════════════════════════════════════════════════════════════════════
#  BRANCH RENDERERS
# ═══════════════════════════════════════════════════════════════════════════

def render_readiness_chart(df, id_col, type_col, unit_col, score_col):
    """Generic stacked bar chart for any branch."""
    import altair as alt
    chart_df = df[[id_col, type_col, unit_col, score_col]].copy()
    chart_df.columns = ["asset_id", "asset_type", "unit", "Score"]
    chart_df["Status"] = chart_df["Score"].apply(
        lambda s: "Operational" if s >= 5 else "Needs Attention" if s >= 40 else "Critical"
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
            (aircraft_df[score_col] >= 40) & (aircraft_df[score_col] < 5)
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
        op_df = aircraft_df[aircraft_df[score_col] >= 5].copy()
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
        rows_per_page = cfg("table_rows_per_page", 20)
        st.caption(f"Latest {rows_per_page} {panel_title.lower()}")
        st.dataframe(missions_df.tail(rows_per_page), use_container_width=True, hide_index=True)