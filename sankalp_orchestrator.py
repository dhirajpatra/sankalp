"""
sankalp_orchestrator.py – Sankalp Multi-Agent Orchestrator
Runs all defence agents (IAF, Army, Navy) in sequence, passing shared context.
"""

import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sankalp")


def main():
    print("\n" + "=" * 60)
    print("  🛡️  SANKALP – DEFENCE DIGITAL TWIN ORCHESTRATOR  🛡️")
    print("  भारतीय सशस्त्र सेना | Open Source Ontology Platform")
    print("  IAF · Army · Navy")
    print("=" * 60 + "\n")

    context = {}

    # ══════════════════════════════════════════════════════
    #  IAF PIPELINE
    # ══════════════════════════════════════════════════════
    print("─" * 50)
    print("✈️  IAF PIPELINE")
    print("─" * 50)

    print("🟢 [1/5] Ganana (IAF): Ingesting raw IAF data...")
    from agents.ganana import ingest
    context["iaf_raw"] = ingest()
    for table, info in context["iaf_raw"].items():
        print(f"   ✔ {table}: {info['rows']} rows")

    print("\n🔵 [2/5] Shodhan (IAF): Transforming to Gold quality...")
    from agents.shodhan import transform
    context["iaf_gold_db"] = transform()
    print(f"   ✔ Gold store: {context['iaf_gold_db']}")

    print("\n🟡 [3/5] Bandhan (IAF): Building Neo4j ontology graph...")
    from agents.bandhan import build_ontology as iaf_build
    context["iaf_graph"] = iaf_build(context["iaf_gold_db"])
    s = context["iaf_graph"]
    print(f"   ✔ Aircraft: {s.get('aircraft',0)}, Crew: {s.get('crew',0)}, "
          f"Missions: {s.get('missions',0)}, Relationships: {s.get('relationships',0)}")
    if s.get("mode") == "offline":
        print("   ⚠️  Neo4j offline – ontology built in SQLite only")

    print("\n🟠 [4/5] Bhavishyavani (IAF): Computing AI readiness scores...")
    from agents.bhavishyavani import compute_readiness
    context["iaf_at_risk"] = compute_readiness(context["iaf_gold_db"])
    print("   ⚠️  Top-3 IAF aircraft requiring maintenance attention:")
    for r in context["iaf_at_risk"]:
        print(f"      {r['aircraft_id']} ({r['type']}) – Score: {r['final_readiness_score']:.1f}%")

    # ══════════════════════════════════════════════════════
    #  ARMY PIPELINE
    # ══════════════════════════════════════════════════════
    print("\n" + "─" * 50)
    print("🪖  ARMY PIPELINE")
    print("─" * 50)

    print("\n🟢 [1/3] Ganana (Army): Ingesting raw Army data...")
    from agents.ganana_army import ingest as army_ingest
    context["army_raw"] = army_ingest()
    for table, info in context["army_raw"].items():
        print(f"   ✔ {table}: {info['rows']} rows")

    print("\n🔵 [2/3] Shodhan (Army): Transforming to Gold quality...")
    from agents.shodhan_army import transform as army_transform
    context["army_gold_db"] = army_transform()
    print(f"   ✔ Gold store: {context['army_gold_db']}")

    print("\n🟡 [3/3] Bandhan (Army): Building Neo4j ontology graph...")
    from agents.bandhan_army import build_ontology as army_build
    context["army_graph"] = army_build(context["army_gold_db"])
    s = context["army_graph"]
    print(f"   ✔ Assets: {s.get('assets',0)}, Crew: {s.get('crew',0)}, "
          f"Ops: {s.get('ops',0)}, Relationships: {s.get('relationships',0)}")
    if s.get("mode") == "offline":
        print("   ⚠️  Neo4j offline – Army ontology built in SQLite only")

    # ══════════════════════════════════════════════════════
    #  NAVY PIPELINE
    # ══════════════════════════════════════════════════════
    print("\n" + "─" * 50)
    print("⚓  NAVY PIPELINE")
    print("─" * 50)

    print("\n🟢 [1/3] Ganana (Navy): Ingesting raw Navy data...")
    from agents.ganana_navy import ingest as navy_ingest
    context["navy_raw"] = navy_ingest()
    for table, info in context["navy_raw"].items():
        print(f"   ✔ {table}: {info['rows']} rows")

    print("\n🔵 [2/3] Shodhan (Navy): Transforming to Gold quality...")
    from agents.shodhan_navy import transform as navy_transform
    context["navy_gold_db"] = navy_transform()
    print(f"   ✔ Gold store: {context['navy_gold_db']}")

    print("\n🟡 [3/3] Bandhan (Navy): Building Neo4j ontology graph...")
    from agents.bandhan_navy import build_ontology as navy_build
    context["navy_graph"] = navy_build(context["navy_gold_db"])
    s = context["navy_graph"]
    print(f"   ✔ Vessels: {s.get('vessels',0)}, Crew: {s.get('crew',0)}, "
          f"Sorties: {s.get('sorties',0)}, Relationships: {s.get('relationships',0)}")
    if s.get("mode") == "offline":
        print("   ⚠️  Neo4j offline – Navy ontology built in SQLite only")

    # ══════════════════════════════════════════════════════
    #  DASHBOARD
    # ══════════════════════════════════════════════════════
    print("\n" + "─" * 50)
    print("🟣 Darshan: Launching Streamlit command dashboard...")
    print("   → http://localhost:8501\n")
    print("=" * 60)
    subprocess.run([sys.executable, "-m", "streamlit", "run", "agents/darshan.py", "--server.port", "8501"])


if __name__ == "__main__":
    main()
