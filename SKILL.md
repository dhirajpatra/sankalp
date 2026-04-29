---
name: sankalp-ontology-platform
description: Build a multi-agent MVP named Sankalp – an open-source, Defence Ontology Platform “Ontology as a digital twin” tailored for Indian defence use cases (DRDO, Indian Army, IAF, Navy). Built with Python, Neo4j, Streamlit, and optional ML integration.
---

# Skill: Sankalp – Multi-Agent Open Ontology Builder for Indian Defence

## Purpose
Enable Claude to guide the development of a **multi-agent MVP** named **Sankalp** – an open-source, “Ontology as a digital twin” tailored for Indian defence use cases (DRDO, Indian Army, IAF, Navy). Built with Python, Neo4j, Streamlit, and optional ML integration.

## Core Multi-Agent Architecture (Sankalp's 5 Agents)

| Agent Name (Sankalp Codename) | Defence Ontology Equivalent | Open Source Tool | Defence-Relevant Function |
|-------------------------------|--------------------|------------------|---------------------------|
| **Ganana** (गणना – Counting) | Ingestion / Magritte | Airbyte / Python (Pandas) | Ingest logistics, personnel, platform data from multiple defence silos. |
| **Shodhan** (शोधन – Purification) | Foundry Pipeline | dbt / Pandas + SQLite | Clean and standardise data (e.g., inconsistent unit names, vehicle IDs). |
| **Bandhan** (बंधन – Bond/Link) | Ontology (Objects + Links) | Neo4j (Cypher) | Map entities to nodes (e.g., `:Aircraft`, `:Squadron`, `:MaintenanceLog`) and relationships. |
| **Darshan** (दर्शन – View) | Workshop / Quiver | Streamlit + FastAPI | Provide command‑dashboards for officers to query assets and run actions. |
| **Bhavishyavani** (भविष्यवाणी – Forecast) | Model Integration | scikit‑learn + Neo4j GDS | Predict readiness scores, maintenance windows, or risk of asset failure. |

---

## Sankalp MVP Scope (1-2 days, defence‑themed)

**Input:** Small CSV files representing defence logistics:
- `aircraft.csv` (aircraft_id, type, squadron, last_maintenance_date, flight_hours)
- `crew.csv` (crew_id, name, rank, aircraft_type_qualified)
- `missions.csv` (mission_id, aircraft_id, crew_id, date, mission_type, fuel_used)

