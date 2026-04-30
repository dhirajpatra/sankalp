"""
ontology_tools.py – SANKALP Cypher + similarity tools for Groq function-calling.
Changes:
  - Trimmed text_to_cypher system prompt (~50% shorter, kept only essential rules + 4 examples)
  - max_completion_tokens=200 (Cypher queries are short)
"""

import os
import re
import json
import logging
from neo4j import GraphDatabase
from dotenv import load_dotenv
from config_loader import cfg

load_dotenv(override=True)

NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "password")

logger = logging.getLogger("ontology_tools")


# ── Execute Cypher ────────────────────────────────────────────────────────────

def execute_cypher(cypher_query: str) -> str:
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            data = [r.data() for r in session.run(cypher_query)]
        driver.close()
        return str(data)
    except Exception as e:
        logger.error(f"Cypher error: {e}")
        return f"Error: {e}"


# ── Similarity search ─────────────────────────────────────────────────────────

def similarity_search(query: str) -> str:
    cypher = f"""
    MATCH (n)
    WHERE
        (n:Aircraft   AND (toString(n.aircraft_id) =~ '(?i).*{query}.*'
                       OR  toString(n.squadron)    =~ '(?i).*{query}.*'
                       OR  toString(n.aircraft_type) =~ '(?i).*{query}.*')) OR
        (n:ArmyAsset  AND (toString(n.asset_id)    =~ '(?i).*{query}.*'
                       OR  toString(n.unit)         =~ '(?i).*{query}.*')) OR
        (n:Vessel     AND (toString(n.vessel_id)    =~ '(?i).*{query}.*'
                       OR  toString(n.flotilla)     =~ '(?i).*{query}.*')) OR
        (n:Crew       AND  toString(n.name)         =~ '(?i).*{query}.*')
    RETURN labels(n) AS labels, n
    LIMIT 10
    """
    return execute_cypher(cypher)


# ── Text → Cypher ─────────────────────────────────────────────────────────────

# Trimmed system prompt: schema essentials + 4 examples only (~50% shorter than before)
_CYPHER_SYSTEM = """Output ONLY a valid Cypher query. No markdown, no explanation.

NODES & KEY PROPERTIES:
- Aircraft: aircraft_id, aircraft_type, squadron, flight_hours, operational_status, readiness_base_score, final_readiness_score, last_maintenance_date
- ArmyAsset: asset_id, asset_type, unit, operational_hours, operational_status, readiness_base_score
- Vessel: vessel_id, vessel_type, flotilla, sea_hours, operational_status, readiness_base_score
- Crew: crew_id, name, rank, aircraft_type_qualified
- Mission: mission_id, date, mission_type, fuel_used
- ArmyOperation: op_id, date, op_type, ammo_expended
- Sortie: sortie_id, date, sortie_type, fuel_consumed_tons

RELATIONSHIPS (exact):
(Aircraft)-[:EXECUTED]->(Mission)
(Crew)-[:PARTICIPATED_IN]->(Mission)
(ArmyAsset)-[:DEPLOYED_FOR]->(ArmyOperation)
(ArmyPersonnel)-[:ENGAGED_IN]->(ArmyOperation)
(Vessel)-[:SAILED_FOR]->(Sortie)
(NavyCrew)-[:ASSIGNED_TO]->(Sortie)

RULES:
- squadron is a PROPERTY on Aircraft, not a separate node
- Use operational_status values: 'Operational', 'Watch', 'Critical'
- Single quotes for strings; no invented labels or relationships

EXAMPLES:
Q: Operational aircraft in Flying Bullets squadron
A: MATCH (a:Aircraft) WHERE a.squadron='Flying Bullets' AND a.operational_status='Operational' RETURN a

Q: Which squadron has most operational aircraft?
A: MATCH (a:Aircraft) WHERE a.operational_status='Operational' RETURN a.squadron AS squadron, count(a) AS cnt ORDER BY cnt DESC

Q: Missions for aircraft AC-001
A: MATCH (a:Aircraft {aircraft_id:'AC-001'})-[:EXECUTED]->(m:Mission) RETURN m

Q: Operational navy vessels
A: MATCH (v:Vessel) WHERE v.operational_status='Operational' RETURN v.vessel_id, v.vessel_type, v.flotilla
"""

VALID_LABELS = {"Aircraft", "ArmyAsset", "Vessel", "Crew", "Mission",
                "ArmyOperation", "Sortie", "ArmyPersonnel", "NavyCrew"}


def text_to_cypher(query: str, groq_client) -> str:
    llm_model = os.getenv("MODEL", "llama-3.1-8b-instant").strip("\"'")

    completion = groq_client.chat.completions.create(
        model=llm_model,
        messages=[
            {"role": "system", "content": _CYPHER_SYSTEM},
            {"role": "user",   "content": query},
        ],
        temperature=0.0,
        max_completion_tokens=int(cfg("llm.cypher_tokens")),
    )

    cypher = completion.choices[0].message.content.strip()

    # Strip markdown fences if present
    if cypher.startswith("```"):
        lines = cypher.split("\n")
        cypher = "\n".join(lines[1:-1]).strip()
    if cypher.lower().startswith("cypher"):
        cypher = cypher[6:].strip()

    # Basic validation: reject invented labels
    found_labels = re.findall(r'\((\w+)\s*:', cypher)
    for lbl in found_labels:
        if lbl not in VALID_LABELS and not lbl[0].islower():
            return f"Error: Invalid label '{lbl}'. Please rephrase."

    result = execute_cypher(cypher)
    # Cap result to avoid bloating the next tool-result message
    capped = str(result)[:800]
    return f"Cypher: {cypher}\nResult: {capped}"


# ── Tool schema ───────────────────────────────────────────────────────────────

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "text_to_cypher",
            "description": "Convert a natural language question to Cypher and execute it on Neo4j.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language question."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "similarity_search",
            "description": "Search ontology nodes by keyword/name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term."}
                },
                "required": ["query"],
            },
        },
    },
]
