"""
automation_integration_patch.py
================================
Shows exactly what to add/change in two existing files.
Run this script to apply the patches automatically:

    python automation_integration_patch.py

Or apply manually using the diff sections below.
"""

import re

# ════════════════════════════════════════════════════════════════════════════
#  PATCH 1 — agents/darshan_left_sidebar.py
#  Add the Automation branch to the sidebar list
# ════════════════════════════════════════════════════════════════════════════

SIDEBAR_OLD = '''    branches = [
        ("iaf",   "✈️", "Indian Air Force", "IAF"),
        ("army",  "🪖", "Indian Army",       "ARMY"),
        ("navy",  "⚓", "Indian Navy",       "NAVY"),
        ("ontology", "🧠", "Ontology Engine", "LOGIC"),
        ("admin", "⚙️", "Admin / Data Import", "ADMIN"),
    ]'''

SIDEBAR_NEW = '''    branches = [
        ("iaf",        "✈️", "Indian Air Force",    "IAF"),
        ("army",       "🪖", "Indian Army",          "ARMY"),
        ("navy",       "⚓", "Indian Navy",          "NAVY"),
        ("ontology",   "🧠", "Ontology Engine",      "LOGIC"),
        ("automation", "⚡", "Automation Engine",    "AUTO"),
        ("admin",      "⚙️", "Admin / Data Import",  "ADMIN"),
    ]'''

# ════════════════════════════════════════════════════════════════════════════
#  PATCH 2 — agents/darshan.py
#  (a) Import render_automation
#  (b) Add branch route at the bottom
# ════════════════════════════════════════════════════════════════════════════

DARSHAN_IMPORT_OLD = "from darshan_navy_branch import render_navy"
DARSHAN_IMPORT_NEW = (
    "from darshan_navy_branch import render_navy\n"
    "from darshan_automation_tab import render_automation"
)

DARSHAN_ROUTE_OLD = "elif branch == \"admin\":"
DARSHAN_ROUTE_NEW = (
    "elif branch == \"automation\":\n"
    "    render_automation()\n"
    "elif branch == \"admin\":"
)

# ════════════════════════════════════════════════════════════════════════════
#  PATCH 3 — sankalp_orchestrator.py
#  Start the automation scheduler after all pipelines complete
# ════════════════════════════════════════════════════════════════════════════

ORCH_IMPORT_OLD = "import sys\nimport subprocess\nimport logging"
ORCH_IMPORT_NEW = (
    "import sys\nimport subprocess\nimport logging\n"
    "from agents.automation_engine import init_db as auto_init_db, start_scheduler"
)

ORCH_DASHBOARD_OLD = '    print("\\n" + "─" * 50)'
ORCH_DASHBOARD_NEW = '''    # ══════════════════════════════════════════════════════
    #  AUTOMATION ENGINE
    # ══════════════════════════════════════════════════════
    print("\\n" + "─" * 50)
    print("⚡  AUTOMATION ENGINE")
    print("─" * 50)
    print("\\n🟢 Initialising automation DB and starting scheduler…")
    auto_init_db()
    start_scheduler(interval_minutes=5)
    print("   ✔ Scheduler running — evaluating rules every 5 minutes.")

    print("\\n" + "─" * 50)'''


def _apply(path: str, old: str, new: str, label: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        if old not in src:
            print(f"  ⚠  [{label}] target string not found in {path} — skipping (may already be applied).")
            return
        src = src.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"  ✅ [{label}] patched {path}")
    except FileNotFoundError:
        print(f"  ❌ [{label}] file not found: {path}")


if __name__ == "__main__":
    print("\n=== Applying automation integration patches ===\n")

    _apply("agents/darshan_left_sidebar.py", SIDEBAR_OLD,  SIDEBAR_NEW,  "sidebar branch list")
    _apply("agents/darshan.py",              DARSHAN_IMPORT_OLD, DARSHAN_IMPORT_NEW, "darshan import")
    _apply("agents/darshan.py",              DARSHAN_ROUTE_OLD,  DARSHAN_ROUTE_NEW,  "darshan route")
    _apply("sankalp_orchestrator.py",        ORCH_IMPORT_OLD,    ORCH_IMPORT_NEW,    "orchestrator import")
    _apply("sankalp_orchestrator.py",        ORCH_DASHBOARD_OLD, ORCH_DASHBOARD_NEW, "orchestrator scheduler start")

    print("\n=== Done. ===")
    print("Run `pip install apscheduler>=3.10` if not already installed.")
    print("Then restart `python sankalp_orchestrator.py`.\n")
