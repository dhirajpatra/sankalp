---
name: sankalp-ontology-platform
description: >
  Production multi-agent Defence Ontology Platform named Sankalp —
  "Ontology as a Digital Twin" for Indian Defence (DRDO / IAF / Army / Navy).
  Built with Python 3.10+, Neo4j 5.x, Streamlit 1.35+, Groq LLM (Llama 3.1),
  FAISS RAG, and FastMCP. Covers a full three-branch (IAF, Army, Navy)
  ETL-to-dashboard pipeline with live readiness monitoring, threat intelligence,
  mission planning, geospatial visualisation, and Claude Desktop integration.
---

# Skill: Sankalp — Multi-Agent Defence Ontology Platform

## Purpose

Guide the development, extension, and maintenance of **Sankalp**, a
production-grade, open-source "Ontology as Digital Twin" platform for Indian
defence use cases. The system ingests CSV data from three service branches
(IAF, Army, Navy), transforms it through a multi-agent ETL pipeline into a
Neo4j knowledge graph, computes AI readiness scores, and surfaces everything
through a Streamlit dashboard with live alerts, threat intelligence, mission
planning, and Claude Desktop integration via MCP.

---

## Agent Roster

### Core ETL Agents (run by `sankalp_orchestrator.py`)

| # | Agent | Sanskrit | File(s) | Role |
|---|-------|----------|---------|------|
| 1 | **Ganana** | गणना – Counting | `ganana.py`, `ganana_army.py`, `ganana_navy.py` | Reads CSVs from `data/raw/` → writes raw SQLite stores per branch |
| 2 | **Shodhan** | शोधन – Purification | `shodhan.py`, `shodhan_army.py`, `shodhan_navy.py` | Cleans & enriches raw stores → Gold-quality SQLite tables |
| 3 | **Bandhan** | बंधन – Bond | `bandhan.py`, `bandhan_army.py`, `bandhan_navy.py` | Merges Gold tables → Neo4j knowledge graph (nodes + relationships) |
| 4 | **Bhavishyavani** | भविष्यवाणी – Forecast | `bhavishyavani.py` | Computes `final_readiness_score` via ML formula → writes back to Neo4j |
| 5 | **Darshan** | दर्शन – View | `darshan.py` + tab modules | Streamlit command dashboard; surfaces all branches and advanced modules |

### Specialist / Advanced Agents

| Agent | Sanskrit | File(s) | Role |
|-------|----------|---------|------|
| **Ontology Engine** | — | `ontology_engine.py`, `ontology_tools.py`, `ontology_rag.py` | Natural Language → Cypher via Groq LLM (tool-calling) + FAISS RAG over doctrine rules |
| **Readiness Monitor** | — | `readiness_monitor.py` | Background daemon thread; polls Neo4j every `alerts.monitor_poll_secs` seconds, writes tier-change alerts to SQLite |
| **Automation Engine** | — | `automation_engine.py` | Schedules & executes automated defence actions; persisted to `sankalp_automation.db` |
| **Threat Engine** | — | `threat_engine.py` | Evaluates 6 pre-loaded threat scenarios; produces `ThreatAssessment` with verdict, coverage %, gaps, risks, recommendations |
| **Yojana** | योजना – Plan | `yojana.py` | Mission Planning Agent; scores assets on readiness + type suitability and crew on rank + qualification; greedy pairing; 20+ mission types across all 3 branches |
| **Geo Map** | — | `darshan_geo_map.py` | Folium map of India; 25 squadron/unit/flotilla GPS locations; colour-coded by readiness; threat zone overlays |

---

## Orchestrator Flow

