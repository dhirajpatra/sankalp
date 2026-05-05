"""
integration_patch.py – Wire new modules into Darshan
Run once: python integration_patch.py

Adds to darshan_left_sidebar.py:
  - 🗺️ Geo Map
  - 🎯 Threat Intel
  - 📋 Mission Plan

Adds to darshan.py:
  - imports for geo_map, threat, yojana
  - branch routes
"""

def _apply(path: str, old: str, new: str, label: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        if old not in src:
            print(f"  ⚠  [{label}] already applied or target not found in {path}")
            return
        src = src.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  ✅ [{label}] patched {path}")
    except FileNotFoundError:
        print(f"  ❌ [{label}] file not found: {path}")


# ── Sidebar: add new branches ─────────────────────────────────────────────────
SIDEBAR_OLD = '''        branches = [
            ("iaf",      "✈️", "Indian Air Force",    "IAF"),
            ("army",     "🪖", "Indian Army",          "ARMY"),
            ("navy",     "⚓", "Indian Navy",           "NAVY"),
            ("ontology", "🧠", "Ontology Engine",       "LOGIC"),
            ("alerts",   "🔔", "Live Alerts",           "ALERTS"),  # ← new
            ("admin",    "⚙️", "Admin / Data Import",  "ADMIN"),
        ]'''

SIDEBAR_NEW = '''        branches = [
            ("iaf",      "✈️", "Indian Air Force",    "IAF"),
            ("army",     "🪖", "Indian Army",          "ARMY"),
            ("navy",     "⚓", "Indian Navy",           "NAVY"),
            ("ontology", "🧠", "Ontology Engine",       "LOGIC"),
            ("alerts",   "🔔", "Live Alerts",           "ALERTS"),
            ("threat",   "🎯", "Threat Intel",          "THREAT"),
            ("yojana",   "📋", "Mission Plan",          "PLAN"),
            ("map",      "🗺️", "Geo Map",              "MAP"),
            ("admin",    "⚙️", "Admin / Data Import",  "ADMIN"),
        ]'''

# ── darshan.py: add imports ───────────────────────────────────────────────────
DARSHAN_IMPORT_OLD = "from darshan_navy_branch import render_navy"
DARSHAN_IMPORT_NEW = (
    "from darshan_navy_branch import render_navy\n"
    "from darshan_threat_tab import render_threat_panel\n"
    "from darshan_yojana_tab import render_yojana_panel\n"
    "from darshan_geo_map import render_geo_map"
)

# ── darshan.py: add routes ────────────────────────────────────────────────────
DARSHAN_ROUTE_OLD = 'elif branch == "admin":'
DARSHAN_ROUTE_NEW = (
    'elif branch == "threat":\n'
    '    render_threat_panel()\n'
    'elif branch == "yojana":\n'
    '    render_yojana_panel()\n'
    'elif branch == "map":\n'
    '    render_geo_map()\n'
    'elif branch == "admin":'
)


if __name__ == "__main__":
    print("\n=== Applying new module integration patches ===\n")
    _apply("agents/darshan_left_sidebar.py", SIDEBAR_OLD,         SIDEBAR_NEW,         "sidebar branches")
    _apply("agents/darshan.py",              DARSHAN_IMPORT_OLD,  DARSHAN_IMPORT_NEW,  "darshan imports")
    _apply("agents/darshan.py",              DARSHAN_ROUTE_OLD,   DARSHAN_ROUTE_NEW,   "darshan routes")
    print("\n=== Done ===")
    print("Install new deps if needed:")
    print("  pip install folium streamlit-folium mcp")
