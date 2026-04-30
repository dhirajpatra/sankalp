"""
darshan_alerts_panel.py – SANKALP Live Alerts & Optimization Panel
Renders inside Darshan as a sidebar badge + full alerts view.
Reads from the SQLite alerts DB written by readiness_monitor.py.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

try:
    from readiness_monitor import (
        get_recent_alerts, get_snapshots, ack_all_alerts,
        unread_count, start_monitor, is_running,
    )
except ImportError:
    from agents.readiness_monitor import (
        get_recent_alerts, get_snapshots, ack_all_alerts,
        unread_count, start_monitor, is_running,
    )


# ── Ensure monitor is running ─────────────────────────────────────────────────

def ensure_monitor():
    """Call once at Streamlit startup to launch background thread."""
    if not is_running():
        start_monitor()


# ── Sidebar badge ─────────────────────────────────────────────────────────────

def render_alert_badge():
    """
    Renders a small badge in the sidebar showing unread alert count.
    Call this from darshan_left_sidebar.py after the branch nav.
    """
    n = unread_count()
    color = "#E24B4A" if n > 0 else "#639922"
    label = f"{n} unread alert{'s' if n != 1 else ''}" if n > 0 else "All clear"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
        f'<div style="width:10px;height:10px;border-radius:50%;background:{color};flex-shrink:0;"></div>'
        f'<span style="font-size:12px;color:var(--color-text-secondary);">{label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Full alerts panel ─────────────────────────────────────────────────────────

def render_alerts_panel():
    st.markdown("## Optimization Engine — Live Alerts")
    st.caption(
        "Event-driven monitoring: the readiness engine polls Neo4j every 10 s, "
        "evaluates all doctrine rules, and auto-writes alerts when tiers change."
    )

    # ── Controls row ──────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("Mark all read", use_container_width=True):
            ack_all_alerts()
            st.rerun()
    with c2:
        show_all = st.checkbox("Show acknowledged", value=False)
    with c3:
        n = unread_count()
        color = "#E24B4A" if n > 0 else "#639922"
        st.markdown(
            f'<div style="padding:6px 12px;border-radius:6px;border:0.5px solid var(--color-border-tertiary);'
            f'background:var(--color-background-secondary);font-size:13px;">'
            f'<span style="color:{color};font-weight:500;">{n} unread alert{"s" if n!=1 else ""}</span>'
            f' &nbsp;·&nbsp; Monitor: '
            f'<span style="color:{"#639922" if is_running() else "#E24B4A"};">'
            f'{"running" if is_running() else "stopped"}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Fleet readiness timeline ───────────────────────────────────────────────
    snapshots = get_snapshots(limit=60)
    if len(snapshots) >= 2:
        st.markdown("#### Fleet readiness over time")
        df_snap = pd.DataFrame(snapshots)
        df_snap["ts"] = pd.to_datetime(df_snap["ts"])

        import altair as alt
        base = alt.Chart(df_snap).properties(height=160)
        lines = (
            base.mark_line(point=False).encode(
                x=alt.X("ts:T", title=None, axis=alt.Axis(format="%H:%M")),
                y=alt.Y("value:Q", title="Avg readiness %", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("branch:N", scale=alt.Scale(
                    domain=["IAF", "Army", "Navy"],
                    range=["#185FA5", "#3B6D11", "#0F6E56"],
                )),
                strokeDash=alt.StrokeDash("branch:N", scale=alt.Scale(
                    domain=["IAF", "Army", "Navy"],
                    range=[[1,0], [4,2], [2,2]],
                )),
                tooltip=["ts:T", "branch:N", alt.Tooltip("value:Q", format=".1f")],
            )
        )

        melted = df_snap[["ts", "iaf_ready", "army_ready", "navy_ready"]].melt(
            id_vars="ts",
            value_vars=["iaf_ready", "army_ready", "navy_ready"],
            var_name="branch", value_name="value",
        )
        melted["branch"] = melted["branch"].map(
            {"iaf_ready": "IAF", "army_ready": "Army", "navy_ready": "Navy"}
        )
        lines = alt.Chart(melted).mark_line(point=False).encode(
            x=alt.X("ts:T", title=None, axis=alt.Axis(format="%H:%M")),
            y=alt.Y("value:Q", title="Avg readiness %", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("branch:N", scale=alt.Scale(
                domain=["IAF", "Army", "Navy"],
                range=["#185FA5", "#3B6D11", "#0F6E56"],
            )),
            strokeDash=alt.StrokeDash("branch:N", scale=alt.Scale(
                domain=["IAF", "Army", "Navy"],
                range=[[1,0], [4,2], [2,2]],
            )),
            tooltip=["ts:T", "branch:N", alt.Tooltip("value:Q", format=".1f")],
        ).properties(height=160)
        st.altair_chart(lines, use_container_width=True)

    # ── Op counts timeline ────────────────────────────────────────────────────
    if len(snapshots) >= 2:
        df_snap = pd.DataFrame(snapshots)
        df_snap["ts"] = pd.to_datetime(df_snap["ts"])
        melted_op = df_snap[["ts", "iaf_op", "army_op", "navy_op"]].melt(
            id_vars="ts",
            value_vars=["iaf_op", "army_op", "navy_op"],
            var_name="branch", value_name="count",
        )
        melted_op["branch"] = melted_op["branch"].map(
            {"iaf_op": "IAF aircraft", "army_op": "Army assets", "navy_op": "Navy vessels"}
        )
        op_chart = alt.Chart(melted_op).mark_line(point=True, size=1.5).encode(
            x=alt.X("ts:T", title=None, axis=alt.Axis(format="%H:%M")),
            y=alt.Y("count:Q", title="Operational count"),
            color=alt.Color("branch:N", scale=alt.Scale(
                domain=["IAF aircraft", "Army assets", "Navy vessels"],
                range=["#185FA5", "#3B6D11", "#0F6E56"],
            )),
            tooltip=["ts:T", "branch:N", "count:Q"],
        ).properties(height=120)
        st.altair_chart(op_chart, use_container_width=True)

    # ── Alert log ─────────────────────────────────────────────────────────────
    st.markdown("#### Event log")
    alerts = get_recent_alerts(limit=100, unread_only=not show_all)

    if not alerts:
        st.success("No alerts. All doctrine rules stable." if not show_all else "No alerts recorded yet.")
    else:
        TIER_ICONS = {"SUPERIOR": "🏆", "ADEQUATE": "🟡", "INSUFFICIENT": "🔴"}
        DIR_COLOR  = {"degraded": "#A32D2D", "improved": "#3B6D11"}

        for a in alerts:
            direction = a.get("direction", "degraded")
            icon      = "▼" if direction == "degraded" else "▲"
            color     = DIR_COLOR.get(direction, "#888")
            acked     = a.get("ack", 0)
            opacity   = "0.5" if acked else "1.0"
            prev_icon = TIER_ICONS.get(a.get("prev_tier",""), "")
            new_icon  = TIER_ICONS.get(a.get("new_tier",""), "")

            st.markdown(
                f'<div style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;'
                f'border-bottom:0.5px solid var(--color-border-tertiary);opacity:{opacity};">'
                f'<div style="color:{color};font-size:16px;min-width:16px;">{icon}</div>'
                f'<div style="flex:1;">'
                f'<div style="font-size:13px;font-weight:500;color:var(--color-text-primary);">'
                f'{a["rule_name"]}</div>'
                f'<div style="font-size:12px;color:var(--color-text-secondary);margin-top:2px;">'
                f'{prev_icon} {a.get("prev_tier","")} → {new_icon} {a.get("new_tier","")} &nbsp;·&nbsp; '
                f'IAF:{a.get("iaf_op",0)} Army:{a.get("army_op",0)} Navy:{a.get("navy_op",0)}'
                f'</div>'
                f'</div>'
                f'<div style="font-size:11px;color:var(--color-text-secondary);min-width:90px;text-align:right;">'
                f'{a.get("ts","")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
