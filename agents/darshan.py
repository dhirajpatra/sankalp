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
from darshan_navy_branch import render_navy
from darshan_iaf_branch import render_iaf
from darshan_army_branch import render_army

try:
    from admin_import import render_admin_dashboard
    from ontology_engine import evaluate_action, load_rules, save_rules, ask_llm_groq
    from darshan_left_sidebar import render_left_sidebar
except ImportError:
    from agents.admin_import import render_admin_dashboard
    from agents.ontology_engine import evaluate_action, load_rules, save_rules, ask_llm_groq
    from agents.darshan_left_sidebar import render_left_sidebar

load_dotenv(override=True)
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

STYLES = "assets/styles/style.css"

# ── DB paths ────────────────────────────────────────────────────────────────
IAF_DB   = "data/processed/sankalp_gold.db"
ARMY_DB  = "data/processed/sankalp_army_gold.db"
NAVY_DB  = "data/processed/sankalp_navy_gold.db"

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
render_left_sidebar()



# ── Ontology Engine Route ────────────────────────────────────────────────────
def render_ontology_engine():
    st.title("🧠 Ontology Engine (Action & Logic)")
    st.markdown("Define complex cross-branch action requirements and query the ontology to see if current fleet readiness supports operational execution.")
    
    tab1, tab2 = st.tabs(["⚡ Execute Action", "⚙️ Update Logic"])
    
    with tab1:
        st.subheader("Query Ontology")
        
        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Display chat messages from history on app rerun
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Accept user input
        if prompt := st.chat_input("Ask Sankalp-AI an operational question..."):
            # Display user message in chat message container
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Display assistant response in chat message container
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                with st.spinner("Sankalp-AI is analyzing ontology..."):
                    response = ask_llm_groq(prompt)
                message_placeholder.markdown(response)
            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": response})
                        
    with tab2:
        st.subheader("Update Ontology Logic")
        st.markdown("Modify the baseline requirements for joint operations.")
        
        rules = load_rules()
        
        st.markdown("#### Global Thresholds")
        current_threshold = rules.get("__global_settings__", {}).get("operational_threshold", 5)
        new_threshold = st.number_input("Global Operational Base Score Threshold", min_value=0, max_value=100, value=current_threshold)
        
        if st.button("Update Global Threshold"):
            from agents.ontology_engine import set_operational_threshold
            set_operational_threshold(new_threshold)
            st.success(f"Global threshold updated to {new_threshold}. Neo4j database nodes have been re-evaluated.")
            
        st.markdown("---")
        st.markdown("#### Specific Action Rules")
        
        # Filter out __global_settings__ from the selectbox
        action_keys = [k for k in rules.keys() if k != "__global_settings__"]
        edit_action = st.selectbox("Select Logic to Edit:", action_keys)
        
        rule = rules[edit_action]
        with st.form("edit_logic_form"):
            desc = st.text_area("Description", value=rule["description"])
            iaf_min = st.number_input("Min Operational IAF Aircraft", min_value=0, value=rule["iaf_min_operational"])
            army_min = st.number_input("Min Operational Army Assets", min_value=0, value=rule["army_min_operational"])
            navy_min = st.number_input("Min Operational Navy Vessels", min_value=0, value=rule["navy_min_operational"])
            
            if st.form_submit_button("Save Logic to Engine"):
                rules[edit_action] = {
                    "description": desc,
                    "iaf_min_operational": iaf_min,
                    "army_min_operational": army_min,
                    "navy_min_operational": navy_min,
                    "logic_mode": rule.get("logic_mode", "standard"),
                    "iaf_sufficient_alone": rule.get("iaf_sufficient_alone", False),
                    "army_enhances": rule.get("army_enhances", False),
                    "army_enhancement_threshold": rule.get("army_enhancement_threshold", 0)
                }
                save_rules(rules)
                st.success("Ontology logic updated successfully!")

# ── Route to branch ──────────────────────────────────────────────────────────
branch = st.session_state.branch
if branch == "iaf":
    render_iaf()
elif branch == "army":
    render_army()
elif branch == "navy":
    render_navy()
elif branch == "ontology":
    render_ontology_engine()
elif branch == "admin":
    render_admin_dashboard(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
