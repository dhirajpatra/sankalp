import json
import os
import logging
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv

logger = logging.getLogger("ontology_engine")

# ── .env loading ──────────────────────────────────────────────────────────────
# Docker injects env vars directly via docker-compose environment: block,
# so no .env file exists inside the container.  For local dev, search upward
# from this file's location until we find a .env, then load it.
def _load_env():
    candidate = Path(__file__).resolve().parent  # start at agents/
    for _ in range(4):                            # walk up at most 4 levels
        env_file = candidate / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=True)
            logger.info(f"Loaded .env from {env_file}")
            return
        candidate = candidate.parent
    # Not found – Docker has already injected everything via environment:
    logger.info("No .env file found on disk; relying on environment variables (Docker mode).")

_load_env()

# ── Connection config (read after env is loaded) ──────────────────────────────
NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER",     "neo4j")
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
            "attack terrorist infiltration from our southern sea borders": {
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
    """Queries Neo4j for current operational counts across all branches."""
    try:
        driver = get_neo4j_driver()
        caps = {"iaf_op": 0, "army_op": 0, "navy_op": 0}
        with driver.session() as session:
            res = session.run(
                "MATCH (a:Aircraft) WHERE "
                "coalesce(a.final_readiness_score, coalesce(a.readiness_base_score, "
                "100 - (toFloat(coalesce(a.flight_hours, 0)) * 0.8))) >= 60 "
                "RETURN COUNT(a)"
            )
            caps["iaf_op"] = res.single()[0]

            res = session.run(
                "MATCH (a:ArmyAsset) WHERE "
                "coalesce(a.final_readiness_score, coalesce(a.readiness_base_score, "
                "100 - (toFloat(coalesce(a.operational_hours, 0)) * 0.5))) >= 60 "
                "RETURN COUNT(a)"
            )
            caps["army_op"] = res.single()[0]

            res = session.run(
                "MATCH (v:Vessel) WHERE "
                "coalesce(v.final_readiness_score, coalesce(v.readiness_base_score, "
                "100 - (toFloat(coalesce(v.sea_hours, 0)) * 0.2))) >= 60 "
                "RETURN COUNT(v)"
            )
            caps["navy_op"] = res.single()[0]
        driver.close()
        return caps
    except Exception as e:
        logger.error(f"Neo4j capability query failed: {e}")
        return {"iaf_op": 0, "army_op": 0, "navy_op": 0}


def evaluate_action(action_name):
    rules = load_rules()
    if action_name not in rules:
        return False, [f"Action '{action_name}' not defined in ontology logic."]

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


def _resolve_api_key() -> str:
    """
    Reads Groq API key from environment.
    Works in both Docker (env vars injected by compose) and local dev (.env file).
    Calls _load_env() again to catch any late .env writes.
    """
    _load_env()  # no-op in Docker; re-reads .env for local dev

    PLACEHOLDERS = {"fdsfdfas", "your_api_key_here", "changeme", "xxxx",
                    "gsk_...", "gsk_your_real_key", ""}
    var_names = ["GROQ_API_KEY", "GROQ_LLM_API_KEY", "LLM_API_KEY"]

    for var in var_names:
        raw = os.getenv(var, "")
        cleaned = raw.strip().strip("\"'")
        if cleaned and cleaned.lower() not in PLACEHOLDERS:
            logger.info(f"Groq key resolved from env var: {var}")
            return cleaned

    logger.error(
        "No valid Groq API key found in environment. "
        + " | ".join(f"{v}={os.getenv(v, '<not set>')!r}" for v in var_names)
    )
    return ""


def ask_llm_groq(query: str) -> str:
    """Uses Groq API to answer a natural language question based on ontology state."""
    api_key = _resolve_api_key()

    if not api_key:
        # Show exactly what env vars Docker has so the user can debug
        var_names = ["GROQ_API_KEY", "GROQ_LLM_API_KEY", "LLM_API_KEY"]
        env_dump = "\n".join(
            f"- `{v}` = `{os.getenv(v, '<not set>')}`" for v in var_names
        )
        return (
            "⚠️ **Groq API key not found in environment.**\n\n"
            f"**Current env var values seen by the app:**\n{env_dump}\n\n"
            "**If running via Docker Compose**, add to your `docker-compose.yml` "
            "under the `agents:` service `environment:` block:\n"
            "```yaml\n      GROQ_API_KEY: your_gsk_key_here\n```\n"
            "Then restart: `docker compose down && docker compose up -d`\n\n"
            "**If running locally**, ensure `.env` in the project root contains:\n"
            "```\nGROQ_API_KEY=gsk_your_real_key\n```"
        )

    llm_model = os.getenv("MODEL", "llama-3.1-8b-instant").strip("\"'")
    # Strip any provider prefix e.g. "llama/llama-3.1-8b-instant" → "llama-3.1-8b-instant"
    if "/" in llm_model:
        llm_model = llm_model.split("/")[-1]

    caps  = get_current_capabilities()
    rules = load_rules()

    system_prompt = (
        "You are 'Sankalp-AI', the master defence intelligence ontology AI for the Indian Armed Forces. "
        "Answer operational questions concisely and decisively like a high-ranking military commander. "
        "Use the provided live data to answer. If numbers don't support an action, clearly state why.\n\n"
        f"CURRENT FLEET CAPABILITIES (Live Neo4j Digital Twin):\n"
        f"- IAF: {caps['iaf_op']} Operational Aircraft\n"
        f"- Army: {caps['army_op']} Operational Assets\n"
        f"- Navy: {caps['navy_op']} Seaworthy Vessels\n\n"
        f"DOCTRINE RULES:\n{json.dumps(rules, indent=2)}\n"
    )

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        # Try agentic tool use
        try:
            from agents.ontology_tools import tools_schema, text_to_cypher, similarity_search
            _use_tools = True
        except ImportError:
            try:
                from ontology_tools import tools_schema, text_to_cypher, similarity_search
                _use_tools = True
            except ImportError:
                _use_tools = False

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": query},
        ]

        if _use_tools:
            completion = client.chat.completions.create(
                model=llm_model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=0.2,
                max_completion_tokens=2048,
            )
            response_message = completion.choices[0].message

            if response_message.tool_calls:
                messages.append({
                    "role": "assistant",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name,
                                      "arguments": tc.function.arguments}}
                        for tc in response_message.tool_calls
                    ],
                })
                for tc in response_message.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)
                    if fn_name == "text_to_cypher":
                        result = text_to_cypher(fn_args.get("query", ""), client)
                    elif fn_name == "similarity_search":
                        result = similarity_search(fn_args.get("query", ""))
                    else:
                        result = "Unknown tool."
                    messages.append({
                        "tool_call_id": tc.id, "role": "tool",
                        "name": fn_name, "content": result
                    })

                second = client.chat.completions.create(
                    model=llm_model, messages=messages,
                    temperature=0.2, stream=True,
                )
                return "".join(chunk.choices[0].delta.content or "" for chunk in second)

            return response_message.content or ""

        else:
            completion = client.chat.completions.create(
                model=llm_model,
                messages=messages,
                temperature=0.2,
                max_completion_tokens=2048,
            )
            return completion.choices[0].message.content or ""

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return (
            f"⚠️ **Groq API error:** `{e}`\n\n"
            f"Model used: `{llm_model}`\n"
            "Verify the key is valid at https://console.groq.com"
        )