```
sankalp_orchestrator.py
│
├── IAF Pipeline
│   ├── Ganana     → data/processed/sankalp_raw.db
│   ├── Shodhan    → data/processed/sankalp_gold.db
│   ├── Bandhan    → Neo4j (:Aircraft, :Crew, :Mission)
│   └── Bhavishyavani → Neo4j (final_readiness_score on :Aircraft)
│
├── Army Pipeline
│   ├── Ganana     → data/processed/sankalp_army_raw.db
│   ├── Shodhan    → data/processed/sankalp_army_gold.db
│   └── Bandhan    → Neo4j (:ArmyAsset, :ArmyPersonnel, :ArmyOperation)
│
├── Navy Pipeline
│   ├── Ganana     → data/processed/sankalp_navy_raw.db
│   ├── Shodhan    → data/processed/sankalp_navy_gold.db
│   └── Bandhan    → Neo4j (:Vessel, :NavyCrew, :Sortie)
│
├── Readiness Monitor  → background daemon thread starts
│
└── Darshan  → streamlit run agents/darshan.py --server.port 8501
```

All values (ports, paths, thresholds, LLM settings) are read from `config.yml`
via `config_loader.cfg()`. No hardcoded constants in agent code.

---

## Configuration System

Central config: **`config.yml`** — read via `config_loader.py`.

```python
from config_loader import cfg

db_path = cfg("paths.iaf_gold_db")          # "data/processed/sankalp_gold.db"
poll    = cfg("alerts.monitor_poll_secs")    # 60
model   = cfg("llm.model")                  # "llama-3.1-8b-instant"
```

Environment variables override any `config.yml` value at runtime.

| Key Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq LLM inference |
| `NEO4J_PASSWORD` | Neo4j auth |
| `NEO4J_URI` | Bolt URI (default: `bolt://localhost:7687`) |
| `MODEL` | LLM model override |

---

## Neo4j Graph Schema

### Node Labels

| Label | Branch | Key Properties |
|-------|--------|----------------|
| `:Aircraft` | IAF | `aircraft_id`, `type`, `squadron`, `flight_hours`, `final_readiness_score` |
| `:Crew` | IAF | `crew_id`, `name`, `rank`, `aircraft_type_qualified` |
| `:Mission` | IAF | `mission_id`, `date`, `mission_type`, `fuel_used` |
| `:ArmyAsset` | Army | `asset_id`, `asset_type`, `unit`, `final_readiness_score` |
| `:ArmyPersonnel` | Army | `personnel_id`, `name`, `rank` |
| `:ArmyOperation` | Army | `op_id`, `date`, `op_type`, `ammo_expended` |
| `:Vessel` | Navy | `vessel_id`, `vessel_type`, `flotilla`, `final_readiness_score` |
| `:NavyCrew` | Navy | `crew_id`, `name`, `rank` |
| `:Sortie` | Navy | `sortie_id`, `date`, `sortie_type`, `fuel_consumed_tons` |

### Relationships

```cypher
(Aircraft)-[:EXECUTED]->(Mission)
(Crew)-[:PARTICIPATED_IN]->(Mission)
(ArmyAsset)-[:DEPLOYED_FOR]->(ArmyOperation)
(ArmyPersonnel)-[:ENGAGED_IN]->(ArmyOperation)
(Vessel)-[:SAILED_FOR]->(Sortie)
(NavyCrew)-[:ASSIGNED_TO]->(Sortie)
```

### Sample Query — Asset Lineage

```cypher
// Which crew flew which aircraft on which mission?
MATCH (c:Crew)-[:PARTICIPATED_IN]->(m:Mission)<-[:EXECUTED]-(a:Aircraft)
RETURN a.aircraft_id, a.type, c.name, c.rank, m.mission_type, m.date
ORDER BY m.date DESC
LIMIT 20
```

---

## Readiness Scoring Formula

Used by **Bhavishyavani** and all branch readiness modules:

```
final_readiness_score =
    (readiness_base_score × weight_base)
  - (days_since_last_mission × weight_staleness)
  + (mission_count × weight_currency)
```

Default weights (all branches, from `config.yml`):

| Weight | Value |
|--------|-------|
| `weight_base` | `0.6` |
| `weight_staleness` | `0.05` per day |
| `weight_currency` | `0.2` per mission |

Operational threshold (default `5`, configurable via admin UI or `config.yml`):
- **≥ threshold** → Operational ✅
- **threshold − watch_band … threshold** → Watch ⚠️
- **< threshold − watch_band** → Critical 🔴

