# 🛡️ SANKALP — Defence Ontology Platform

> **संकल्प** (Sankalp) — *"A solemn resolve"*  
> "Ontology as Digital Twin" for Indian Defence (DRDO / IAF / Army / Navy).

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.x-green)](https://neo4j.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🧠 Architecture — 5 Agents

| Agent | Sanskrit Name | Role |
|-------|--------------|------|
| Ingestion | **Ganana** (गणना) | Reads CSVs → SQLite raw store |
| Transformation | **Shodhan** (शोधन) | Cleans & enriches → Gold tables |
| Ontology | **Bandhan** (बंधन) | Builds Neo4j knowledge graph |
| ML Readiness | **Bhavishyavani** (भविष्यवाणी) | Computes AI readiness scores |
| Dashboard | **Darshan** (दर्शन) | Streamlit command interface |

---

## 🚀 Quick Start

### 1. Clone & setup
```bash
git clone https://github.com/<your-org>/sankalp.git
cd sankalp
cp .env.example .env 
pip install -r requirements.txt

# Create the Neo4j import directory before running Docker
# This ensures it is owned by your user, preventing permission errors
mkdir -p data/neo4j_import
```

### 2. Start Neo4j (Docker)
```bash
docker compose up -d
```
Neo4j Browser: http://localhost:7474 (user: `neo4j user`, pass: `neo4j password`)

### 3. Run the full pipeline
```bash
python sankalp_orchestrator.py
```

Dashboard opens at: http://localhost:8501

### 4. Without Neo4j (offline / demo mode)
The system runs fully in SQLite — Bandhan and Bhavishyavani log warnings and continue.

## Architecture:

![Architecture Diagram](docs/sankalp_architecture.svg)


- **Data sources** — three parallel branches (IAF, Army, Navy) each supplying CSVs
- **Ganana** — ingestion agents per branch, writing to SQLite raw stores
- **Shodhan** — transformation agents producing Gold-quality tables
- **Bandhan** — the shared ontology agent that merges all three branches into the Neo4j knowledge graph
- **Neo4j** — the central graph store holding `:Aircraft`, `:ArmyAsset`, `:Vessel`, crew, missions, sorties, and relationships
- **Bhavishyavani** *(amber)* — ML readiness scoring, writing `final_readiness_score` back to Neo4j
- **Ontology Engine** *(red)* — doctrine rule evaluation + Groq LLM + RAG layer
- **Readiness Monitor** *(gray)* — background polling thread writing to the Alerts SQLite DB
- **Darshan** — the Streamlit dashboard that surfaces everything across all branches

The dashed arrow from Bhavishyavani back to Neo4j represents the score write-back. Let me know if you'd like a more detailed sub-diagram for any specific layer, like the Neo4j graph schema or the Darshan UI routing.


## 🔔 Optimization Engine — Live Alerts

The Live Alerts system is an event-driven readiness monitor that runs as a background thread alongside the main orchestrator. It continuously polls the Neo4j knowledge graph, evaluates all defined doctrine rules, and automatically records alerts whenever operational tiers change.

### How it works

A background thread (`readiness_monitor.py`) wakes every 10 seconds (configurable via `MONITOR_POLL_SECS`), queries Neo4j for the latest readiness scores across all three branches, and runs `evaluate_action()` against every doctrine rule. If a rule's tier shifts — say from `ADEQUATE` to `INSUFFICIENT` because too many aircraft dropped below the operational threshold — the monitor writes an alert record to a local SQLite database (`data/processed/sankalp_alerts.db`) with the direction of change, the branch counts at the time, and a human-readable message.

### Alert tiers

| Tier | Meaning |
|---|---|
| 🏆 SUPERIOR | All branch requirements met and enhancement thresholds exceeded |
| 🟡 ADEQUATE | Minimum requirements met; action is executable |
| 🔴 INSUFFICIENT | One or more branch minimums not met; action cannot be executed |

A transition from a higher tier to a lower one is recorded as `degraded`; the reverse is recorded as `improved`.

### Viewing alerts

Navigate to **🔔 Live Alerts** in the Darshan sidebar. The panel shows:

- A **fleet readiness timeline** — line chart of average readiness % per branch over time (IAF, Army, Navy)
- An **operational count timeline** — how many assets are in `Operational` status per branch
- A **scrollable event log** of all tier changes, colour-coded by direction, with branch counts at the time of each event

You can toggle "Show acknowledged" to include older read alerts, and mark all unread alerts as acknowledged with a single click.

### Architecture

```
Neo4j (live graph)
      ↓  polls every 10s
readiness_monitor.py  (background daemon thread)
      ↓  on tier change
sankalp_alerts.db  (SQLite — alerts + fleet_snapshots tables)
      ↓  reads
Darshan → 🔔 Live Alerts panel  (Streamlit, auto-refreshes every 15s)
```

### Configuration

| Variable | Default | Description |
|---|---|---|
| `MONITOR_POLL_SECS` | `10` | Polling interval in seconds |
| `GLOBAL_OPERATIONAL_THRESHOLD` | `5` | Base score threshold for `Operational` status |

The monitor starts automatically when the orchestrator runs and restarts idempotently if the Darshan UI calls `ensure_monitor()` on each page load. It degrades gracefully — if Neo4j is unreachable, it falls back to reading readiness scores directly from the Gold SQLite stores.


## 📁 Project Structure

```
sankalp-ontology-platform/
│
├── sankalp_orchestrator.py         # Master orchestrator — runs all agents then launches dashboard
├── config.yml                      # Central configuration (ports, paths, thresholds, LLM settings)
├── config_loader.py                # cfg() helper — reads config.yml with dot-path access
│
├── agents/                         # All pipeline & UI agents
│   │
│   │── Ingestion (Ganana)
│   ├── ganana.py                   # IAF raw data ingestion (CSV → SQLite)
│   ├── ganana_army.py              # Army raw data ingestion
│   ├── ganana_navy.py              # Navy raw data ingestion
│   │
│   │── Transformation (Shodhan)
│   ├── shodhan.py                  # IAF data cleansing & gold table build
│   ├── shodhan_army.py             # Army transformation
│   ├── shodhan_navy.py             # Navy transformation
│   │
│   │── Ontology Graph (Bandhan)
│   ├── bandhan.py                  # IAF → Neo4j knowledge graph builder
│   ├── bandhan_army.py             # Army → Neo4j graph builder
│   ├── bandhan_navy.py             # Navy → Neo4j graph builder
│   │
│   │── ML Readiness (Bhavishyavani)
│   ├── bhavishyavani.py            # AI readiness score computation (IAF)
│   │
│   │── AI / Ontology Engine
│   ├── ontology_engine.py          # NL → Cypher LLM engine (Groq + tool calling)
│   ├── ontology_tools.py           # Cypher execution tools for LLM
│   ├── ontology_rag.py             # RAG pipeline over ontology rules (FAISS)
│   ├── ontology_rules.json         # Default rule definitions (seeded to data/processed/)
│   │
│   │── Event-Driven Monitor
│   ├── readiness_monitor.py        # Background thread — polls Neo4j, writes alerts DB
│   ├── automation_engine.py        # Automated action scheduling & execution
│   │
│   │── Dashboard (Darshan — Streamlit)
│   ├── darshan.py                  # Main Streamlit entry point & page config
│   ├── darshan_left_sidebar.py     # Sidebar navigation & branch selector
│   ├── darshan_db_helper.py        # Shared DB/Neo4j data loaders & score utilities
│   ├── darshan_branch_renders.py   # Reusable metric cards & readiness chart components
│   ├── darshan_iaf_branch.py       # IAF branch tab renderer
│   ├── darshan_army_branch.py      # Army branch tab renderer
│   ├── darshan_navy_branch.py      # Navy branch tab renderer
│   ├── darshan_alerts_panel.py     # Live alerts panel (reads alerts DB)
│   ├── darshan_automation_tab.py   # Automation controls tab
│   ├── darshan_chat_patch.py       # Ontology Engine chat panel patch
│   ├── render_ontology_engine_patch.py  # Ontology engine rendering helpers
│   ├── admin_import.py             # Admin: manual CSV import via dashboard
│   │
│   ├── assets/
│   │   └── styles/
│   │       └── style.css           # Global Streamlit CSS theme
│   │
│   └── __init__.py
│
├── data/
│   ├── raw/                        # Source CSV files (input data)
│   │   ├── aircraft.csv
│   │   ├── crew.csv
│   │   ├── missions.csv
│   │   ├── squadrons.csv
│   │   ├── maintenance_logs.csv
│   │   ├── army_assets.csv
│   │   ├── army_crew.csv
│   │   ├── army_ops.csv
│   │   ├── navy_vessels.csv
│   │   ├── navy_crew.csv
│   │   └── navy_sorties.csv
│   │
│   ├── processed/                  # Auto-generated at runtime (gitignored)
│   │   ├── sankalp_raw.db          # IAF raw SQLite store
│   │   ├── sankalp_gold.db         # IAF gold SQLite store
│   │   ├── sankalp_army_raw.db
│   │   ├── sankalp_army_gold.db
│   │   ├── sankalp_navy_raw.db
│   │   ├── sankalp_navy_gold.db
│   │   ├── sankalp_alerts.db       # Live readiness alerts
│   │   ├── sankalp_automation.db   # Automation task store
│   │   ├── ontology_rules.json     # Active rules (seeded from agents/ontology_rules.json)
│   │   ├── ontology_rag.index      # FAISS vector index for RAG
│   │   └── ontology_rag_meta.json  # RAG metadata (chunk → rule mapping)
│   │
│   └── neo4j_import/               # Bind-mounted into Neo4j container for bulk import
│
├── docs/
│   ├── sankalp_architecture.svg    # System architecture diagram
│   ├── palantir_vs_sankalp_gap_analysis.svg
│   └── todo.md                     # Development task tracker
│
├── tests/
│   └── test_automation_engine.py   # Unit tests for automation engine
│
├── .env                            # Secrets & env vars (never committed — see env.example)
├── env.example                     # Template for .env
├── .dockerignore
├── Dockerfile                      # Python 3.11-slim image
├── docker-compose.yml              # Neo4j + agents services (uses env_file: .env)
├── requirements.txt                # Core Python dependencies
├── requirements-add.txt            # Additional/supplementary dependencies
├── setup.sh                        # One-shot local setup script
├── data-init.sh                    # Initialise data directories
├── data-migrate.py                 # DB migration utility
├── fix-neo4j.py                    # Neo4j connection diagnostics & fix helper
├── neo4j-setup.sh                  # Neo4j APOC & config bootstrap script
├── automation_integration_patch.py # Patch script for automation integration
├── update_ontology_patch.py        # Patch script for ontology rule updates
├── test_altair.py                  # Quick Altair chart smoke test
├── SETUP.md                        # Detailed setup & deployment guide
├── SKILL.md                        # Agent skill / capability reference
├── LICENSE                         # MIT License
└── README.md                       # This file
```

---

## 🔭 Sample Ontology Query (Neo4j Cypher)

```cypher
-- Asset lineage: which crew flew which aircraft on which mission?
MATCH (c:Crew)-[:PARTICIPATED_IN]->(m:Mission)<-[:EXECUTED]-(a:Aircraft)
RETURN a.aircraft_id, a.type, c.name, c.rank, m.mission_type, m.date
ORDER BY m.date DESC
```

---

## 🗺️ Roadmap to Production

| Phase | Feature |
|-------|---------|
| ✅ MVP | 5-agent pipeline, Streamlit UI, Neo4j ontology |
| 🔜 v1.0 | Auth (Keycloak), role-based access (Officer / Admin) |
| 🔜 v1.1 | Airbyte connectors for live defence data sources |
| 🔜 v2.0 | LLM chatbot over ontology (NL → Cypher via LangChain) |
| 🔜 v2.1 | Graph Data Science (community detection, path analysis) |
| 🔜 v3.0 | Multi-branch deployment (Army / Navy / IAF namespaces) |

---

## 🤝 Contributing

PRs welcome. Add agents under `agents/`, follow the naming convention (`<sanskrit_name>.py`).

---

## 📜 License

MIT — Open source for national defence innovation. 🇮🇳