**Output:** Streamlit dashboard "Sankalp Darshan" where a defence user can:
- Select an aircraft → see its crew, mission history, and predicted maintenance due date.
- Click **"Log New Mission"** action – writes back to Neo4j (replaces Ontology's "Action").
- See a **"Readiness Score"** (0–100%) as an ML‑generated property on each aircraft.

**No production security** – but labels and variable names reflect defence terminology.

---

## Agent Prompts (Sankalp Versions)

### 1. Ganana (Ingestion Agent) – prompt
```text
You are Ganana, Sankalp's Ingestion Agent for Indian defence. Write a Python function that:
- Reads CSV files from a 'data/raw/' folder (aircraft.csv, crew.csv, missions.csv).
- Stores each as a table in an SQLite database called 'sankalp_raw.db'.
- Handles missing values by logging warnings (e.g., null last_maintenance_date).
- Returns a status dictionary with table names and row counts.
```

### 2. Shodhan (Transformation Agent) – prompt
```text
You are Shodhan, Sankalp's Transformation Agent. From 'sankalp_raw.db', produce three 'Gold' tables:
- `aircraft_gold`: aircraft_id, type, squadron, last_maintenance_date (converted to ISO), flight_hours, readiness_base_score (calculated as 100 - (flight_hours / 10) capped at 0-100).
- `crew_gold`: crew_id, name, rank, aircraft_type_qualified.
- `missions_gold`: mission_id, aircraft_id, crew_id, date, mission_type, fuel_used.

Write these to 'sankalp_gold.db'. Return the list of created tables.
```

### 3. Bandhan (Ontology Agent – Neo4j) – prompt
```text
You are Bandhan, Sankalp's Ontology Agent. Write Python code to:
- Connect to Neo4j (default: localhost:7687, auth none for MVP).
- Clear existing nodes/relationships.
- Read `aircraft_gold`, `crew_gold`, `missions_gold` from 'sankalp_gold.db'.
- Create nodes:
  - :Aircraft (properties from aircraft_gold)
  - :Crew (properties from crew_gold)
  - :Mission (properties from missions_gold)
- Create relationships:
  - (crew)-[:PARTICIPATED_IN]->(mission)
  - (aircraft)-[:EXECUTED]->(mission)
- Return node and relationship counts.
```

### 4. Darshan (UI Agent – Streamlit) – prompt
```text
You are Darshan, Sankalp's UI Agent. Write a Streamlit app titled "Sankalp – Defence Digital Twin" that:
- Allows user to select an Aircraft ID from a dropdown.
- Displays aircraft properties (type, squadron, flight_hours, readiness_base_score).
- Shows a list of missions that aircraft executed (date, mission_type, crew involved).
- Contains a button "Log New Mission". When clicked:
  - Opens a small form (mission date, type, fuel used).
  - On submit, runs a Cypher query to create a new :Mission node and connects it to the selected aircraft.
  - Also updates the aircraft's flight_hours (+1 hour per mission).
- Shows total counts: #Aircraft, #Crew, #Missions in the sidebar.
```

### 5. Bhavishyavani (ML Agent) – prompt
```text
You are Bhavishyavani, Sankalp's ML Integration Agent. Do:
1. Using Neo4j and Graph RAG if required, compute for each aircraft:
   - mission_count = number of connected missions
   - days_since_last_mission = (today - last mission date).days
2. Train a simple RandomForestRegressor (or rule-based) that calculates a "final_readiness_score" = 
   base_readiness_score * 0.6 - (days_since_last_mission * 0.5) + (mission_count * 0.2), clipped to 0-100.
3. Write final_readiness_score as a property on each :Aircraft node.
4. Return top 3 aircraft with lowest readiness scores (need maintenance attention).
```

---

## Message Protocol (Sankalp Orchestrator)

Simple sequential Python orchestrator – `sankalp_orchestrator.py`:

```python
from agents import ganana, shodhan, bandhan, darshan, bhavishyavani

def main():
    context = {}
    
    print("🟢 Ganana: Ingestion...")
    context['raw_db'] = ganana.ingest()
    
    print("🔵 Shodhan: Transformation...")
    context['gold_db'] = shodhan.transform(context['raw_db'])
    
    print("🟡 Bandhan: Building Ontology in Neo4j...")
    context['graph_stats'] = bandhan.build_ontology(context['gold_db'])
    
    print("🟠 Bhavishyavani: Computing Readiness Scores...")
    context['risk_assets'] = bhavishyavani.compute_readiness()
    
    print("🟣 Darshan: Launching UI...")
    darshan.launch_dashboard()   # Blocks or subprocess

if __name__ == "__main__":
    main()
```

---

## Sankalp-Specific Evaluation Criteria

| Criteria | Defence Analogy | Verification |
|----------|----------------|--------------|
| Objects & Links | Aircraft → Mission → Crew lineage | `MATCH (a:Aircraft)-[:EXECUTED]->(m:Mission)<-[:PARTICIPATED_IN]-(c:Crew) RETURN *` |
| Action writes back | Logging a new mission in the field | UI form → new mission appears in Neo4j and aircraft flight_hours increase |
| ML readiness score | Predictive maintenance for IAF | Query `MATCH (a:Aircraft) RETURN a.final_readiness_score` → non‑null values |
| Agent independence | Remove Bhavishyavani → Darshan still runs (no readiness score) | Uninstall ML libs → UI still shows aircraft base data |

---

## Open Source Stack (Sankalp Lock)

```yaml
Ingestion: pandas 2.0+, SQLite3
Transformation: pandas OR dbt-core 1.5+
Graph DB: Neo4j 5.x (Community / AuraDB free)
Graph Driver: neo4j-python-driver
UI: streamlit 1.28+, py2neo
ML: scikit-learn 1.3+
Orchestration: Python 3.10+
Visualisation (optional): streamlit-agraph or pyvis
```

---

## One-Command Startup for Sankalp MVP

```bash
# Clone / create project
mkdir sankalp && cd sankalp

# Start Neo4j (Docker)
docker run --name sankalp-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=none -d neo4j:5

# Install dependencies
pip install pandas streamlit neo4j scikit-learn

# Run orchestrator
python sankalp_orchestrator.py
```

---

## Sample Defence Data (for `data/raw/aircraft.csv`)

```csv
aircraft_id,type,squadron,last_maintenance_date,flight_hours
IAF-101,Su-30MKI,No. 20 Squadron,2025-01-15,1200
IAF-102,MiG-29,No. 28 Squadron,2024-11-20,950
IAF-203,Tejas,No. 45 Squadron,2025-02-10,320
```

---

## Sankalp Skill Activation Phrase

When you want Claude to use this skill, say:
> **"Use the Sankalp skill to build the multi-agent MVP"**

Claude will then:
1. Generate all 5 agent files with defence‑centric naming.
2. Provide the orchestrator and sample data.
3. Add Indian defence commentary and comments in code (e.g., `# DRDO requirement: asset lineage`).
4. Ask clarifying questions about your specific defence branch (Army/Navy/IAF) to tailor labels.

---

## Sankalp Repository Structure (Generated by Claude)

```
sankalp/
├── sankalp_orchestrator.py
├── agents/
│   ├── __init__.py
│   ├── ganana.py (ingestion)
│   ├── shodhan.py (transformation)
│   ├── bandhan.py (ontology + Neo4j)
│   ├── darshan.py (Streamlit UI)
│   └── bhavishyavani.py (ML readiness)
|   └──system/
|   └──tasks/
|   └──tools/
├── data/
│   └── raw/
│       ├── aircraft.csv
│       ├── crew.csv
│       └── missions.csv
|   └──processed/ (created at runtime)
├── evals/
│   └── tests/
|   └── traces/
|   └── scorecards/
├── sankalp.db (created at runtime)
├── sankalp_gold.db (created at runtime)
├── docker-compose.yml (Neo4j)
└── README.md (Sankalp-specific instructions)
```