---

## Ontology Engine (AI Query Interface)

Natural language → Cypher via Groq tool-calling:

```
User: "Which IAF aircraft have readiness below 40%?"
  │
  ├── ontology_rag.py  →  FAISS retrieves top-2 relevant doctrine rules
  ├── ontology_engine.py  →  Groq Llama-3.1 selects & calls Cypher tool
  ├── ontology_tools.py  →  executes Cypher against live Neo4j
  └── result returned as structured JSON + LLM explanation
```

Rules are stored in `data/processed/ontology_rules.json` and embedded via
`sentence-transformers/all-MiniLM-L6-v2`.

---

## Live Alerts Architecture

```
Neo4j (live graph)
      ↓  polls every 60s  [config: alerts.monitor_poll_secs]
readiness_monitor.py  (background daemon thread)
      ↓  on tier change  (SUPERIOR → ADEQUATE → INSUFFICIENT)
sankalp_alerts.db  (SQLite: alerts + fleet_snapshots tables)
      ↓  reads
Darshan → 🔔 Live Alerts panel  (auto-refreshes every 30s)
```

Tier transitions recorded as `degraded` (higher→lower) or `improved` (lower→higher).

---

## Threat Intelligence Engine

Six pre-loaded scenarios in `agents/threat_engine.py`:

| Scenario key | Description |
|---|---|
| `northern_infiltration` | Air superiority required on northern border |
| `western_border_strike` | Multi-asset western sector response |
| `two_front_war` | Simultaneous northern + western engagement |
| `southern_sea_threat` | Navy blockade + IAF recon |
| `cyber_plus_border` | Hybrid cyber + physical border threat |
| `island_territory_dispute` | Andaman & Nicobar maritime response |

Each produces a `ThreatAssessment` with:
- `verdict`: CAPABLE / MARGINAL / INSUFFICIENT
- `coverage_pct`: fleet coverage percentage
- `branch_metrics`: per-branch operational counts
- `gaps`: unmet requirements
- `risks` and `recommendations`

Add custom scenarios: `engine.add_scenario(key, ThreatScenario(...))`

---

## Mission Planning Agent — Yojana

`MissionPlanner` in `agents/yojana.py`:

1. **Asset scoring** — readiness score × type-suitability weight for the requested mission type
2. **Crew scoring** — rank seniority points + qualification match bonus
3. **Greedy pairing** — best-scored asset + best-qualified crew → ranked `MissionPlan` list
4. Supports all 3 branches and 20+ mission types (Strike, Patrol, CAS, ASW, Border Vigil, …)

Each `MissionPlan` returns: `asset_id`, `crew_id`, `confidence`, `readiness_score`,
`rationale`, `warnings`, branch label.

---

## MCP Server — Claude Desktop Integration

Two transports, one code file (`mcp_server.py`):

```bash
# stdio — Claude Desktop
python mcp_server.py

# HTTP/SSE — URL-based connectors
python mcp_server.py --http --port 8080
```

### Exposed MCP Tools (8 total)

| Tool | Description |
|------|-------------|
| `get_fleet_readiness` | Readiness summary (total / operational / watch / critical / avg %) for all branches |
| `get_critical_assets` | Assets below readiness threshold; filter by branch |
| `evaluate_doctrine` | Evaluate a doctrine action by name → SUPERIOR / ADEQUATE / INSUFFICIENT |
| `list_doctrine_rules` | All rules with branch minimums |
| `get_mission_history` | Recent missions / operations / sorties across branches |
| `get_top_ready_assets` | Top-N assets by readiness per branch |
| `assess_threat_scenario` | Assess current fleet against a named threat scenario |
| `plan_mission` | Recommend optimal asset-crew pairings for a mission type |

### Claude Desktop Config

