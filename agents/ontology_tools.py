import os
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(override=True)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "password")

logger = logging.getLogger("ontology_tools")

def execute_cypher(cypher_query: str):
    """Executes a Cypher query on the Neo4j database and returns the result."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            result = session.run(cypher_query)
            data = [r.data() for r in result]
        driver.close()
        return str(data)
    except Exception as e:
        logger.error(f"Cypher Error: {e}")
        return f"Error executing Cypher: {e}"

def similarity_search(query: str):
    """Searches the ontology for nodes similar to the query."""
    cypher_query = f"""
    MATCH (n)
    WHERE 
        (n:Aircraft AND (toString(n.aircraft_id) =~ '(?i).*{query}.*' OR toString(n.squadron) =~ '(?i).*{query}.*' OR toString(n.aircraft_type) =~ '(?i).*{query}.*')) OR
        (n:ArmyAsset AND (toString(n.asset_id) =~ '(?i).*{query}.*' OR toString(n.unit) =~ '(?i).*{query}.*')) OR
        (n:Vessel AND (toString(n.vessel_id) =~ '(?i).*{query}.*' OR toString(n.flotilla) =~ '(?i).*{query}.*')) OR
        (n:Crew AND toString(n.name) =~ '(?i).*{query}.*')
    RETURN labels(n) AS labels, n
    LIMIT 10
    """
    return execute_cypher(cypher_query)

def text_to_cypher(query: str, groq_client):
    """Generates a Cypher query from natural language using Groq, and executes it."""
    system_prompt = """You are a Neo4j Cypher expert. Given a natural language query, you must output ONLY a valid Cypher query that answers the question.
Do not output any markdown formatting, no explanations, no backticks. Only the raw Cypher string.

ONTOLOGY SCHEMA (EXACT - DO NOT INVENT):

Aircraft node properties:
- aircraft_id (string, e.g., 'AC-001')
- aircraft_type (string, e.g., 'HAL Tejas', 'Su-30MKI')
- squadron (string, e.g., 'Flying Bullets', 'Winged Arrows')
- base_location (string, e.g., 'Ambala AFS')
- flight_hours (integer)
- operational_status (string: 'Operational', 'Watch', 'Critical', 'MAINTENANCE_REQUIRED')
- readiness_base_score (integer, 0-100)
- final_readiness_score (integer, 0-100)
- mission_ready (boolean, true/false)
- last_maintenance_date (date, format 'YYYY-MM-DD')

ArmyAsset node properties:
- asset_id, asset_type, unit, operational_hours, operational_status, readiness_base_score, mission_ready

Vessel node properties:
- vessel_id, vessel_type, flotilla, sea_hours, operational_status, readiness_base_score, mission_ready

Crew node properties:
- crew_id, name, rank, aircraft_type_qualified

Mission node properties:
- mission_id, date, mission_type, fuel_used

RELATIONSHIPS (USE EXACTLY THESE NAMES):
- (Aircraft)-[:EXECUTED]->(Mission)
- (Crew)-[:PARTICIPATED_IN]->(Mission)
- (ArmyAsset)-[:DEPLOYED_FOR]->(ArmyOperation)
- (Vessel)-[:SAILED_FOR]->(Sortie)

CRITICAL RULES:
1. Squadron is a PROPERTY on Aircraft. There is NO separate 'Squadron' node.
2. Use 'operational_status' not 'status'
3. Use single quotes for string values: 'Operational'
4. NEVER invent relationships like HAS_AIRCRAFT or IS_READY
5. For boolean checks: mission_ready = true (no quotes)

EXAMPLES:
Q: Show all OPERATIONAL aircraft in Flying Bullets squadron
A: MATCH (a:Aircraft) WHERE a.squadron = 'Flying Bullets' AND a.operational_status = 'Operational' RETURN a

Q: How many operational aircraft in Flying Bullets squadron?
A: MATCH (a:Aircraft) WHERE a.squadron = 'Flying Bullets' AND a.operational_status = 'Operational' RETURN count(a)

Q: Show all mission ready aircraft
A: MATCH (a:Aircraft) WHERE a.mission_ready = true RETURN a.aircraft_id, a.aircraft_type, a.squadron

Q: Which squadron has the most operational aircraft?
A: MATCH (a:Aircraft) WHERE a.operational_status = 'Operational' RETURN a.squadron AS squadron, count(a) AS count ORDER BY count DESC

Q: Show aircraft that need maintenance (not operational)
A: MATCH (a:Aircraft) WHERE a.operational_status <> 'Operational' RETURN a.aircraft_id, a.operational_status, a.final_readiness_score

Q: Show all missions for aircraft AC-001
A: MATCH (a:Aircraft {aircraft_id: 'AC-001'})-[:EXECUTED]->(m:Mission) RETURN m

Q: Count all operational Army assets
A: MATCH (aa:ArmyAsset) WHERE aa.operational_status = 'Operational' RETURN count(aa)

Q: Show vessels that are mission ready
A: MATCH (v:Vessel) WHERE v.mission_ready = true RETURN v.vessel_id, v.vessel_type, v.flotilla
"""
    
    llm_model = os.getenv("MODEL", "llama-3.1-8b-instant").strip('"\'')
    completion = groq_client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        temperature=0.0,
        max_completion_tokens=500,
    )
    
    generated_cypher = completion.choices[0].message.content.strip()
    
    # Clean up markdown
    if generated_cypher.startswith("```"):
        lines = generated_cypher.split("\n")
        generated_cypher = "\n".join(lines[1:-1])
    if generated_cypher.startswith("cypher"):
        generated_cypher = generated_cypher[6:].strip()
    
    # VALIDATION: Reject queries with invented relationships
    invalid_patterns = ["HAS_AIRCRAFT", "HAS_ARMY", "HAS_VESSEL", "IS_READY", "IS_OPERATIONAL", "Squadron", "status ="]
    for pattern in invalid_patterns:
        if pattern in generated_cypher and "WHERE" in generated_cypher:
            # Try to auto-correct or return error
            return f"Error: Invalid syntax detected. Please rephrase. (Contains '{pattern}')"
    
    result = execute_cypher(generated_cypher)
    return f"Executed Cypher: {generated_cypher}\nResult: {result}"

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "text_to_cypher",
            "description": "Convert a natural language question into a Cypher query and execute it on the Neo4j database to get exact numbers or relationships.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The natural language question to translate to Cypher."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "similarity_search",
            "description": "Search the ontology for nodes that contain text similar to the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term or keyword."
                    }
                },
                "required": ["query"]
            }
        }
    }
]
