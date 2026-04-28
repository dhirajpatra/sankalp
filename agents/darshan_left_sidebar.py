import streamlit as st
from darshan_db_helper import load_iaf, load_army, load_navy

def render_left_sidebar():
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
            ("ontology", "🧠", "Ontology Engine", "LOGIC"),
            ("admin", "⚙️", "Admin / Data Import", "ADMIN"),
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