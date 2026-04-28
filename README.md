# 🛡️ SANKALP — Open Source Defence Ontology Platform

> **संकल्प** (Sankalp) — *"A solemn resolve"*  
> An open-source, "Ontology as Digital Twin" for Indian Defence (DRDO / IAF / Army / Navy).

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

---

## 📁 Project Structure

```
sankalp/
├── sankalp_orchestrator.py     # Master orchestrator
├── agents/
│   ├── ganana.py               # Ingestion Agent
│   ├── shodhan.py              # Transformation Agent
│   ├── bandhan.py              # Neo4j Ontology Agent
│   ├── bhavishyavani.py        # ML Readiness Agent
│   └── darshan.py              # Streamlit Dashboard
├── data/raw/
│   ├── aircraft.csv
│   ├── crew.csv
│   └── missions.csv
├── docker-compose.yml
├── requirements.txt
└── README.md
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
