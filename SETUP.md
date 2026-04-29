# 🛡️ SANKALP Setup & Troubleshooting Guide

## Quick Start

### Option 1: Full Docker Setup (Recommended)

```bash
# 1. Clone the repository
git clone <your-repo>
cd sankalp

# 2. Copy environment file
cp .env.example .env
# Edit .env if needed (default password: sankalp123)

# 3. Start Docker services
docker compose up -d

# 4. Wait ~10 seconds, then initialize databases
chmod +x setup.sh
./setup.sh

# 5. Access the dashboard
# Neo4j Browser: http://localhost:7474
# Streamlit Dashboard: http://localhost:8501
```

### Option 2: Local Development (No Docker)

```bash
# 1. Install Python dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Create sample data directory
mkdir -p data/raw

# 3. Initialize databases
chmod +x data-init.sh
./data-init.sh

# 4. Run the orchestrator
python sankalp_orchestrator.py

# 5. Dashboard opens at http://localhost:8501
```

---

## Troubleshooting

### Error: `pandas.errors.DatabaseError: no such table: aircraft`

**Cause:** The CSV files are missing or the Ganana agent hasn't run yet.

**Solution:**
```bash
# Check if CSV files exist
ls -la data/raw/

# If missing, reinitialize with existing CSVs
./data-init.sh

# Or manually run Ganana
python agents/ganana.py
python agents/shodhan.py
```

### Error: `ConnectionRefusedError` when connecting to Neo4j

**Cause:** Neo4j container isn't running or not ready yet.

**Solution:**
```bash
# Check if Neo4j is running
docker ps | grep neo4j

# If not running, start it
docker compose up -d neo4j

# Wait 10 seconds and check logs
docker logs sankalp-neo4j

# Verify connectivity
docker exec sankalp-neo4j cypher-shell -u neo4j_user -p neo4j_password "RETURN 1"
```

### Error: `Streamlit not found`

**Solution:**
```bash
pip install streamlit>=1.28.0
# Or reinstall requirements
pip install -r requirements.txt
```

---

## Available Scripts

### 1. `setup.sh` - Full initialization (Docker)
Initializes everything after `docker compose up`:
- Waits for Neo4j readiness
- Runs Ganana (ingestion)
- Runs Shodhan (transformation)
- Runs Bandhan (ontology build)
- Runs Bhavishyavani (readiness scoring)

```bash
./setup.sh
```

### 2. `neo4j-setup.sh` - Neo4j configuration
Creates indices and constraints for performance:
```bash
./neo4j-setup.sh
```

### 3. `data-init.sh` - SQLite data initialization
Runs Ganana and Shodhan to populate SQLite:
```bash
./data-init.sh
```

---

## Data Files

Sample CSV files are located in `data/raw/`:

- **aircraft.csv** - Aircraft assets (ID, type, squadron, maintenance date, flight hours)
- **crew.csv** - Pilot/crew roster (ID, name, rank, qualified aircraft types)
- **missions.csv** - Mission logs (ID, aircraft, crew, date, mission type, fuel used)

### Adding Your Own Data

Replace the sample CSVs with your own data, following the same schema:

```bash
# Your data files
data/raw/
├── aircraft.csv
├── crew.csv
└── missions.csv
```

Then reinitialize:
```bash
./data-init.sh
```

---

## Database Schema

### SQLite (Raw & Gold stores)
- **aircraft** / **aircraft_gold** - Aircraft asset registry
- **crew** / **crew_gold** - Personnel registry
- **missions** / **missions_gold** - Mission logs
- **aircraft_readiness** - Computed readiness scores

### Neo4j (Ontology Graph)
**Nodes:**
- `:Aircraft` - Asset nodes (aircraft_id, type, squadron, readiness_base_score, flight_hours, final_readiness_score)
- `:Crew` - Personnel nodes (crew_id, name, rank, aircraft_type_qualified)
- `:Mission` - Mission event nodes (mission_id, date, mission_type, fuel_used)

**Relationships:**
- `:Aircraft` -`[:EXECUTED]`-> `:Mission`
- `:Crew` -`[:PARTICIPATED_IN]`-> `:Mission`

### Query Examples

```cypher
-- Find all missions executed by a specific aircraft
MATCH (a:Aircraft {aircraft_id: "AC-001"})-[:EXECUTED]->(m:Mission)
RETURN m.mission_id, m.mission_type, m.date

-- Find crew who participated in strike missions
MATCH (c:Crew)-[:PARTICIPATED_IN]->(m:Mission {mission_type: "Strike"})
RETURN c.name, c.rank, m.mission_id, m.date

-- Find aircraft readiness status
MATCH (a:Aircraft)
RETURN a.aircraft_id, a.type, a.final_readiness_score
ORDER BY a.final_readiness_score DESC
```

---

## Environment Variables

`.env` file:
```
NEO4J_URI=neo4j://localhost
NEO4J_USER=neo4j
NEO4J_PASSWORD=sankalp123
```

**For Docker:** These are injected into the container automatically.

**For Local Dev:** Create a `.env` file or the agents will use defaults.

---

## Common Commands

```bash
# View Neo4j logs
docker logs -f sankalp-neo4j

# View agents logs
docker logs -f sankalp-agents

# Stop everything
docker compose down

# Reset databases (caution!)
docker compose down -v
rm sankalp_raw.db sankalp_gold.db 2>/dev/null
./setup.sh

# Access Neo4j shell directly
docker exec -it sankalp-neo4j cypher-shell -u neo4j -p sankalp123
```

---

## Architecture Reminder

```
Ganana (CSV → SQLite Raw) 
   ↓
Shodhan (Raw → SQLite Gold)
   ↓
Bandhan (Gold → Neo4j Graph)
   ↓
Bhavishyavani (Gold → Readiness Scores)
   ↓
Darshan (Streamlit Dashboard)
```

Each agent is idempotent and can be re-run independently.

---

## Support

For issues or questions:
1. Check the logs: `docker logs sankalp-agents`
2. Verify Neo4j is running: `docker ps`
3. Test CSV data: `python agents/ganana.py`
4. Review this guide's troubleshooting section
