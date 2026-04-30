"""
Darshan (दर्शन) v2.1 – Sankalp Defence Digital Twin Ontology Platform
Multi-branch: IAF · Army · Navy · Ontology · Live Alerts · Admin
"""

import streamlit as st
import pandas as pd
import os
import random
import string
from datetime import date
from dotenv import load_dotenv
from config_loader import cfg

from darshan_navy_branch import render_navy
from darshan_iaf_branch import render_iaf
from darshan_army_branch import render_army

try:
    from admin_import import render_admin_dashboard
    from ontology_engine import (
        evaluate_action, load_rules, save_rules, ask_llm_groq,
        add_rule, delete_rule, get_operational_threshold, set_operational_threshold,
    )
    from darshan_left_sidebar import render_left_sidebar
    from darshan_alerts_panel import render_alerts_panel, ensure_monitor
except ImportError:
    from agents.admin_import import render_admin_dashboard
    from agents.ontology_engine import (
        evaluate_action, load_rules, save_rules, ask_llm_groq,
        add_rule, delete_rule, get_operational_threshold, set_operational_threshold,
    )
    from agents.darshan_left_sidebar import render_left_sidebar
    from agents.darshan_alerts_panel import render_alerts_panel, ensure_monitor

load_dotenv(override=True)
NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USER     = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

STYLES = cfg("paths.css_file")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sankalp – Defence Digital Twin",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Start background monitor (idempotent – safe to call every rerun) ──────────
ensure_monitor()

# ── CSS ───────────────────────────────────────────────────────────────────────
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), STYLES)
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# ── Session defaults ──────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "branch":       "iaf",
        "tab":          0,
        "sel_asset":    None,
        "metric_panel": None,
        "ontology_tab": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()
render_left_sidebar()

# ── Auto-refresh every 15 s so alert badge stays current ─────────────────────
# Only refresh when on the alerts branch to avoid disrupting other views
if st.session_state.branch == "alerts":
    st_autorefresh = None
    try:
        from streamlit_autorefresh import st_autorefresh  # optional dep
        st_autorefresh(interval=15_000, key="alerts_refresh")
    except ImportError:
        pass  # graceful degradation — user can manually refresh


