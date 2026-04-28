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
    # Using a basic regex match on node properties since embeddings aren't set up yet
    cypher_query = f"""
    MATCH (n)
    WHERE any(k IN keys(n) WHERE toString(n[k]) =~ '(?i).*{query}.*')
    RETURN labels(n) AS labels, n
    LIMIT 10
    """
    return execute_cypher(cypher_query)

def text_to_cypher(query: str, groq_client):
    """Generates a Cypher query from natural language using Groq, and executes it."""
    system_prompt = """You are a Neo4j Cypher expert. Given a natural language query, you must output ONLY a valid Cypher query that answers the question.
Do not output any markdown formatting, no explanations, no backticks. Only the raw Cypher string.

Ontology Schema:
- (a:Aircraft {aircraft_id, aircraft_type, squadron, base_location, flight_hours, operational_status, readiness_base_score})
  * Note: 'base_location' contains the state and border region (e.g. "Punjab (Northern Border)"). Use it for geography questions.
  * Note: To check if an aircraft is "operational" or "ready", you MUST use the condition: `a.operational_status = 'Operational'`.
- (aa:ArmyAsset {asset_id, asset_type, unit, operational_hours, operational_status, readiness_base_score})
  * Note: To check if an asset is "operational", use: `aa.operational_status = 'Operational'`.
- (v:Vessel {vessel_id, vessel_type, flotilla, sea_hours, operational_status, readiness_base_score})
  * Note: To check if a vessel is "operational" or "seaworthy", use: `v.operational_status = 'Operational'`.
- (c:Crew {crew_id, name, rank}), (nc:NavyCrew), (ap:ArmyPersonnel)
- (m:Mission {mission_id, date, mission_type}), (s:Sortie), (ao:ArmyOperation)

Relationships:
- (Aircraft)-[:EXECUTED]->(Mission)
- (Crew)-[:PARTICIPATED_IN]->(Mission)
- (ArmyAsset)-[:DEPLOYED_FOR]->(ArmyOperation)
- (ArmyPersonnel)-[:ENGAGED_IN]->(ArmyOperation)
- (Vessel)-[:SAILED_FOR]->(Sortie)
- (NavyCrew)-[:ASSIGNED_TO]->(Sortie)

CRITICAL RULES:
1. DO NOT chain multiple nodes (e.g. Aircraft->Mission->Crew->Sortie->Vessel) unless explicitly asked to find a relationship path. Keep queries simple.
2. If asked about Aircraft readiness, ONLY use `MATCH (a:Aircraft)`.
3. If asked about Army readiness, ONLY use `MATCH (aa:ArmyAsset)`.
4. If asked about Navy readiness, ONLY use `MATCH (v:Vessel)`.
5. DO NOT hallucinate properties. For example, Vessels do NOT have a `base_location`.

Examples:
Q: How many operational aircraft are at the Northern Border?
A: MATCH (a:Aircraft) WHERE a.base_location CONTAINS 'Northern Border' AND a.operational_status = 'Operational' RETURN count(a)

Q: Are there enough army assets ready in the eastern border?
A: MATCH (aa:ArmyAsset) WHERE aa.unit CONTAINS 'Eastern' AND aa.operational_status = 'Operational' RETURN count(aa)
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
    
    # Clean up markdown if the LLM hallucinated it
    if generated_cypher.startswith("```"):
        lines = generated_cypher.split("\n")
        generated_cypher = "\n".join(lines[1:-1])
    if generated_cypher.startswith("cypher"):
        generated_cypher = generated_cypher[6:].strip()
        
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
