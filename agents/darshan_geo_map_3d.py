"""
darshan_geo_map_3d.py – SANKALP Three.js Globe Map (browser-cached)
====================================================================
A drop-in companion to darshan_geo_map.py that renders asset locations on an
interactive 3-D globe using Three.js, with IndexedDB caching so the dataset
survives page refreshes without re-fetching from Python.

Usage in darshan.py (add alongside existing map tab):
    from darshan_geo_map_3d import render_geo_map_3d
    elif branch == "map3d":
        render_geo_map_3d()

Add to sidebar:
    ("map3d", "🌐", "3-D Globe", "MAP3D"),

IMPORTANT: This module imports data helpers from darshan_geo_map.py but never
           modifies that file or any other core module.
"""

import json
import os
import streamlit as st


# ── Re-use data loading from the existing geo-map module (no changes there) ────
from darshan_geo_map import _load_all_assets, _load_threshold, LOCATION_COORDS

# ── Load HTML template ─────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_HTML_PATH = os.path.join(_HERE, "assets", "geo_map_3d.html")


def _read_html_template() -> str:
    with open(_HTML_PATH, encoding="utf-8") as f:
        return f.read()


def _assets_to_json(threshold: int) -> str:
    """Convert MapAsset list → JSON string suitable for injection into the HTML."""
    assets = _load_all_assets()
    payload = []
    for a in assets:
        status = (
            "operational" if a.readiness >= threshold
            else "watch" if a.readiness >= threshold - 20
            else "critical"
        )
        payload.append({
            "id":       a.asset_id,
            "type":     a.asset_type,
            "unit":     a.unit,
            "branch":   a.branch,
            "readiness": round(a.readiness, 1),
            "status":   status,
            "lat":      a.lat,
            "lon":      a.lon,
        })
    return json.dumps(payload)


def render_geo_map_3d():
    st.markdown("## 🌐 3-D Globe — भारत रक्षा Asset Map")
    st.caption(
        "Three.js WebGL globe with IndexedDB caching. "
        "Asset positions persist in your browser until data is refreshed."
    )

    threshold = _load_threshold()

    # ── Summary metrics (re-uses same data loader) ────────────────────────────
    assets = _load_all_assets()
    if not assets:
        st.warning(
            "No geo-located assets found. Run the full pipeline first:\n"
            "```\npython sankalp_orchestrator.py\n```"
        )
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Assets", len(assets))
    m2.metric("🟢 Operational", sum(1 for a in assets if a.readiness >= threshold))
    m3.metric("🟡 Watch",       sum(1 for a in assets if threshold - 20 <= a.readiness < threshold))
    m4.metric("🔴 Critical",    sum(1 for a in assets if a.readiness < threshold - 20))

    # ── Force-refresh button ──────────────────────────────────────────────────
    col_btn, col_hint = st.columns([1, 5])
    with col_btn:
        force_refresh = st.button("🔄 Refresh Globe Data", key="geo3d_refresh")
    with col_hint:
        st.caption("Data is cached in IndexedDB. Click Refresh to push updated readiness scores to the globe.")

    st.markdown("---")

    # ── Build HTML payload ────────────────────────────────────────────────────
    try:
        html_template = _read_html_template()
    except FileNotFoundError:
        st.error(
            f"Globe HTML template not found at `{_HTML_PATH}`. "
            "Ensure `agents/assets/geo_map_3d.html` is present."
        )
        return

    assets_json  = _assets_to_json(threshold)
    force_flag   = "true" if force_refresh else "false"

    # Inject Python-side data into the HTML template
    html = (
        html_template
        .replace("__ASSETS_JSON__", assets_json)
        .replace("__THRESHOLD__",   str(threshold))
        .replace("__FORCE_REFRESH__", force_flag)
    )

    st.iframe(srcdoc=html, height=680, scrolling=False)

    # ── Legend ────────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="display:flex;gap:24px;padding:6px 0;font-size:12px;">'
        '<span><span style="color:#00e676;">●</span> Operational</span>'
        '<span><span style="color:#ff9800;">●</span> Watch</span>'
        '<span><span style="color:#ff4b4b;">●</span> Critical</span>'
        '<span style="margin-left:16px;"><span style="color:#4FC3F7;">●</span> IAF &nbsp;'
        '<span style="color:#81C784;">●</span> Army &nbsp;'
        '<span style="color:#4DB6AC;">●</span> Navy</span>'
        '<span style="margin-left:auto;font-style:italic;color:#666;">Scroll to zoom · Drag to rotate · Click marker for details</span>'
        '</div>',
        unsafe_allow_html=True,
    )