# ── Ontology Engine (unchanged from v2.0) ────────────────────────────────────
def render_ontology_engine():
    st.title("🧠 Ontology Engine (Action & Logic)")
    st.markdown(
        "Define cross-branch action requirements and query the ontology to see "
        "if current fleet readiness supports operational execution."
    )

    tab_labels = ["⚡ Execute Action", "✏️ Edit Logic", "➕ Add New Logic", "🗑️ Delete Logic"]
    tab_cols = st.columns(len(tab_labels))
    for i, (col, lbl) in enumerate(zip(tab_cols, tab_labels)):
        with col:
            active = st.session_state.ontology_tab == i
            if st.button(lbl, key=f"ontology_subtab_{i}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.ontology_tab = i
                st.rerun()

    st.markdown("---")
    active_tab = st.session_state.ontology_tab

    if active_tab == 0:
        st.subheader("Query Ontology")
        if "messages" not in st.session_state:
            st.session_state.messages = []
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        if prompt := st.chat_input("Ask Sankalp-AI an operational question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                placeholder = st.empty()
                with st.spinner("Sankalp-AI is analyzing ontology..."):
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[-6:]
                        if m["role"] != "system"
                    ]
                    response = ask_llm_groq(prompt, history=history)
                placeholder.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            if len(st.session_state.messages) > 20:
                st.session_state.messages = st.session_state.messages[-20:]

        st.markdown("---")
        st.caption("⚡ Quick Doctrine Checks")
        rules = load_rules()
        action_keys = [k for k in rules if k != "__global_settings__"]
        for action_name in action_keys:
            rule = rules[action_name]
            result = evaluate_action(action_name)
            can_execute, reasons, tier = result
            if tier == "SUPERIOR":
                badge, color = "🏆 SUPERIOR", "#00c853"
            elif tier == "ADEQUATE":
                badge, color = "🟡 ADEQUATE", "#ff9800"
            else:
                badge, color = "🔴 INSUFFICIENT", "#f44336"
            with st.expander(f"{badge} — {action_name.title()}", expanded=False):
                st.markdown(
                    f'<div style="background:#f8f9fa;border-left:4px solid {color};'
                    f'padding:10px 14px;border-radius:4px;margin-bottom:10px;">'
                    f'<span style="color:{color};font-weight:700;font-size:15px;">'
                    f'{badge}</span></div>',
                    unsafe_allow_html=True,
                )
                st.caption(rule.get("description", ""))
                for r in reasons:
                    st.markdown(r)

    elif active_tab == 1:
        st.subheader("✏️ Edit Existing Doctrine Rule")
        rules = load_rules()
        action_keys = [k for k in rules if k != "__global_settings__"]
        if not action_keys:
            st.info("No rules defined yet.")
            return
        st.markdown("#### 🌐 Global Operational Threshold")
        current_threshold = rules.get("__global_settings__", {}).get("operational_threshold", 5)
        new_threshold = st.number_input("Base Score Threshold", min_value=0, max_value=100,
                                        value=int(current_threshold), key="edit_global_thresh")
        if st.button("💾 Update Global Threshold", key="save_global_thresh"):
            set_operational_threshold(new_threshold)
            st.success(f"✅ Global threshold updated to {new_threshold}.")
        st.markdown("---")
        edit_action = st.selectbox("Select Rule to Edit:", action_keys, key="edit_rule_select")
        rule = rules[edit_action]
        with st.form("edit_logic_form"):
            desc = st.text_area("Description", value=rule.get("description", ""), height=100)
            c1, c2, c3 = st.columns(3)
            with c1:
                iaf_min = st.number_input("Min IAF Aircraft", min_value=0,
                                          value=int(rule.get("iaf_min_operational", 0)))
            with c2:
                army_min = st.number_input("Min Army Assets", min_value=0,
                                           value=int(rule.get("army_min_operational", 0)))
            with c3:
                navy_min = st.number_input("Min Navy Vessels", min_value=0,
                                           value=int(rule.get("navy_min_operational", 0)))
            c4, c5 = st.columns(2)
            with c4:
                iaf_alone = st.checkbox("IAF can execute alone",
                                        value=rule.get("iaf_sufficient_alone", False))
            with c5:
                army_enh = st.checkbox("Army upgrades to SUPERIOR",
                                       value=rule.get("army_enhances", False))
            army_thr = st.number_input("Army threshold for SUPERIOR", min_value=0,
                                       value=int(rule.get("army_enhancement_threshold", 0)),
                                       disabled=not army_enh)
            if st.form_submit_button("💾 Save Changes"):
                rules[edit_action] = {
                    "description": desc,
                    "iaf_min_operational": iaf_min,
                    "army_min_operational": army_min,
                    "navy_min_operational": navy_min,
                    "iaf_sufficient_alone": iaf_alone,
                    "army_enhances": army_enh,
                    "army_enhancement_threshold": int(army_thr),
                    "logic_mode": "iaf_primary_army_superior" if (iaf_alone and army_enh) else "standard",
                }
                save_rules(rules)
                st.success(f"✅ Rule '{edit_action}' updated!")
                st.rerun()

    elif active_tab == 2:
        st.subheader("➕ Add New Doctrine Rule")
        with st.form("add_logic_form", clear_on_submit=True):
            action_name = st.text_input("Action Name",
                                        placeholder="e.g. secure eastern air corridor")
            description = st.text_area("Description", height=110)
            c1, c2, c3 = st.columns(3)
            with c1:
                iaf_min = st.number_input("IAF Aircraft", min_value=0, value=0, key="add_iaf")
            with c2:
                army_min = st.number_input("Army Assets", min_value=0, value=0, key="add_army")
            with c3:
                navy_min = st.number_input("Navy Vessels", min_value=0, value=0, key="add_navy")
            c4, c5 = st.columns(2)
            with c4:
                iaf_alone = st.checkbox("IAF can execute alone", key="add_iaf_alone")
            with c5:
                army_enh = st.checkbox("Army upgrades to SUPERIOR", key="add_army_enh")
            army_thr = st.number_input("Army threshold for SUPERIOR", min_value=0,
                                       value=0, key="add_army_thr",
                                       disabled=not st.session_state.get("add_army_enh", False))
            submitted = st.form_submit_button("✅ Add Rule", type="primary")
        if submitted:
            if not action_name.strip():
                st.error("Action name is required.")
            else:
                ok, msg = add_rule(action_name, description, iaf_min, army_min, navy_min,
                                   iaf_alone, army_enh, int(army_thr))
                if ok:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")

        st.markdown("---")
        st.caption("📋 All currently defined rules")
        rules = load_rules()
        action_keys = [k for k in rules if k != "__global_settings__"]
        if action_keys:
            preview_df = [{"Rule": k, "IAF Min": rules[k].get("iaf_min_operational", 0),
                           "Army Min": rules[k].get("army_min_operational", 0),
                           "Navy Min": rules[k].get("navy_min_operational", 0),
                           "Logic": rules[k].get("logic_mode", "standard")} for k in action_keys]
            st.dataframe(pd.DataFrame(preview_df), use_container_width=True, hide_index=True)

    elif active_tab == 3:
        st.subheader("🗑️ Delete Doctrine Rule")
        rules = load_rules()
        action_keys = [k for k in rules if k != "__global_settings__"]
        if not action_keys:
            st.info("No rules to delete.")
        else:
            del_action = st.selectbox("Select Rule to Delete:", action_keys)
            rule = rules[del_action]
            st.markdown(
                f'<div style="background:#fff3f3;border:1px solid #ffcccc;border-radius:6px;'
                f'padding:12px 16px;margin:8px 0;font-size:13px;">'
                f'<b>{del_action}</b><br>{rule.get("description","")}'
                f'</div>', unsafe_allow_html=True,
            )
            confirm = st.checkbox(f'Confirm deletion of "{del_action}"')
            if st.button("🗑️ Delete Rule", type="primary", disabled=not confirm):
                ok, msg = delete_rule(del_action)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")


# ── Route to branch ───────────────────────────────────────────────────────────
branch = st.session_state.branch
if branch == "iaf":
    render_iaf()
elif branch == "army":
    render_army()
elif branch == "navy":
    render_navy()
elif branch == "ontology":
    render_ontology_engine()
elif branch == "alerts":
    render_alerts_panel()          # ← new
elif branch == "admin":
    render_admin_dashboard(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)