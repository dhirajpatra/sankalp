"""
darshan_yojana_tab.py – SANKALP Mission Planning UI (Yojana)
Renders mission plan recommendations inside Darshan.

Usage in darshan.py:
    from darshan_yojana_tab import render_yojana_panel
    elif branch == "yojana":
        render_yojana_panel()

Add to sidebar branches:
    ("yojana", "📋", "Mission Plan", "PLAN"),
"""

import streamlit as st
from datetime import date, timedelta

try:
    from agents.yojana import MissionPlanner, MISSION_QUALIFICATIONS
except ImportError:
    from yojana import MissionPlanner, MISSION_QUALIFICATIONS

CONFIDENCE_COLOR = {"HIGH": "#00e676", "MEDIUM": "#ff9800", "LOW": "#ff4b4b"}
CONFIDENCE_ICON  = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}
BRANCH_ICON      = {"iaf": "✈️", "army": "🪖", "navy": "⚓"}


def render_yojana_panel():
    st.markdown("## 📋 Yojana — Mission Planning Agent (योजना)")
    st.caption(
        "AI-assisted forward planning: selects optimal assets and crew for upcoming missions "
        "based on live readiness scores, qualifications, and operational history."
    )

    planner = MissionPlanner()

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        branch = st.selectbox("Branch", ["iaf", "army", "navy"],
                              format_func=lambda b: f"{BRANCH_ICON[b]} {b.upper()}")
    with c2:
        mission_types = planner.available_mission_types(branch)
        mission_type  = st.selectbox("Mission Type", mission_types)
    with c3:
        planned_date = st.date_input("Planned Date",
                                     value=date.today() + timedelta(days=1),
                                     min_value=date.today())
    with c4:
        top_n = st.number_input("Top N options", min_value=1, max_value=5, value=3)

    if st.button("🚀 Generate Mission Plans", type="primary", use_container_width=True):
        with st.spinner("Analysing fleet and generating recommendations..."):
            try:
                plans = planner.plan(
                    branch=branch,
                    mission_type=mission_type,
                    planned_date=planned_date.isoformat(),
                    top_n=int(top_n),
                )
            except Exception as e:
                st.error(f"Planning error: {e}")
                return

        if not plans:
            st.warning(
                f"No assets meet the minimum readiness requirement for **{mission_type}**. "
                f"Review the readiness alerts panel for assets needing maintenance."
            )
            return

        st.success(f"Generated **{len(plans)}** mission plan(s) for {mission_type} on {planned_date}")
        st.markdown("---")

        # ── Plan cards ────────────────────────────────────────────────────────
        for plan in plans:
            c_color = CONFIDENCE_COLOR[plan.confidence]
            c_icon  = CONFIDENCE_ICON[plan.confidence]

            with st.expander(
                f"#{plan.rank}  {c_icon} **{plan.confidence}** confidence — "
                f"{plan.asset.asset_id} ({plan.asset.asset_type}) · {plan.crew.name}",
                expanded=(plan.rank == 1),
            ):
                col1, col2, col3 = st.columns([2, 2, 1])

                with col1:
                    st.markdown("**Asset**")
                    st.markdown(f"**ID:** `{plan.asset.asset_id}`")
                    st.markdown(f"**Type:** {plan.asset.asset_type}")
                    st.markdown(f"**Unit:** {plan.asset.unit}")
                    st.markdown(f"**Readiness:** {plan.asset.readiness:.1f}%")
                    # Readiness bar
                    bar_color = (
                        "#00e676" if plan.asset.readiness >= 60
                        else "#ff9800" if plan.asset.readiness >= 40
                        else "#ff4b4b"
                    )
                    st.markdown(
                        f'<div style="background:#e0e0e0;border-radius:4px;height:6px;">'
                        f'<div style="background:{bar_color};width:{min(plan.asset.readiness,100):.0f}%;'
                        f'height:6px;border-radius:4px;"></div></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(f"Operational hours: {plan.asset.hours:.0f} | "
                               f"Last maint: {plan.asset.last_maintenance}")

                with col2:
                    st.markdown("**Crew**")
                    st.markdown(f"**Name:** {plan.crew.name}")
                    st.markdown(f"**Rank:** {plan.crew.rank}")
                    st.markdown(f"**Qualified on:** {plan.crew.qualified_on}")
                    st.markdown(f"**Crew score:** {plan.crew.suitability_score:.0f}/100")

                with col3:
                    st.markdown(
                        f'<div style="background:{c_color}22;border:2px solid {c_color};'
                        f'border-radius:8px;padding:12px;text-align:center;margin-top:8px;">'
                        f'<div style="font-size:24px;">{c_icon}</div>'
                        f'<div style="color:{c_color};font-weight:700;font-size:13px;">'
                        f'{plan.confidence}</div>'
                        f'<div style="font-size:10px;color:#888;">CONFIDENCE</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # Rationale
                st.markdown("**✅ Rationale:**")
                for r in plan.rationale:
                    st.markdown(f"  - {r}")

                # Warnings
                if plan.warnings:
                    st.markdown("**⚠️ Warnings:**")
                    for w in plan.warnings:
                        st.markdown(f"  - {w}")

                # Quick log button (links to branch mission log tab)
                if st.button(
                    f"📝 Go to Mission Log →",
                    key=f"log_btn_{plan.rank}",
                    help="Switch to the branch mission log tab to submit this plan",
                ):
                    st.session_state.branch = branch
                    st.session_state.tab = 2
                    st.rerun()

        # ── Comparison table ──────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### Side-by-side comparison")
        import pandas as pd
        df = pd.DataFrame([{
            "Rank":        p.rank,
            "Asset":       p.asset.asset_id,
            "Type":        p.asset.asset_type,
            "Readiness %": round(p.asset.readiness, 1),
            "Asset Score": round(p.asset.suitability_score, 1),
            "Crew":        p.crew.name,
            "Crew Rank":   p.crew.rank,
            "Crew Score":  round(p.crew.suitability_score, 1),
            "Confidence":  p.confidence,
            "Warnings":    len(p.warnings),
        } for p in plans])
        st.dataframe(df, use_container_width=True, hide_index=True)

    else:
        # ── Mission type info card ─────────────────────────────────────────────
        spec = MISSION_QUALIFICATIONS.get(mission_type, {})
        if spec:
            st.info(
                f"**{mission_type}** requires min readiness **{spec.get('min_readiness', 50)}%**. "
                f"Preferred asset types: {', '.join(spec.get('preferred_types', ['Any'])) or 'Any'}."
            )
        st.caption("Configure the mission above and click **Generate Mission Plans**.")
