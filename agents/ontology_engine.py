import json
import os
import logging
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv

logger = logging.getLogger("ontology_engine")

# ── .env loading ──────────────────────────────────────────────────────────────
def _load_env():
    candidate = Path(__file__).resolve().parent
    for _ in range(4):
        env_file = candidate / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=True)
            logger.info(f"Loaded .env from {env_file}")
            return
        candidate = candidate.parent
    logger.info("No .env file found; relying on environment variables (Docker mode).")

_load_env()

NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sankalp123")

RULES_FILE = "data/processed/ontology_rules.json"


def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


def load_rules():
    if not os.path.exists(RULES_FILE):
        _write_default_rules()
    with open(RULES_FILE, "r") as f:
        return json.load(f)


def _write_default_rules():
    os.makedirs("data/processed", exist_ok=True)
    default = {
        "protect northern border from any type of infiltration": {
            "iaf_min_operational": 5,
            "army_min_operational": 0,
            "navy_min_operational": 0,
            "iaf_sufficient_alone": True,
            "army_enhances": True,
            "army_enhancement_threshold": 10,
            "description": (
                "IAF alone can handle northern border infiltration with air superiority. "
                "If Army assets (>=10) are also available, the response is classified "
                "SUPERIOR with ground assault capability."
            ),
            "logic_mode": "iaf_primary_army_superior"
        },
        "attack terrorist infiltration from our southern sea borders": {
            "iaf_min_operational": 2,
            "army_min_operational": 0,
            "navy_min_operational": 8,
            "iaf_sufficient_alone": False,
            "army_enhances": False,
            "army_enhancement_threshold": 0,
            "description": (
                "Requires fleet of Navy vessels for blockade and IAF recon support."
            ),
            "logic_mode": "standard"
        }
    }
    with open(RULES_FILE, "w") as f:
        json.dump(default, f, indent=4)


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


def evaluate_action(action_name: str):
    """
    Evaluate whether a named doctrine action can be executed.

    logic_mode = "iaf_primary_army_superior":
        - IAF meeting its minimum alone = CAN EXECUTE (air-only response)
        - IAF + Army both meeting thresholds = SUPERIOR RESPONSE
        - IAF below minimum = CANNOT EXECUTE regardless of Army

    logic_mode = "standard":
        - All branch minimums must be met simultaneously
    """
    rules = load_rules()
    if action_name not in rules:
        return False, [f"Action '{action_name}' not defined in ontology logic."]

    rule  = rules[action_name]
    caps  = get_current_capabilities()
    mode  = rule.get("logic_mode", "standard")

    reasons     = []
    can_execute = False
    tier        = None   # "SUPERIOR" | "ADEQUATE" | "INSUFFICIENT"

    if mode == "iaf_primary_army_superior":
        iaf_ok   = caps["iaf_op"] >= rule["iaf_min_operational"]
        army_enh = rule.get("army_enhances", False)
        army_thr = rule.get("army_enhancement_threshold", 0)
        army_ok  = caps["army_op"] >= army_thr if army_enh else False

        if iaf_ok and army_ok:
            can_execute = True
            tier = "SUPERIOR"
            reasons.append(
                f"✅ **IAF**: {caps['iaf_op']} operational aircraft "
                f"(minimum {rule['iaf_min_operational']}) — air superiority confirmed."
            )
            reasons.append(
                f"✅ **Army**: {caps['army_op']} operational assets "
                f"(enhancement threshold {army_thr}) — ground assault capability added. "
                f"**Response tier: 🏆 SUPERIOR**"
            )
        elif iaf_ok:
            can_execute = True
            tier = "ADEQUATE"
            reasons.append(
                f"✅ **IAF**: {caps['iaf_op']} operational aircraft "
                f"(minimum {rule['iaf_min_operational']}) — air-only response possible."
            )
            if army_enh:
                reasons.append(
                    f"⚠️  **Army**: {caps['army_op']} operational assets "
                    f"(enhancement threshold {army_thr} not met) — "
                    f"ground support unavailable. **Response tier: 🟡 ADEQUATE (Air Only)**"
                )
        else:
            can_execute = False
            tier = "INSUFFICIENT"
            reasons.append(
                f"❌ **IAF**: {caps['iaf_op']} operational aircraft — "
                f"minimum {rule['iaf_min_operational']} required. "
                f"**Cannot execute — no air superiority.**"
            )
            if army_enh:
                army_status = "✅" if army_ok else "⚠️ "
                reasons.append(
                    f"{army_status} **Army**: {caps['army_op']} assets available, "
                    f"but IAF shortfall prevents execution. "
                    f"**Response tier: 🔴 INSUFFICIENT**"
                )

        # Navy not required for northern border — just note it
        reasons.append(
            f"ℹ️  **Navy**: {caps['navy_op']} seaworthy vessels "
            f"(not required for this doctrine)."
        )

    else:
        # Standard mode — all minimums must be met
        iaf_ok   = caps["iaf_op"]   >= rule["iaf_min_operational"]
        army_ok  = caps["army_op"]  >= rule["army_min_operational"]
        navy_ok  = caps["navy_op"]  >= rule["navy_min_operational"]
        can_execute = iaf_ok and army_ok and navy_ok

        def _fmt(label, actual, required, ok):
            mark = "✅" if ok else "❌"
            return f"{mark} **{label}**: {actual} available (requires {required})."

        reasons.append(_fmt("IAF",  caps["iaf_op"],  rule["iaf_min_operational"],  iaf_ok))
        reasons.append(_fmt("Army", caps["army_op"], rule["army_min_operational"], army_ok))
        reasons.append(_fmt("Navy", caps["navy_op"], rule["navy_min_operational"], navy_ok))
        tier = "ADEQUATE" if can_execute else "INSUFFICIENT"

    return can_execute, reasons, tier


