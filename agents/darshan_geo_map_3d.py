"""
darshan_geo_map_3d.py – SANKALP Tactical Globe (upgraded)
Replaces the original geo_map_3d.html with the full Anduril-style
tactical COP: classification colours, trail histories, threat rings,
heading arrows, track thumbnail panels, sidebar track list.
"""

import json
import os
import random
import sqlite3
import streamlit as st

try:
    from config_loader import cfg
except ImportError:
    cfg = lambda k, d=None: d

_HERE     = os.path.dirname(os.path.abspath(__file__))
_HTML     = os.path.join(_HERE, "assets", "geo_map_3d.html")
IAF_GOLD  = os.path.join(_HERE, "../data/processed/sankalp_gold.db")
ARMY_GOLD = os.path.join(_HERE, "../data/processed/sankalp_army_gold.db")
NAVY_GOLD = os.path.join(_HERE, "../data/processed/sankalp_navy_gold.db")
RULES     = os.path.join(_HERE, "../data/processed/ontology_rules.json")

# ── GPS lookup (squadron / unit / flotilla → lat, lon) ──────────────────────
LOCATION_COORDS = {
    # IAF
    "Tigers":           (31.63, 74.87),
    "Tuskers":          (32.69, 74.84),
    "Winged Arrows":    (34.15, 77.58),
    "Oorials":          (34.08, 74.79),
    "Wolfpack":         (30.35, 76.78),
    "Eight Pursoots":   (26.82, 75.80),
    "Flying Lancers":   (22.30, 70.78),
    "Black Cobras":     (27.02, 70.91),
    "Bulls":            (23.07, 72.63),
    "Flying Bullets":   (26.10, 91.58),
    "Dragons":          (27.08, 93.61),
    "Battle Axes":      (27.49, 95.01),
    "Eagle Squadron":   (28.97, 77.08),
    "Phoenix Flight":   (31.63, 74.87),
    "Night Hunters":    (26.82, 75.80),
    # Army
    "Armoured Corps":       (27.17, 78.00),
    "Mechanised Infantry":  (28.61, 77.20),
    "Artillery":            (17.38, 78.49),
    "Army Aviation":        (17.45, 78.39),
    "Infantry":             (13.08, 80.27),
    "Para SF":              (33.50, 77.50),
    "Engineers":            (18.52, 73.85),
    # Navy
    "Western Fleet":             (18.93, 72.84),
    "Eastern Fleet":             (17.68, 83.29),
    "Southern Naval Command":    ( 9.94, 76.27),
    "Submarine Command":         (15.85, 74.50),
    "Naval Air Arm":             (15.85, 74.50),
    "Far Eastern Naval Command": (11.66, 92.73),
    "Andaman & Nicobar":         (11.66, 92.73),
}

# ── Heading lookup (unit → approximate patrol heading) ──────────────────────
UNIT_HEADING = {
    "Tigers": 10, "Tuskers": 5, "Winged Arrows": 180, "Oorials": 90,
    "Wolfpack": 270, "Eight Pursoots": 45, "Flying Lancers": 330,
    "Black Cobras": 0, "Bulls": 270, "Flying Bullets": 315,
    "Dragons": 200, "Battle Axes": 180, "Eagle Squadron": 60,
    "Western Fleet": 220, "Eastern Fleet": 90,
    "Southern Naval Command": 135, "Submarine Command": 45,
    "Naval Air Arm": 270, "Far Eastern Naval Command": 315,
    "Andaman & Nicobar": 200,
}


def _load_threshold() -> int:
    try:
        with open(RULES) as f:
            return json.load(f).get("__global_settings__", {}) \
                               .get("operational_threshold", 5)
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
        return []


def _scatter(lat, lon, radius=0.25):
    """Slightly scatter assets so markers don't pile on one point."""
    return (
        lat + random.uniform(-radius, radius),
        lon + random.uniform(-radius, radius),
    )


def _fake_history(lat, lon, heading, steps=4):
    """Generate a short backwards trail from the current position."""
    import math
    trail = []
    hdg_r = (heading + 180) % 360  # reverse
    for i in range(steps, 0, -1):
        d = i * 0.4
        la = lat + math.cos(math.radians(hdg_r)) * d
        lo = lon + math.sin(math.radians(hdg_r)) * d
        trail.append([round(la, 4), round(lo, 4)])
    trail.append([round(lat, 4), round(lon, 4)])
    return trail


