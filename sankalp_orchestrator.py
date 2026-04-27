"""
sankalp_orchestrator.py – Sankalp Multi-Agent Orchestrator
Runs the five defence agents in sequence, passing shared context between them.
"""

import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sankalp")


def main():
    print("\n" + "=" * 60)
    print("  🛡️  SANKALP – DEFENCE DIGITAL TWIN ORCHESTRATOR  🛡️")
    print("  भारतीय वायु सेना | Open Source Ontology Platform")
    print("=" * 60 + "\n")

    context = {}

    # --- Step 1: Ganana – Ingestion ---
    print("🟢 [1/5] Ganana: Ingesting raw defence data...")
    from agents.ganana import ingest
    context["raw_status"] = ingest()
    for table, info in context["raw_status"].items():
        print(f"   ✔ {table}: {info['rows']} rows")

    # --- Step 2: Shodhan – Transformation ---
    print("\n🔵 [2/5] Shodhan: Transforming to Gold quality...")
    from agents.shodhan import transform
    context["gold_db"] = transform()
    print(f"   ✔ Gold store: {context['gold_db']}")

    # --- Step 3: Bandhan – Ontology ---
    print("\n🟡 [3/5] Bandhan: Building Neo4j ontology graph...")
    from agents.bandhan import build_ontology
    context["graph_stats"] = build_ontology(context["gold_db"])
    stats = context["graph_stats"]
    print(f"   ✔ Aircraft: {stats.get('aircraft',0)}, Crew: {stats.get('crew',0)}, "
          f"Missions: {stats.get('missions',0)}, Relationships: {stats.get('relationships',0)}")
    if stats.get("mode") == "offline":
        print("   ⚠️  Neo4j offline – ontology built in SQLite only (set bolt URI in bandhan.py)")

    # --- Step 4: Bhavishyavani – ML Readiness ---
    print("\n🟠 [4/5] Bhavishyavani: Computing AI readiness scores...")
    from agents.bhavishyavani import compute_readiness
    context["at_risk"] = compute_readiness(context["gold_db"])
    print("   ⚠️  Top-3 aircraft requiring maintenance attention:")
    for r in context["at_risk"]:
        print(f"      {r['aircraft_id']} ({r['type']}) – Score: {r['final_readiness_score']:.1f}%")

    # --- Step 5: Darshan – Launch Dashboard ---
    print("\n🟣 [5/5] Darshan: Launching Streamlit command dashboard...")
    print("   → http://localhost:8501\n")
    print("=" * 60)
    subprocess.run([sys.executable, "-m", "streamlit", "run", "agents/darshan.py", "--server.port", "8501"])


if __name__ == "__main__":
    main()
