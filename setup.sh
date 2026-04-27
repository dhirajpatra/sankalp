#!/bin/bash
# Setup script for Sankalp Ontology Platform
# Initializes databases and Neo4j after Docker Compose startup

set -e

echo "🛡️  SANKALP Setup Script"
echo "======================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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

# Initialize SQLite tables from CSV
echo -e "${BLUE}🔵 Running Ganana (Ingestion Agent)...${NC}"
docker exec sankalp-agents python agents/ganana.py
echo -e "${GREEN}✅ SQLite raw tables created${NC}"

# Transform data to Gold store
echo -e "${BLUE}🔵 Running Shodhan (Transformation Agent)...${NC}"
docker exec sankalp-agents python agents/shodhan.py
echo -e "${GREEN}✅ Gold store ready${NC}"

# Build Neo4j ontology
echo -e "${BLUE}🔵 Running Bandhan (Ontology Agent)...${NC}"
docker exec sankalp-agents python agents/bandhan.py
echo -e "${GREEN}✅ Neo4j ontology graph created${NC}"

# Compute readiness scores
echo -e "${BLUE}🔵 Running Bhavishyavani (ML Readiness Agent)...${NC}"
docker exec sankalp-agents python agents/bhavishyavani.py
echo -e "${GREEN}✅ Readiness scores computed${NC}"

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}🎉 Setup Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "📊 Neo4j Browser: http://localhost:7474"
echo "   Username: neo4j"
echo "   Password: ${NEO4J_PASSWORD}"
echo ""
echo "📈 Streamlit Dashboard: http://localhost:8501"
echo ""
