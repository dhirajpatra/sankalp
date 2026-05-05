"""
darshan_chat_patch.py
Drop-in replacement for the chat block inside render_ontology_engine() → active_tab == 0.

Key change: passes st.session_state.messages[-6:] as history to ask_llm_groq
so the engine can cap context without losing the API call signature.
"""

# Replace the chat block in render_ontology_engine / active_tab == 0 with this:

CHAT_BLOCK = '''
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Render existing messages
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
                    # Pass only last 6 messages as history (caps token usage)
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[-6:]
                        if m["role"] != "system"
                    ]
                    response = ask_llm_groq(prompt, history=history)
                placeholder.markdown(response)

            st.session_state.messages.append({"role": "assistant", "content": response})

            # Keep session history bounded to 20 messages to avoid memory bloat
            if len(st.session_state.messages) > 20:
                st.session_state.messages = st.session_state.messages[-20:]
'''
