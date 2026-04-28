import json
import os
import logging
import requests
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger("ontology_engine")

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sankalp123")

RULES_FILE = "data/processed/ontology_rules.json"

def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

def load_rules():
    if not os.path.exists(RULES_FILE):
        return {
            "protect northern border from any type of infiltration": {
                "iaf_min_operational": 5,
                "army_min_operational": 10,
                "navy_min_operational": 0,
                "description": "Requires a joint strike force of IAF jets for air superiority and Army assets for ground assault."
            },
            "attack terrorist infiltation from our southern sea borders": {
                "iaf_min_operational": 2,
                "army_min_operational": 0,
                "navy_min_operational": 8,
                "description": "Requires fleet of Navy vessels for blockade and IAF recon support."
            }
        }
    with open(RULES_FILE, "r") as f:
        return json.load(f)

def save_rules(rules):
    os.makedirs("data/processed", exist_ok=True)
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=4)

def get_current_capabilities():
    """Queries Neo4j to get current operational counts across all branches."""
    driver = get_neo4j_driver()
    caps = {"iaf_op": 0, "army_op": 0, "navy_op": 0}
    with driver.session() as session:
        # IAF
        res = session.run("MATCH (a:Aircraft) WHERE coalesce(a.operational_status, '') = 'OPERATIONAL' OR coalesce(a.readiness_base_score, 100 - (toFloat(coalesce(a.flight_hours, 0)) * 0.8)) >= 60 RETURN COUNT(a)")
        caps["iaf_op"] = res.single()[0]
        # Army
        res = session.run("MATCH (a:ArmyAsset) WHERE coalesce(a.operational_status, '') = 'OPERATIONAL' OR coalesce(a.readiness_base_score, 100 - (toFloat(coalesce(a.operational_hours, 0)) * 0.5)) >= 60 RETURN COUNT(a)")
        caps["army_op"] = res.single()[0]
        # Navy
        res = session.run("MATCH (v:Vessel) WHERE coalesce(v.operational_status, '') = 'OPERATIONAL' OR coalesce(v.readiness_base_score, 100 - (toFloat(coalesce(v.sea_hours, 0)) * 0.2)) >= 60 RETURN COUNT(v)")
        caps["navy_op"] = res.single()[0]
    driver.close()
    return caps

def evaluate_action(action_name):
    rules = load_rules()
    if action_name not in rules:
        return False, f"Action '{action_name}' not defined in ontology logic."
    
    rule = rules[action_name]
    caps = get_current_capabilities()
    
    reasons = []
    can_execute = True
    
    if caps["iaf_op"] < rule["iaf_min_operational"]:
        can_execute = False
        reasons.append(f"❌ **IAF**: Need {rule['iaf_min_operational']} operational aircraft, but only have {caps['iaf_op']}.")
    else:
        reasons.append(f"✅ **IAF**: Have {caps['iaf_op']} operational aircraft (requires {rule['iaf_min_operational']}).")
        
    if caps["army_op"] < rule["army_min_operational"]:
        can_execute = False
        reasons.append(f"❌ **Army**: Need {rule['army_min_operational']} operational assets, but only have {caps['army_op']}.")
    else:
        reasons.append(f"✅ **Army**: Have {caps['army_op']} operational assets (requires {rule['army_min_operational']}).")
        
    if caps["navy_op"] < rule["navy_min_operational"]:
        can_execute = False
        reasons.append(f"❌ **Navy**: Need {rule['navy_min_operational']} seaworthy vessels, but only have {caps['navy_op']}.")
    else:
        reasons.append(f"✅ **Navy**: Have {caps['navy_op']} seaworthy vessels (requires {rule['navy_min_operational']}).")
        
    return can_execute, reasons

def ask_llm_groq(query: str) -> str:
    """Uses Groq API to answer a natural language question based on ontology state."""
    api_key = (os.getenv("GROQ_LLM_API_KEY") or os.getenv("LLM_API_KEY", "")).strip('"\'')
    if not api_key or api_key == "fdsfdfas":
        return "⚠️ Error: Valid GROQ_LLM_API_KEY or LLM_API_KEY not found in .env file."

    llm_model = os.getenv("MODEL", "llama-3.1-8b-instant").strip('"\'')

    # Get live context from Neo4j
    caps = get_current_capabilities()
    rules = load_rules()
    
    system_prompt = (
        "You are 'Sankalp-AI', the master defence intelligence ontology AI for the Indian Armed Forces. "
        "You must answer operational questions concisely and decisively like a high-ranking military commander. "
        "Use the provided context to answer the user's operational question. If the numbers don't support the action, clearly state why.\n\n"
        f"CURRENT FLEET CAPABILITIES (Live Neo4j Digital Twin Data):\n"
        f"- IAF: {caps['iaf_op']} Operational Aircraft\n"
        f"- Army: {caps['army_op']} Operational Assets\n"
        f"- Navy: {caps['navy_op']} Seaworthy Vessels\n\n"
        f"PRE-DEFINED DOCTRINE RULES:\n{json.dumps(rules, indent=2)}\n"
    )

    try:
        from groq import Groq
        from agents.ontology_tools import tools_schema, text_to_cypher, similarity_search
        client = Groq(api_key=api_key)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        # Step 1: Call Groq with available tools
        completion = client.chat.completions.create(
            model=llm_model,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
            temperature=0.2,
            max_completion_tokens=2048,
        )
        
        response_message = completion.choices[0].message
        
        # Step 2: Check if Groq decided to use a tool
        if response_message.tool_calls:
            messages.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    } for tool_call in response_message.tool_calls
                ]
            })
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "text_to_cypher":
                    tool_result = text_to_cypher(function_args.get("query", ""), client)
                elif function_name == "similarity_search":
                    tool_result = similarity_search(function_args.get("query", ""))
                else:
                    tool_result = "Unknown tool."
                    
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": tool_result
                })
                
            # Step 3: Call Groq again with the tool responses to get the final answer
            second_response = client.chat.completions.create(
                model=llm_model,
                messages=messages,
                temperature=0.2,
                stream=True,
            )
            
            result_text = ""
            for chunk in second_response:
                result_text += chunk.choices[0].delta.content or ""
            return result_text
            
        else:
            # If no tools were called, just return the direct response
            return response_message.content

    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        return f"⚠️ Groq API Error: {e}"
