"""
darshan_geo_map.py – SANKALP Geospatial Map View
Renders asset locations on an interactive map of India with readiness
heat-colouring. Plugs into Darshan as a new branch tab.

Dependencies: pip install folium streamlit-folium

Usage in darshan.py:
    from darshan_geo_map import render_geo_map
    elif branch == "map":
        render_geo_map()

Add to sidebar branches:
    ("map", "🗺️", "Geo Map", "MAP"),
"""

import streamlit as st
import sqlite3
import os
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger("darshan_geo_map")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
IAF_GOLD  = os.path.join(BASE, "../data/processed/sankalp_gold.db")
ARMY_GOLD = os.path.join(BASE, "../data/processed/sankalp_army_gold.db")
NAVY_GOLD = os.path.join(BASE, "../data/processed/sankalp_navy_gold.db")
RULES     = os.path.join(BASE, "../data/processed/ontology_rules.json")

# ── Squadron / Unit → GPS coordinates (India-centric) ────────────────────────
# Extend this dict when new units are added — nothing else needs changing.
LOCATION_COORDS: dict[str, tuple[float, float]] = {
    # IAF Squadrons
    "Tigers":           (31.63, 74.87),   # Halwara, Punjab
    "Tuskers":          (32.69, 74.84),   # Jammu
    "Winged Arrows":    (34.15, 77.58),   # Leh, Ladakh
    "Oorials":          (34.08, 74.79),   # Srinagar, Kashmir
    "Wolfpack":         (30.35, 76.78),   # Ambala, Punjab
    "Eight Pursoots":   (26.82, 75.80),   # Jaipur, Rajasthan
    "Flying Lancers":   (22.30, 70.78),   # Jamnagar, Gujarat
    "Black Cobras":     (27.02, 70.91),   # Uttarlai, Rajasthan
    "Bulls":            (23.07, 72.63),   # Ahmedabad, Gujarat
    "Flying Bullets":   (26.10, 91.58),   # Guwahati, Assam
    "Dragons":          (27.08, 93.61),   # Tezpur, Arunachal
    "Battle Axes":      (27.49, 95.01),   # Chabua, Assam
    "Eagle Squadron":   (28.97, 77.08),   # Hindon, Haryana
    "Phoenix Flight":   (31.63, 74.87),   # Halwara, Punjab
    "Night Hunters":    (26.82, 75.80),   # Jaipur, Rajasthan

    # Army Units
    "Armoured Corps":       (27.17, 78.00),  # Agra (Armour school)
    "Mechanised Infantry":  (28.61, 77.20),  # Delhi area
    "Artillery":            (17.38, 78.49),  # Hyderabad (Artillery centre)
    "Army Aviation":        (17.45, 78.39),  # Begumpet
    "Infantry":             (13.08, 80.27),  # Chennai (Infantry centre)
    "Para SF":              (13.08, 80.27),  # Chennai
    "Engineers":            (18.52, 73.85),  # Pune (Engineers corps)

    # Navy Flotillas
    "Western Fleet":            (18.93, 72.84),  # Mumbai
    "Eastern Fleet":            (17.68, 83.29),  # Visakhapatnam
    "Southern Naval Command":   (9.94,  76.27),  # Kochi
    "Submarine Command":        (15.85, 74.50),  # Karwar (INS Kadamba)
    "Naval Air Arm":            (15.85, 74.50),  # Karwar
    "Far Eastern Naval Command":(11.66, 92.73),  # Port Blair
    "Andaman & Nicobar":        (11.66, 92.73),  # Port Blair
}

# India bounding box centre
INDIA_CENTER = [22.5, 80.0]


# ── Data loader ───────────────────────────────────────────────────────────────

@dataclass
class MapAsset:
    asset_id: str
    asset_type: str
    unit: str
    branch: str
    readiness: float
    lat: float
    lon: float


def _load_threshold() -> int:
    try:
        with open(RULES) as f:
            return json.load(f).get("__global_settings__", {}).get("operational_threshold", 5)
    except Exception:
        return 5


def _sql(db_path: str, sql: str) -> list[dict]:
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"SQL error: {e}")
        return []