def _resolve_api_key() -> str:
    _load_env()
    PLACEHOLDERS = {"fdsfdfas", "your_api_key_here", "changeme", "xxxx",
                    "gsk_...", "gsk_your_real_key", ""}
    for var in ["GROQ_API_KEY", "GROQ_LLM_API_KEY", "LLM_API_KEY"]:
        raw = os.getenv(var, "")
        cleaned = raw.strip().strip("\"'")
        if cleaned and cleaned.lower() not in PLACEHOLDERS:
            logger.info(f"Groq key resolved from: {var}")
            return cleaned
    logger.error("No valid Groq API key found in environment.")
    return ""


def ask_llm_groq(query: str) -> str:
    """
    Uses Groq API with live Neo4j context and the doctrine rules.
    The system prompt explicitly teaches the LLM about the
    iaf_primary_army_superior logic so it reasons correctly.
    """
    api_key = _resolve_api_key()

    if not api_key:
        var_names = ["GROQ_API_KEY", "GROQ_LLM_API_KEY", "LLM_API_KEY"]
        env_dump = "\n".join(
            f"- `{v}` = `{os.getenv(v, '<not set>')}`" for v in var_names
        )
        return (
            "⚠️ **Groq API key not found in environment.**\n\n"
            f"**Current env var values:**\n{env_dump}\n\n"
            "**Docker Compose** — add to `agents:` → `environment:`:\n"
            "```yaml\n      GROQ_API_KEY: your_gsk_key_here\n```\n"
            "Then: `docker compose down && docker compose up -d`\n\n"
            "**Local dev** — add to `.env`:\n"
            "```\nGROQ_API_KEY=gsk_your_real_key\n```"
        )

    llm_model = os.getenv("MODEL", "llama-3.1-8b-instant").strip("\"'")
    if "/" in llm_model:
        llm_model = llm_model.split("/")[-1]

    caps  = get_current_capabilities()
    rules = load_rules()

    system_prompt = (
        "You are 'Sankalp-AI', the master defence intelligence ontology AI "
        "for the Indian Armed Forces. Answer like a decisive senior military commander.\n\n"

        "## DOCTRINE LOGIC RULES\n"
        "Some actions follow 'iaf_primary_army_superior' mode:\n"
        "  - IAF alone meeting its minimum → CAN EXECUTE (air-only, ADEQUATE tier)\n"
        "  - IAF + Army both meeting thresholds → CAN EXECUTE (SUPERIOR tier — "
        "ground assault adds decisive advantage)\n"
        "  - IAF below minimum → CANNOT EXECUTE (no air superiority) even if Army is ready\n\n"

        "## LIVE FLEET STATUS (Neo4j Digital Twin)\n"
        f"- IAF: {caps['iaf_op']} operational aircraft\n"
        f"- Army: {caps['army_op']} operational assets\n"
        f"- Navy: {caps['navy_op']} seaworthy vessels\n\n"

        "## CONFIGURED DOCTRINE RULES\n"
        f"{json.dumps(rules, indent=2)}\n\n"

        "When answering, state the response tier clearly: "
        "🏆 SUPERIOR, 🟡 ADEQUATE, or 🔴 INSUFFICIENT. "
        "Be specific about which branch meets or fails the threshold."
    )

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

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
                model=llm_model, messages=messages,
                temperature=0.2, max_completion_tokens=2048,
            )
            return completion.choices[0].message.content or ""

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return (
            f"⚠️ **Groq API error:** `{e}`\n\n"
            f"Model: `{llm_model}` — verify at https://console.groq.com"
        )