Edit `~/.config/claude/claude_desktop_config.json` (Linux/Mac) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "sankalp": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/sankalp-ontology-platform/mcp_server.py"]
    }
  }
}
```

---

## Darshan Dashboard Tabs

| Tab | File | Content |
|-----|------|---------|
| IAF | `darshan_iaf_branch.py` | Aircraft metrics, readiness chart, mission log, log new mission |
| Army | `darshan_army_branch.py` | Asset metrics, ops log, log new operation |
| Navy | `darshan_navy_branch.py` | Vessel metrics, sortie log, log new sortie |
| 🔔 Live Alerts | `darshan_alerts_panel.py` | Readiness timeline, operational count chart, event log |
| 🤖 Ontology Engine | `render_ontology_engine_patch.py` | NL→Cypher chat interface |
| ⚡ Automation | `darshan_automation_tab.py` | Automated action queue and controls |
| ☠️ Threats | `darshan_threat_tab.py` | Threat scenario overview, deep-dive, custom builder |
| 📋 Yojana | `darshan_yojana_tab.py` | Mission plan cards, comparison table |
| 🗺️ Map | `darshan_geo_map.py` | Folium map — 25 locations, branch filters, threat overlays |
| 📥 Admin Import | `admin_import.py` | Manual CSV upload & re-ingestion |

---

## Tech Stack

```yaml
Language:        Python 3.10+
Graph DB:        Neo4j 5.x  (Community Edition or AuraDB)
Graph Driver:    neo4j-python-driver >= 5.0
Dashboard:       Streamlit >= 1.35
LLM:             Groq  (llama-3.1-8b-instant by default)
RAG:             FAISS-cpu >= 1.8  +  sentence-transformers >= 2.7
ML:              scikit-learn >= 1.3
Data:            pandas >= 2.0  +  SQLite3
Scheduler:       APScheduler >= 3.10  +  streamlit-autorefresh
Geo:             folium >= 0.15  +  streamlit-folium >= 0.18
Charts:          Altair >= 5.0
MCP:             fastmcp (mcp >= 1.0) + starlette + uvicorn
Containers:      Docker + Docker Compose (Neo4j 5 + APOC)
```

---

## Running Locally

```bash
# 1. Clone & configure
git clone https://github.com/<org>/sankalp-ontology-platform.git
cd sankalp-ontology-platform
cp .env.example .env       # set GROQ_API_KEY and NEO4J_PASSWORD
pip install -r requirements.txt
mkdir -p data/neo4j_import

# 2. Start Neo4j
docker compose up -d

# 3. Run full pipeline + dashboard
python sankalp_orchestrator.py

# 4. (Optional) MCP server for Claude Desktop
python mcp_server.py

# 5. (Optional) MCP over HTTP
python mcp_server.py --http --port 8080
# or:
uvicorn mcp_server_http:app --port 8080
```

| Service | URL |
|---------|-----|
| Streamlit Dashboard | http://localhost:8501 |
| Neo4j Browser | http://localhost:7474 |
| MCP HTTP endpoint | http://localhost:8080/sse |

---

## Adding a New Agent

1. Create `agents/<sanskrit_name>.py` with a clear `run()` or equivalent entry function.
2. If it needs a dashboard tab, create `agents/darshan_<feature>_tab.py` and register it in `darshan.py`.
3. Add any new paths or config values to `config.yml`.
4. If exposing via MCP, add a `@mcp.tool` function in `mcp_server.py`.
5. Update `README.md` and this `SKILL.md`.

---

## Evaluation Criteria

| Criterion | Verification |
|-----------|-------------|
| Full ETL pipeline | `python sankalp_orchestrator.py` completes without error; Neo4j has nodes for all 3 branches |
| Readiness scores | `MATCH (a:Aircraft) RETURN a.final_readiness_score LIMIT 5` → non-null values |
| Live alerts | Navigate to 🔔 Live Alerts in Darshan; timeline chart populated |
| Ontology Engine | Ask "How many IAF aircraft are operational?" in the chat tab → gets Cypher-backed answer |
| MCP tools | `python mcp_server.py` starts; Claude Desktop can call `get_fleet_readiness` |
| Offline resilience | Stop Neo4j → orchestrator completes; Darshan falls back to SQLite |
| Config-driven | Change `alerts.monitor_poll_secs` in `config.yml` → monitor picks it up on next restart; no code change needed |
