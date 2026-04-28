def render_ontology_engine():
    st.title("🧠 Ontology Engine (Action & Logic)")
    st.markdown(
        "Define cross-branch action requirements and query the ontology to see "
        "if current fleet readiness supports operational execution."
    )

    tab1, tab2 = st.tabs(["⚡ Execute Action", "⚙️ Update Logic"])

    # ── Tab 1: Chat ──────────────────────────────────────────────────────────
    with tab1:
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
                    response = ask_llm_groq(prompt)
                placeholder.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

        # ── Quick-action buttons ─────────────────────────────────────────────
        st.markdown("---")
        st.caption("⚡ Quick Doctrine Checks")
        rules = load_rules()
        caps  = get_current_capabilities()

        for action_name, rule in rules.items():
            result = evaluate_action(action_name)
            # evaluate_action returns (can_execute, reasons[, tier])
            can_execute = result[0]
            reasons     = result[1]
            tier        = result[2] if len(result) > 2 else ("ADEQUATE" if can_execute else "INSUFFICIENT")

            if tier == "SUPERIOR":
                badge = "🏆 SUPERIOR"
                color = "#00c853"
            elif tier == "ADEQUATE":
                badge = "🟡 ADEQUATE"
                color = "#ff9800"
            else:
                badge = "🔴 INSUFFICIENT"
                color = "#f44336"

            with st.expander(f"{badge} — {action_name.title()}", expanded=False):
                st.markdown(
                    f'<div style="background:#0d1f30;border-left:4px solid {color};'
                    f'padding:10px 14px;border-radius:4px;margin-bottom:10px;">'
                    f'<span style="color:{color};font-weight:700;font-size:15px;">'
                    f'{badge}</span></div>',
                    unsafe_allow_html=True,
                )
                st.caption(rule.get("description", ""))
                for r in reasons:
                    st.markdown(r)

                # Live capability mini-summary
                mode = rule.get("logic_mode", "standard")
                if mode == "iaf_primary_army_superior":
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✈️ IAF Op.", caps["iaf_op"],
                              delta=f"min {rule['iaf_min_operational']}")
                    c2.metric("🪖 Army Op.", caps["army_op"],
                              delta=f"enh {rule.get('army_enhancement_threshold', 0)}")
                    c3.metric("⚓ Navy Op.", caps["navy_op"], delta="not required")

    # ── Tab 2: Update Logic ──────────────────────────────────────────────────
    with tab2:
        st.subheader("Update Ontology Logic")
        st.markdown("Modify baseline requirements for joint operations.")

        rules      = load_rules()
        edit_action = st.selectbox("Select Logic to Edit:", list(rules.keys()))
        rule        = rules[edit_action]
        mode        = rule.get("logic_mode", "standard")

        with st.form("edit_logic_form"):
            desc     = st.text_area("Description", value=rule.get("description", ""))
            iaf_min  = st.number_input("Min Operational IAF Aircraft",
                                       min_value=0, value=rule["iaf_min_operational"])
            army_min = st.number_input("Min Operational Army Assets",
                                       min_value=0, value=rule["army_min_operational"])
            navy_min = st.number_input("Min Operational Navy Vessels",
                                       min_value=0, value=rule["navy_min_operational"])

            st.markdown("---")
            st.caption("Advanced logic settings")
            iaf_alone = st.checkbox(
                "IAF can execute alone (without Army/Navy meeting minimums)",
                value=rule.get("iaf_sufficient_alone", False),
            )
            army_enh  = st.checkbox(
                "Army presence upgrades response to SUPERIOR tier",
                value=rule.get("army_enhances", False),
            )
            army_thr  = st.number_input(
                "Army assets needed for SUPERIOR tier",
                min_value=0,
                value=rule.get("army_enhancement_threshold", 0),
                disabled=not army_enh,
            )

            if st.form_submit_button("💾 Save Logic to Engine"):
                rules[edit_action] = {
                    "description":               desc,
                    "iaf_min_operational":        iaf_min,
                    "army_min_operational":       army_min,
                    "navy_min_operational":       navy_min,
                    "iaf_sufficient_alone":       iaf_alone,
                    "army_enhances":              army_enh,
                    "army_enhancement_threshold": int(army_thr),
                    "logic_mode": (
                        "iaf_primary_army_superior"
                        if (iaf_alone and army_enh)
                        else "standard"
                    ),
                }
                save_rules(rules)
                st.success("✅ Ontology logic updated successfully!")
                st.rerun()