def _load_assets(threshold: int) -> list[dict]:
    assets = []

    # ── IAF ────────────────────────────────────────────────────────────────
    rows = _sql(IAF_GOLD, """
        SELECT r.aircraft_id AS asset_id,
               g.aircraft_type AS type,
               g.squadron AS unit,
               COALESCE(r.final_readiness_score, g.readiness_base_score, 0) AS readiness
        FROM aircraft_readiness r
        JOIN aircraft_gold g ON r.aircraft_id = g.aircraft_id
    """)
    if not rows:
        rows = _sql(IAF_GOLD, """
            SELECT aircraft_id AS asset_id,
                   aircraft_type AS type,
                   squadron AS unit,
                   readiness_base_score AS readiness
            FROM aircraft_gold
        """)
    for r in rows:
        unit = r.get("unit") or ""
        coords = LOCATION_COORDS.get(unit)
        if not coords:
            continue
        lat, lon = _scatter(*coords)
        hdg = UNIT_HEADING.get(unit, random.randint(0, 359))
        assets.append({
            "asset_id": r["asset_id"],
            "type":     r["type"] or "Aircraft",
            "branch":   "IAF",
            "unit":     unit,
            "readiness": round(float(r["readiness"] or 0), 1),
            "lat":      round(lat, 4),
            "lon":      round(lon, 4),
            "heading":  hdg,
            "history":  _fake_history(lat, lon, hdg),
            "status":   (
                "operational" if float(r["readiness"] or 0) >= threshold
                else "watch"  if float(r["readiness"] or 0) >= threshold - 20
                else "critical"
            ),
        })

    # ── Army ────────────────────────────────────────────────────────────────
    rows = _sql(ARMY_GOLD, """
        SELECT r.asset_id,
               g.asset_type AS type,
               g.unit,
               COALESCE(r.final_readiness_score, g.readiness_base_score, 0) AS readiness
        FROM asset_readiness r
        JOIN assets_gold g ON r.asset_id = g.asset_id
    """)
    if not rows:
        rows = _sql(ARMY_GOLD, """
            SELECT asset_id, asset_type AS type, unit,
                   readiness_base_score AS readiness
            FROM assets_gold
        """)
    for r in rows:
        unit = r.get("unit") or ""
        coords = LOCATION_COORDS.get(unit)
        if not coords:
            continue
        lat, lon = _scatter(*coords)
        hdg = UNIT_HEADING.get(unit, random.randint(0, 359))
        assets.append({
            "asset_id": r["asset_id"],
            "type":     r["type"] or "Vehicle",
            "branch":   "Army",
            "unit":     unit,
            "readiness": round(float(r["readiness"] or 0), 1),
            "lat":      round(lat, 4),
            "lon":      round(lon, 4),
            "heading":  hdg,
            "history":  _fake_history(lat, lon, hdg),
            "status":   (
                "operational" if float(r["readiness"] or 0) >= threshold
                else "watch"  if float(r["readiness"] or 0) >= threshold - 20
                else "critical"
            ),
        })

    # ── Navy ────────────────────────────────────────────────────────────────
    rows = _sql(NAVY_GOLD, """
        SELECT r.vessel_id AS asset_id,
               g.vessel_type AS type,
               g.flotilla AS unit,
               COALESCE(r.final_readiness_score, g.readiness_base_score, 0) AS readiness
        FROM vessel_readiness r
        JOIN vessels_gold g ON r.vessel_id = g.vessel_id
    """)
    if not rows:
        rows = _sql(NAVY_GOLD, """
            SELECT vessel_id AS asset_id, vessel_type AS type,
                   flotilla AS unit, readiness_base_score AS readiness
            FROM vessels_gold
        """)
    for r in rows:
        unit = r.get("unit") or ""
        coords = LOCATION_COORDS.get(unit)
        if not coords:
            continue
        lat, lon = _scatter(*coords, radius=0.4)
        hdg = UNIT_HEADING.get(unit, random.randint(0, 359))
        assets.append({
            "asset_id": r["asset_id"],
            "type":     r["type"] or "Vessel",
            "branch":   "Navy",
            "unit":     unit,
            "readiness": round(float(r["readiness"] or 0), 1),
            "lat":      round(lat, 4),
            "lon":      round(lon, 4),
            "heading":  hdg,
            "history":  _fake_history(lat, lon, hdg),
            "status":   (
                "operational" if float(r["readiness"] or 0) >= threshold
                else "watch"  if float(r["readiness"] or 0) >= threshold - 20
                else "critical"
            ),
        })

    return assets


def render_geo_map_3d():
    st.markdown("## 🌐 3-D Tactical Globe — भारत रक्षा")
    st.caption(
        "Live tactical common operating picture — "
        "hover or click any asset for its track thumbnail. "
        "Drag to rotate · scroll to zoom."
    )

    threshold = _load_threshold()
    assets    = _load_assets(threshold)

    if not assets:
        st.warning(
            "No geo-located assets found. Run the full pipeline first:\n"
            "```\npython sankalp_orchestrator.py\n```"
        )
        return

    # ── Summary strip ────────────────────────────────────────────────────────
    op    = sum(1 for a in assets if a["status"] == "operational")
    watch = sum(1 for a in assets if a["status"] == "watch")
    crit  = sum(1 for a in assets if a["status"] == "critical")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Assets", len(assets))
    c2.metric("🟢 Operational", op)
    c3.metric("🟡 Watch",       watch)
    c4.metric("🔴 Critical",    crit)
    with c5:
        if st.button("🔄 Refresh Globe", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")

    # ── Build HTML ───────────────────────────────────────────────────────────
    try:
        with open(_HTML, encoding="utf-8") as f:
            html_template = f.read()
    except FileNotFoundError:
        st.error(f"Globe template not found: `{_HTML}`")
        return

    assets_json   = json.dumps(assets)
    force_refresh = "false"

    html = (
        html_template
        .replace("__ASSETS_JSON__",  assets_json)
        .replace("__THRESHOLD__",    str(threshold))
        .replace("__FORCE_REFRESH__", force_refresh)
    )

    st.components.v1.html(html, height=720, scrolling=False)