def _load_all_assets() -> list[MapAsset]:
    assets = []

    # IAF
    rows = _sql(IAF_GOLD, """
        SELECT r.aircraft_id AS id, g.aircraft_type AS type, g.squadron AS unit,
               r.final_readiness_score AS score
        FROM aircraft_readiness r
        JOIN aircraft_gold g ON r.aircraft_id = g.aircraft_id
    """)
    if not rows:
        rows = _sql(IAF_GOLD, """
            SELECT aircraft_id AS id, aircraft_type AS type, squadron AS unit,
                   readiness_base_score AS score FROM aircraft_gold
        """)
    for r in rows:
        unit = r["unit"] or ""
        lat, lon = LOCATION_COORDS.get(unit, (None, None))
        if lat:
            # Scatter assets slightly so markers don't pile on one point
            import random
            lat += random.uniform(-0.3, 0.3)
            lon += random.uniform(-0.3, 0.3)
            assets.append(MapAsset(r["id"], r["type"], unit, "IAF",
                                   float(r["score"] or 0), lat, lon))

    # Army
    rows = _sql(ARMY_GOLD, """
        SELECT r.asset_id AS id, g.asset_type AS type, g.unit AS unit,
               r.final_readiness_score AS score
        FROM asset_readiness r
        JOIN assets_gold g ON r.asset_id = g.asset_id
    """)
    if not rows:
        rows = _sql(ARMY_GOLD, """
            SELECT asset_id AS id, asset_type AS type, unit,
                   readiness_base_score AS score FROM assets_gold
        """)
    for r in rows:
        unit = r["unit"] or ""
        lat, lon = LOCATION_COORDS.get(unit, (None, None))
        if lat:
            import random
            lat += random.uniform(-0.3, 0.3)
            lon += random.uniform(-0.3, 0.3)
            assets.append(MapAsset(r["id"], r["type"], unit, "Army",
                                   float(r["score"] or 0), lat, lon))

    # Navy
    rows = _sql(NAVY_GOLD, """
        SELECT r.vessel_id AS id, g.vessel_type AS type, g.flotilla AS unit,
               r.final_readiness_score AS score
        FROM vessel_readiness r
        JOIN vessels_gold g ON r.vessel_id = g.vessel_id
    """)
    if not rows:
        rows = _sql(NAVY_GOLD, """
            SELECT vessel_id AS id, vessel_type AS type, flotilla AS unit,
                   readiness_base_score AS score FROM vessels_gold
        """)
    for r in rows:
        unit = r["unit"] or ""
        lat, lon = LOCATION_COORDS.get(unit, (None, None))
        if lat:
            import random
            lat += random.uniform(-0.3, 0.3)
            lon += random.uniform(-0.3, 0.3)
            assets.append(MapAsset(r["id"], r["type"], unit, "Navy",
                                   float(r["score"] or 0), lat, lon))

    return assets


# ── Colour helpers ────────────────────────────────────────────────────────────

def _readiness_color(score: float, threshold: int) -> str:
    if score >= threshold:
        return "#00e676"   # green  — Operational
    if score >= threshold - 20:
        return "#ff9800"   # amber  — Watch
    return "#ff4b4b"       # red    — Critical


def _branch_color(branch: str) -> str:
    return {"IAF": "#185FA5", "Army": "#3B6D11", "Navy": "#0F6E56"}.get(branch, "#888")


# ── Map builder ───────────────────────────────────────────────────────────────

