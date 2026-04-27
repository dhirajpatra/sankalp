#!/bin/bash
# Neo4j ontology setup script
# Creates nodes and relationships in Neo4j after database startup

set -e

NEO4J_PASSWORD="${NEO4J_PASSWORD:-sankalp123}"
NEO4J_HOST="localhost"
NEO4J_PORT="7687"

echo "🛡️  SANKALP Neo4j Setup"
echo "======================"

# Wait for Neo4j to be ready
echo "⏳ Waiting for Neo4j to be ready..."
for i in {1..30}; do
    if cypher-shell -a "bolt://${NEO4J_HOST}:${NEO4J_PORT}" -u neo4j -p "${NEO4J_PASSWORD}" "RETURN 1" >/dev/null 2>&1; then
        echo "✅ Neo4j is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Neo4j failed to start after 60 seconds"
        exit 1
    fi
    echo "  Attempt $i/30..."
    sleep 2
done

echo ""
echo "🔧 Creating Neo4j ontology structure..."

# Create indices for performance
cypher-shell -a "bolt://${NEO4J_HOST}:${NEO4J_PORT}" -u neo4j -p "${NEO4J_PASSWORD}" <<EOF
CREATE INDEX aircraft_id_index IF NOT EXISTS FOR (a:Aircraft) ON (a.aircraft_id);
CREATE INDEX crew_id_index IF NOT EXISTS FOR (c:Crew) ON (c.crew_id);
CREATE INDEX mission_id_index IF NOT EXISTS FOR (m:Mission) ON (m.mission_id);
EOF

echo "✅ Indices created"

# Create constraints for data integrity
echo "Creating constraints..."
cypher-shell -a "bolt://${NEO4J_HOST}:${NEO4J_PORT}" -u neo4j -p "${NEO4J_PASSWORD}" <<EOF
CREATE CONSTRAINT aircraft_id_unique IF NOT EXISTS FOR (a:Aircraft) REQUIRE a.aircraft_id IS UNIQUE;
CREATE CONSTRAINT crew_id_unique IF NOT EXISTS FOR (c:Crew) REQUIRE c.crew_id IS UNIQUE;
CREATE CONSTRAINT mission_id_unique IF NOT EXISTS FOR (m:Mission) REQUIRE m.mission_id IS UNIQUE;
EOF

echo "✅ Constraints created"

# Clear existing graph (optional - remove comment to enable)
# cypher-shell -a "bolt://${NEO4J_HOST}:${NEO4J_PORT}" -u neo4j -p "${NEO4J_PASSWORD}" "MATCH (n) DETACH DELETE n"

echo ""
echo "✅ Neo4j ontology setup complete!"
echo ""
echo "📊 Neo4j Browser: http://localhost:7474"
echo "   Username: neo4j"
echo "   Password: ${NEO4J_PASSWORD}"
echo ""
