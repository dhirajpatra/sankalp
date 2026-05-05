"""
darshan_threat_tab.py – SANKALP Threat Intelligence UI
Renders the Threat Engine results inside Darshan.

Usage in darshan.py:
    from darshan_threat_tab import render_threat_panel
    elif branch == "threat":
        render_threat_panel()

Add to sidebar branches:
    ("threat", "🎯", "Threat Intel", "THREAT"),
"""

import streamlit as st

try:
    from agents.threat_engine import ThreatEngine, THREAT_SCENARIOS
except ImportError:
    from threat_engine import ThreatEngine, THREAT_SCENARIOS


# ── Colour maps ───────────────────────────────────────────────────────────────
VERDICT_COLOR  = {"CAPABLE": "#00e676", "MARGINAL": "#ff9800", "INSUFFICIENT": "#ff4b4b"}
VERDICT_ICON   = {"CAPABLE": "✅", "MARGINAL": "🟡", "INSUFFICIENT": "🔴"}
THREAT_COLOR   = {"CRITICAL": "#ff4b4b", "HIGH": "#ff9800", "MEDIUM": "#2196F3", "LOW": "#00e676"}


def render_threat_panel():
    st.markdown("## 🎯 Threat Intelligence Overlay")
    st.caption(
        "Maps current fleet readiness against simulated adversary threat scenarios. "
        "Verdicts are computed live from gold-store readiness data."
    )

    engine = ThreatEngine()

    # ── Sub-tabs ──────────────────────────────────────────────────────────────
    sub_tabs = ["📊 All Scenarios", "🔍 Scenario Detail", "➕ Custom Scenario"]
    if "threat_tab" not in st.session_state:
        st.session_state.threat_tab = 0

    cols = st.columns(len(sub_tabs))
    for i, (col, label) in enumerate(zip(cols, sub_tabs)):
        with col:
            active = st.session_state.threat_tab == i
            if st.button(label, key=f"threat_subtab_{i}",
                         use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.threat_tab = i
                st.rerun()

    st.markdown("---")

    if st.session_state.threat_tab == 0:
        _render_all_scenarios(engine)
    elif st.session_state.threat_tab == 1:
        _render_scenario_detail(engine)
    elif st.session_state.threat_tab == 2:
        _render_custom_scenario(engine)


# ── Tab 0: All scenarios overview ─────────────────────────────────────────────

def _render_all_scenarios(engine: ThreatEngine):
    with st.spinner("Assessing all threat scenarios..."):
        assessments = engine.assess_all()

    if not assessments:
        st.warning("No readiness data found. Run the pipeline first.")
        return

    # Summary bar
    capable      = sum(1 for a in assessments if a.verdict == "CAPABLE")
    marginal     = sum(1 for a in assessments if a.verdict == "MARGINAL")
    insufficient = sum(1 for a in assessments if a.verdict == "INSUFFICIENT")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scenarios",    len(assessments))
    c2.metric("✅ Capable",   capable)
    c3.metric("🟡 Marginal",  marginal)
    c4.metric("🔴 Insufficient", insufficient)

    st.markdown("---")

    # Scenario cards
    for a in assessments:
        v_color = VERDICT_COLOR[a.verdict]
        v_icon  = VERDICT_ICON[a.verdict]
        t_color = THREAT_COLOR.get(a.threat_level, "#888")

        with st.expander(
            f"{v_icon} **{a.scenario_label}** — {a.verdict} ({a.coverage_pct:.0f}% coverage)",
            expanded=(a.verdict == "INSUFFICIENT"),
        ):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"*{a.description}*")
                st.markdown(
                    f'<span style="background:{t_color}22;color:{t_color};'
                    f'border:1px solid {t_color}55;border-radius:3px;'
                    f'padding:2px 8px;font-size:11px;font-weight:600;">'
                    f'{a.threat_level} THREAT</span> &nbsp; '
                    f'<span style="font-size:12px;color:#666;">Adversary: {a.adversary}</span>',
                    unsafe_allow_html=True,
                )

                # Coverage bar
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(f"**Coverage: {a.coverage_pct:.0f}%**")
                st.markdown(
                    f'<div style="background:#e0e0e0;border-radius:4px;height:8px;">'
                    f'<div style="background:{v_color};width:{min(a.coverage_pct,100):.0f}%;'
                    f'height:8px;border-radius:4px;"></div></div>',
                    unsafe_allow_html=True,
                )

                # Branch breakdown
                st.markdown("<br>**Branch capability vs requirement:**", unsafe_allow_html=True)
                for branch in ("iaf", "army", "navy"):
                    req = a.required[branch]
                    if req == 0:
                        continue
                    cap = a.capability[branch]
                    gap = a.gap[branch]
                    gap_str = f"+{gap}" if gap >= 0 else str(gap)
                    gap_color = "#00e676" if gap >= 0 else "#ff4b4b"
                    icon = {"iaf": "✈️", "army": "🪖", "navy": "⚓"}[branch]
                    st.markdown(
                        f'{icon} **{branch.upper()}**: {cap.operational} operational '
                        f'(need {req}) &nbsp; '
                        f'<span style="color:{gap_color};font-weight:600;">[{gap_str}]</span>',
                        unsafe_allow_html=True,
                    )

            with col2:
                # Verdict badge
                st.markdown(
                    f'<div style="background:{v_color}22;border:2px solid {v_color};'
                    f'border-radius:8px;padding:16px;text-align:center;margin-top:8px;">'
                    f'<div style="font-size:28px;">{v_icon}</div>'
                    f'<div style="color:{v_color};font-weight:700;font-size:14px;">'
                    f'{a.verdict}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # Risks & recommendations
            if a.risk_factors and a.risk_factors[0] != "✅ No significant risk factors identified":
                st.markdown("**⚠️ Risk factors:**")
                for r in a.risk_factors:
                    st.markdown(f"- {r}")

            if a.recommendations:
                st.markdown("**💡 Recommendations:**")
                for r in a.recommendations:
                    st.markdown(f"- {r}")

    # Radar chart summary
    _render_coverage_chart(assessments)


def _render_coverage_chart(assessments):
    """Simple horizontal bar chart of scenario coverage."""
    try:
        import altair as alt
        import pandas as pd

        df = pd.DataFrame([{
            "Scenario": a.scenario_label[:30],
            "Coverage": a.coverage_pct,
            "Verdict":  a.verdict,
        } for a in assessments])

        color_scale = alt.Scale(
            domain=["CAPABLE", "MARGINAL", "INSUFFICIENT"],
            range=["#00e676", "#ff9800", "#ff4b4b"],
        )

        chart = alt.Chart(df).mark_bar().encode(
            x=alt.X("Coverage:Q", scale=alt.Scale(domain=[0, 120]), title="Coverage %"),
            y=alt.Y("Scenario:N", sort="-x"),
            color=alt.Color("Verdict:N", scale=color_scale),
            tooltip=["Scenario", "Coverage", "Verdict"],
        ).properties(height=max(180, len(assessments) * 40), title="Threat Scenario Coverage")

        st.markdown("---")
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        pass


# ── Tab 1: Single scenario deep-dive ──────────────────────────────────────────

def _render_scenario_detail(engine: ThreatEngine):
    scenario_options = {v["label"]: k for k, v in THREAT_SCENARIOS.items()}
    selected_label = st.selectbox("Select Scenario", list(scenario_options.keys()))
    selected_id    = scenario_options[selected_label]

    if st.button("🔍 Assess Now", type="primary"):
        with st.spinner("Running assessment..."):
            a = engine.assess(selected_id)

        v_color = VERDICT_COLOR[a.verdict]
        t_color = THREAT_COLOR.get(a.threat_level, "#888")

        st.markdown(
            f'<div style="background:{v_color}11;border-left:4px solid {v_color};'
            f'padding:12px 16px;border-radius:4px;margin:12px 0;">'
            f'<span style="font-size:20px;">{VERDICT_ICON[a.verdict]}</span> '
            f'<span style="color:{v_color};font-weight:700;font-size:18px;">{a.verdict}</span>'
            f' &nbsp;·&nbsp; {a.coverage_pct:.1f}% coverage'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(f"**Adversary:** {a.adversary}")
        st.markdown(
            f'<span style="background:{t_color}22;color:{t_color};'
            f'border:1px solid {t_color}55;border-radius:3px;padding:2px 8px;'
            f'font-size:11px;font-weight:600;">{a.threat_level} THREAT</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f"\n*{a.description}*")

        st.markdown("---")
        st.markdown("### Branch Requirements vs Capability")
        cols = st.columns(3)
        for col, branch in zip(cols, ("iaf", "army", "navy")):
            cap = a.capability[branch]
            req = a.required[branch]
            gap = a.gap[branch]
            icon = {"iaf": "✈️", "army": "🪖", "navy": "⚓"}[branch]
            delta_color = "normal" if gap >= 0 else "inverse"
            with col:
                st.metric(
                    f"{icon} {branch.upper()} Operational",
                    cap.operational,
                    delta=f"{gap:+d} vs requirement ({req})",
                    delta_color=delta_color,
                )
                st.caption(f"Avg readiness: {cap.avg_readiness}%")

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**⚠️ Risk Factors**")
            for r in a.risk_factors:
                st.markdown(f"- {r}")
        with c2:
            st.markdown("**💡 Recommendations**")
            for r in a.recommendations:
                st.markdown(f"- {r}")

        st.caption(f"Assessed at: {a.assessed_at}")


# ── Tab 2: Add custom scenario ────────────────────────────────────────────────

def _render_custom_scenario(engine: ThreatEngine):
    st.markdown("### Add Custom Threat Scenario")
    st.caption("Define a new scenario and assess it immediately. Persists for this session only.")

    with st.form("custom_scenario_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            sid   = st.text_input("Scenario ID (slug)",  placeholder="eastern_air_incursion")
            label = st.text_input("Display Label",        placeholder="Eastern Air Incursion")
            adversary = st.text_input("Adversary",        placeholder="Eastern Actor")
        with c2:
            threat_level = st.selectbox("Threat Level", ["CRITICAL", "HIGH", "MEDIUM", "LOW"])
            primary      = st.selectbox("Primary Branch", ["iaf", "army", "navy", "all"])
            description  = st.text_area("Description", height=80)

        st.markdown("**Minimum operational assets required:**")
        r1, r2, r3 = st.columns(3)
        with r1: iaf_min  = st.number_input("IAF aircraft", min_value=0, value=0)
        with r2: army_min = st.number_input("Army assets",  min_value=0, value=0)
        with r3: navy_min = st.number_input("Navy vessels", min_value=0, value=0)

        submitted = st.form_submit_button("➕ Add & Assess", type="primary")

    if submitted:
        if not sid or not label:
            st.error("Scenario ID and Label are required.")
            return
        try:
            engine.add_scenario(sid, {
                "label": label, "description": description,
                "required": {"iaf": iaf_min, "army": army_min, "navy": navy_min},
                "threat_level": threat_level, "adversary": adversary,
                "primary_branch": primary,
            })
            a = engine.assess(sid)
            v_color = VERDICT_COLOR[a.verdict]
            st.success(f"Scenario added. Verdict: **{VERDICT_ICON[a.verdict]} {a.verdict}** "
                       f"({a.coverage_pct:.1f}% coverage)")
            for r in a.risk_factors:
                st.markdown(f"- {r}")
        except Exception as e:
            st.error(f"Error: {e}")
