#!/bin/bash
# Setup script for Sankalp Ontology Platform
# Initializes all branch databases and Neo4j after Docker Compose startup

set -e

echo "🛡️  SANKALP Setup Script"
echo "======================="

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Wait for Neo4j to be ready
echo -e "${BLUE}⏳ Waiting for Neo4j to be ready...${NC}"
for i in {1..30}; do
    if docker exec sankalp-neo4j cypher-shell -u neo4j -p "${NEO4J_PASSWORD}" "RETURN 1" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Neo4j is ready!${NC}"
        break
    fi
    echo "  Attempt $i/30..."
    sleep 2
done

# ── IAF Pipeline ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}✈️  IAF Pipeline${NC}"
echo -e "${BLUE}🔵 Running Ganana (IAF Ingestion)...${NC}"
docker exec sankalp-agents python agents/ganana.py
echo -e "${GREEN}✅ IAF raw tables created${NC}"

echo -e "${BLUE}🔵 Running Shodhan (IAF Transformation)...${NC}"
docker exec sankalp-agents python agents/shodhan.py
echo -e "${GREEN}✅ IAF Gold store ready${NC}"

echo -e "${BLUE}🔵 Running Bandhan (IAF Neo4j Ontology)...${NC}"
docker exec sankalp-agents python agents/bandhan.py
echo -e "${GREEN}✅ IAF Neo4j ontology graph created${NC}"

echo -e "${BLUE}🔵 Running Bhavishyavani (IAF ML Readiness)...${NC}"
docker exec sankalp-agents python agents/bhavishyavani.py
echo -e "${GREEN}✅ IAF Readiness scores computed${NC}"

# ── Army Pipeline ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}🪖  Army Pipeline${NC}"
echo -e "${BLUE}🔵 Running Ganana-Army (Ingestion)...${NC}"
docker exec sankalp-agents python agents/ganana_army.py
echo -e "${GREEN}✅ Army raw tables created${NC}"

echo -e "${BLUE}🔵 Running Shodhan-Army (Transformation)...${NC}"
docker exec sankalp-agents python agents/shodhan_army.py
echo -e "${GREEN}✅ Army Gold store ready${NC}"

echo -e "${BLUE}🔵 Running Bandhan-Army (Neo4j Ontology)...${NC}"
docker exec sankalp-agents python agents/bandhan_army.py
echo -e "${GREEN}✅ Army Neo4j ontology graph created${NC}"

# ── Navy Pipeline ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}⚓  Navy Pipeline${NC}"
echo -e "${BLUE}🔵 Running Ganana-Navy (Ingestion)...${NC}"
docker exec sankalp-agents python agents/ganana_navy.py
echo -e "${GREEN}✅ Navy raw tables created${NC}"

echo -e "${BLUE}🔵 Running Shodhan-Navy (Transformation)...${NC}"
docker exec sankalp-agents python agents/shodhan_navy.py
echo -e "${GREEN}✅ Navy Gold store ready${NC}"

echo -e "${BLUE}🔵 Running Bandhan-Navy (Neo4j Ontology)...${NC}"
docker exec sankalp-agents python agents/bandhan_navy.py
echo -e "${GREEN}✅ Navy Neo4j ontology graph created${NC}"

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}🎉 Full Setup Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "📊 Neo4j Browser: http://localhost:7474"
echo "   Username: neo4j"
echo "   Password: ${NEO4J_PASSWORD}"
echo ""
echo "📈 Streamlit Dashboard: http://localhost:8501"
echo ""