def _build_folium_map(assets: list[MapAsset], threshold: int,
                      branch_filter: str, show_only: str):
    try:
        import folium
    except ImportError:
        return None

    m = folium.Map(
        location=INDIA_CENTER,
        zoom_start=5,
        tiles="CartoDB positron",
        prefer_canvas=True,
    )

    # ── Border threat zones (rough polygons) ──────────────────────────────────
    threat_zones = [
        {"name": "Northern Border (LAC)", "coords": [
            [35.5, 74.0], [35.5, 97.0], [32.0, 97.0], [32.0, 74.0]
        ], "color": "#ff4b4b"},
        {"name": "Western Border (LoC)", "coords": [
            [37.0, 73.5], [37.0, 75.0], [23.0, 68.0], [23.0, 73.5]
        ], "color": "#ff9800"},
        {"name": "Southern Sea Lanes", "coords": [
            [8.0, 72.0], [8.0, 80.0], [6.0, 80.0], [6.0, 72.0]
        ], "color": "#2196F3"},
    ]
    for zone in threat_zones:
        folium.Polygon(
            locations=zone["coords"],
            color=zone["color"],
            fill=True,
            fill_opacity=0.06,
            weight=1.5,
            tooltip=zone["name"],
        ).add_to(m)

    # ── Asset markers ─────────────────────────────────────────────────────────
    filtered = [
        a for a in assets
        if (branch_filter == "All" or a.branch == branch_filter)
        and (show_only == "All"
             or (show_only == "Operational" and a.readiness >= threshold)
             or (show_only == "Critical" and a.readiness < threshold - 20)
             or (show_only == "Watch" and threshold - 20 <= a.readiness < threshold))
    ]

    branch_groups = {}
    for a in filtered:
        if a.branch not in branch_groups:
            branch_groups[a.branch] = folium.FeatureGroup(name=a.branch)
        color = _readiness_color(a.readiness, threshold)
        status = ("Operational" if a.readiness >= threshold
                  else "Watch" if a.readiness >= threshold - 20
                  else "Critical")
        folium.CircleMarker(
            location=[a.lat, a.lon],
            radius=7,
            color=_branch_color(a.branch),
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            weight=1.5,
            tooltip=f"{a.asset_id} | {a.asset_type}",
            popup=folium.Popup(
                f"<b>{a.asset_id}</b><br>"
                f"Type: {a.asset_type}<br>"
                f"Branch: {a.branch}<br>"
                f"Unit: {a.unit}<br>"
                f"Readiness: <b style='color:{color}'>{a.readiness:.1f}%</b><br>"
                f"Status: <b>{status}</b>",
                max_width=220,
            ),
        ).add_to(branch_groups[a.branch])

    for grp in branch_groups.values():
        grp.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m, len(filtered)


# ── Streamlit renderer ────────────────────────────────────────────────────────

def render_geo_map():
    st.markdown("## 🗺️ Geospatial Asset Map — भारत रक्षा")
    st.caption("Live readiness heat-map across IAF, Army, and Navy deployment zones.")

    # ── Dependency check ──────────────────────────────────────────────────────
    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.error(
            "Missing dependencies. Install with:\n"
            "```\npip install folium streamlit-folium\n```"
        )
        return

    threshold = _load_threshold()
    assets    = _load_all_assets()

    if not assets:
        st.warning(
            "No geo-located assets found. Run the full pipeline first:\n"
            "```\npython sankalp_orchestrator.py\n```"
        )
        return

    # ── Controls ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        branch_filter = st.selectbox("Branch", ["All", "IAF", "Army", "Navy"])
    with c2:
        show_only = st.selectbox("Show", ["All", "Operational", "Watch", "Critical"])
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption(f"🎯 Operational threshold: **{threshold}%**")

    # ── Summary metrics ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Assets", len(assets))
    m2.metric("🟢 Operational", sum(1 for a in assets if a.readiness >= threshold))
    m3.metric("🟡 Watch",       sum(1 for a in assets if threshold - 20 <= a.readiness < threshold))
    m4.metric("🔴 Critical",    sum(1 for a in assets if a.readiness < threshold - 20))

    st.markdown("---")

    # ── Map ───────────────────────────────────────────────────────────────────
    result = _build_folium_map(assets, threshold, branch_filter, show_only)
    if result is None:
        st.error("Map build failed.")
        return

    fmap, count = result
    st.caption(f"Showing **{count}** asset markers. Click a marker for details.")

    st_folium(fmap, width=None, height=560, returned_objects=[])

    # ── Legend ────────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="display:flex;gap:24px;padding:8px 0;font-size:12px;">'
        '<span><span style="color:#00e676;">●</span> Operational</span>'
        '<span><span style="color:#ff9800;">●</span> Watch</span>'
        '<span><span style="color:#ff4b4b;">●</span> Critical</span>'
        '<span style="margin-left:16px;"><span style="color:#185FA5;">●</span> IAF &nbsp;'
        '<span style="color:#3B6D11;">●</span> Army &nbsp;'
        '<span style="color:#0F6E56;">●</span> Navy</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Data table ────────────────────────────────────────────────────────────
    with st.expander("📋 Asset data table"):
        import pandas as pd
        df = pd.DataFrame([
            {"ID": a.asset_id, "Type": a.asset_type, "Branch": a.branch,
             "Unit": a.unit, "Readiness %": round(a.readiness, 1),
             "Status": ("Operational" if a.readiness >= threshold
                        else "Watch" if a.readiness >= threshold - 20
                        else "Critical")}
            for a in assets
            if (branch_filter == "All" or a.branch == branch_filter)
        ])
        if not df.empty:
            st.dataframe(df.sort_values("Readiness %"), use_container_width=True, hide_index=True)
