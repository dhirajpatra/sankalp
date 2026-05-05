"""
ontology_engine.py – SANKALP Ontology Engine
Fix: evaluate_action results are now injected into the LLM system prompt so the
LLM cannot re-reason from scratch and produce a wrong tier verdict.
"""

import json
import os
import logging
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv
from config_loader import cfg

logger = logging.getLogger("ontology_engine")


def _load_env():
    candidate = Path(__file__).resolve().parent
    for _ in range(4):
        env_file = candidate / ".env"
        if env_file.exists():
            load_dotenv(dotenv_path=env_file, override=True)
            return
        candidate = candidate.parent


_load_env()

NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sankalp123")

RULES_FILE = cfg("paths.rules_file")


# ── Neo4j ─────────────────────────────────────────────────────────────────────
def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


# ── Rules CRUD ────────────────────────────────────────────────────────────────
def load_rules() -> dict:
    if not os.path.exists(RULES_FILE):
        _write_default_rules()
    with open(RULES_FILE) as f:
        return json.load(f)


def save_rules(rules: dict) -> None:
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=4)
    try:
        from ontology_rag import invalidate_index
        invalidate_index()
    except Exception:
        pass


def add_rule(action_name, description, iaf_min, army_min, navy_min,
             iaf_sufficient_alone=False, army_enhances=False,
             army_enhancement_threshold=0):
    action_name = action_name.strip().lower()
    if not action_name:
        return False, "Action name cannot be empty."
    rules = load_rules()
    if action_name in rules:
        return False, f"Rule '{action_name}' already exists."
    logic_mode = (
        "iaf_primary_army_superior"
        if (iaf_sufficient_alone and army_enhances)
        else "standard"
    )
    rules[action_name] = {
        "description": description,
        "iaf_min_operational": iaf_min,
        "army_min_operational": army_min,
        "navy_min_operational": navy_min,
        "iaf_sufficient_alone": iaf_sufficient_alone,
        "army_enhances": army_enhances,
        "army_enhancement_threshold": army_enhancement_threshold,
        "logic_mode": logic_mode,
    }
    save_rules(rules)
    return True, f"Rule '{action_name}' added."


def delete_rule(action_name):
    rules = load_rules()
    if action_name not in rules:
        return False, f"Rule '{action_name}' not found."
    if action_name == "__global_settings__":
        return False, "Cannot delete global settings."
    del rules[action_name]
    save_rules(rules)
    return True, f"Rule '{action_name}' deleted."


# ── Threshold ─────────────────────────────────────────────────────────────────
def get_operational_threshold() -> int:
    return load_rules().get("__global_settings__", {}).get("operational_threshold", 5)


def set_operational_threshold(threshold: int) -> None:
    rules = load_rules()
    rules.setdefault("__global_settings__", {})["operational_threshold"] = threshold
    save_rules(rules)
    update_neo4j_operational_status(threshold)


def update_neo4j_operational_status(threshold: int) -> None:
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            for label, prop in [("Aircraft", "readiness_base_score"),
                                 ("ArmyAsset", "readiness_base_score"),
                                 ("Vessel", "readiness_base_score")]:
                session.run(
                    f"""MATCH (n:{label})
                    SET n.operational_status = CASE
                        WHEN n.{prop} >= $t THEN 'Operational'
                        WHEN n.{prop} >= ($t - 20) THEN 'Watch'
                        ELSE 'Critical' END""",
                    t=threshold,
                )
        driver.close()
    except Exception as e:
        logger.error(f"Neo4j status update failed: {e}")


# ── Capabilities ──────────────────────────────────────────────────────────────
def get_current_capabilities() -> dict:
    try:
        driver = get_neo4j_driver()
        caps = {}
        with driver.session() as session:
            caps["iaf_op"]  = session.run(
                "MATCH (a:Aircraft) WHERE a.operational_status='Operational' RETURN COUNT(a)"
            ).single()[0]
            caps["army_op"] = session.run(
                "MATCH (a:ArmyAsset) WHERE a.operational_status='Operational' RETURN COUNT(a)"
            ).single()[0]
            caps["navy_op"] = session.run(
                "MATCH (v:Vessel) WHERE v.operational_status='Operational' RETURN COUNT(v)"
            ).single()[0]
        driver.close()
        return caps
    except Exception as e:
        logger.error(f"Neo4j capability query failed: {e}")
        return {"iaf_op": 0, "army_op": 0, "navy_op": 0}


# ── Evaluate action ───────────────────────────────────────────────────────────
def evaluate_action(action_name: str) -> tuple:
    """
    Deterministically evaluate whether current fleet capabilities meet the
    requirements for the named action.
    Returns (can_execute: bool, reasons: list[str], tier: str)
    """
    rules = load_rules()
    if action_name not in rules:
        return False, [f"Action '{action_name}' not defined."], "INSUFFICIENT"

    rule = rules[action_name]
    caps = get_current_capabilities()
    mode = rule.get("logic_mode", "standard")
    reasons, can_execute, tier = [], False, "INSUFFICIENT"

    if mode == "iaf_primary_army_superior":
        iaf_ok   = caps["iaf_op"] >= rule["iaf_min_operational"]
        army_thr = rule.get("army_enhancement_threshold", 0)
        army_ok  = caps["army_op"] >= army_thr if rule.get("army_enhances") else False

        if iaf_ok and army_ok:
            can_execute, tier = True, "SUPERIOR"
            reasons += [
                f"✅ IAF: {caps['iaf_op']} aircraft (min {rule['iaf_min_operational']}) — air superiority confirmed.",
                f"✅ Army: {caps['army_op']} assets (threshold {army_thr}) — SUPERIOR tier.",
            ]
        elif iaf_ok:
            can_execute, tier = True, "ADEQUATE"
            reasons.append(f"✅ IAF: {caps['iaf_op']} aircraft — air-only response (ADEQUATE).")
            if rule.get("army_enhances"):
                reasons.append(f"⚠️ Army: {caps['army_op']} assets (threshold {army_thr} not met).")
        else:
            reasons.append(f"❌ IAF: {caps['iaf_op']} aircraft — min {rule['iaf_min_operational']} required.")

        reasons.append(f"ℹ️ Navy: {caps['navy_op']} vessels (not required for this action).")

    else:  # standard mode
        iaf_min  = rule["iaf_min_operational"]
        army_min = rule["army_min_operational"]
        navy_min = rule["navy_min_operational"]

        iaf_ok  = caps["iaf_op"]  >= iaf_min
        army_ok = caps["army_op"] >= army_min
        navy_ok = caps["navy_op"] >= navy_min

        can_execute = iaf_ok and army_ok and navy_ok
        tier = "ADEQUATE" if can_execute else "INSUFFICIENT"

        def _fmt(lbl, actual, req, ok):
            status = "✅" if ok else "❌"
            comparison = "meets" if ok else "BELOW"
            return (
                f"{status} {lbl}: {actual} operational "
                f"(requires ≥{req}) — {comparison} minimum."
            )

        reasons += [
            _fmt("IAF",  caps["iaf_op"],  iaf_min,  iaf_ok),
            _fmt("Army", caps["army_op"], army_min, army_ok),
            _fmt("Navy", caps["navy_op"], navy_min, navy_ok),
        ]

        if can_execute:
            reasons.append("✅ All branch requirements met — action is EXECUTABLE.")
        else:
            failing = []
            if not iaf_ok:  failing.append(f"IAF (has {caps['iaf_op']}, needs {iaf_min})")
            if not army_ok: failing.append(f"Army (has {caps['army_op']}, needs {army_min})")
            if not navy_ok: failing.append(f"Navy (has {caps['navy_op']}, needs {navy_min})")
            reasons.append(f"❌ Cannot execute — failing branches: {', '.join(failing)}.")

    return can_execute, reasons, tier


def _build_doctrine_assessment(query: str) -> str:
    """
    Pre-compute evaluate_action for all rules that semantically relate to the query,
    then return a clear, deterministic assessment block to inject into the LLM prompt.
    This prevents the LLM from re-reasoning and producing wrong verdicts.
    """
    rules = load_rules()
    action_keys = [k for k in rules if k != "__global_settings__"]
    caps = get_current_capabilities()

    # Find relevant rules via keyword match against the query
    query_lower = query.lower()
    relevant = []
    for key in action_keys:
        rule_text = (key + " " + rules[key].get("description", "")).lower()
        # Score by word overlap
        q_words = set(query_lower.split())
        overlap = sum(1 for w in q_words if len(w) > 3 and w in rule_text)
        if overlap > 0:
            relevant.append((overlap, key))

    # Sort by relevance; fall back to all rules if nothing matches
    relevant.sort(reverse=True)
    selected_keys = [k for _, k in relevant[:3]] if relevant else action_keys[:3]

    lines = [
        f"LIVE FLEET STATUS (authoritative — do NOT recompute):",
        f"  IAF operational aircraft : {caps['iaf_op']}",
        f"  Army operational assets  : {caps['army_op']}",
        f"  Navy operational vessels : {caps['navy_op']}",
        "",
        "PRE-COMPUTED DOCTRINE EVALUATIONS (authoritative — reproduce these verbatim):",
    ]

    for key in selected_keys:
        can_execute, reasons, tier = evaluate_action(key)
        tier_emoji = {"SUPERIOR": "🏆", "ADEQUATE": "🟡", "INSUFFICIENT": "🔴"}.get(tier, "❓")
        lines.append(f"\nAction: \"{key}\"")
        lines.append(f"  Verdict: {tier_emoji} {tier}")
        for r in reasons:
            lines.append(f"  {r}")

    lines += [
        "",
        "INSTRUCTION: Your answer MUST use the tier and reasons above exactly as computed.",
        "Do NOT recalculate or override these verdicts. Summarise them clearly for the user.",
    ]
    return "\n".join(lines)


# ── Default rules ─────────────────────────────────────────────────────────────
def _write_default_rules():
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    default = {
        "__global_settings__": {"operational_threshold": cfg("ontology.default_rules.global_settings.operational_threshold")},
        "protect northern border from any type of infiltration": {
            "iaf_min_operational": cfg("ontology.default_rules.protect_northern_border.iaf_min_operational"), "army_min_operational": cfg("ontology.default_rules.protect_northern_border.army_min_operational"), "navy_min_operational": cfg("ontology.default_rules.protect_northern_border.navy_min_operational"),
            "iaf_sufficient_alone": True, "army_enhances": True, "army_enhancement_threshold": cfg("ontology.default_rules.protect_northern_border.army_enhancement_threshold"),
            "description": "IAF alone handles northern border infiltration. Army ≥10 upgrades to SUPERIOR.",
            "logic_mode": "iaf_primary_army_superior",
        },
        "attack terrorist infiltration from our southern sea borders": {
            "iaf_min_operational": cfg("ontology.default_rules.attack_terrorist_infiltration_from_our_southern_sea_borders.iaf_min_operational"), "army_min_operational": cfg("ontology.default_rules.attack_terrorist_infiltration_from_our_southern_sea_borders.army_min_operational"), "navy_min_operational": cfg("ontology.default_rules.attack_terrorist_infiltration_from_our_southern_sea_borders.navy_min_operational"),
            "iaf_sufficient_alone": False, "army_enhances": False, "army_enhancement_threshold": cfg("ontology.default_rules.attack_terrorist_infiltration_from_our_southern_sea_borders.army_enhancement_threshold"),
            "description": "Requires Navy fleet blockade + IAF recon support. Both must meet minimums.",
            "logic_mode": "standard",
        },
    }
    with open(RULES_FILE, "w") as f:
        json.dump(default, f, indent=4)


# ── API key resolver ──────────────────────────────────────────────────────────
def _resolve_api_key() -> str:
    _load_env()
    PLACEHOLDERS = {"fdsfdfas", "your_api_key_here", "changeme", "xxxx", "gsk_...", ""}
    for var in ["GROQ_API_KEY", "GROQ_LLM_API_KEY", "LLM_API_KEY"]:
        val = os.getenv(var, "").strip().strip("\"'")
        if val and val.lower() not in PLACEHOLDERS:
            return val
    return ""


# ── LLM call ──────────────────────────────────────────────────────────────────
def ask_llm_groq(query: str, history: list | None = None) -> str:
    """
    Key fix: pre-computed evaluate_action results are injected into the system
    prompt as authoritative verdicts. The LLM is instructed to reproduce them,
    not re-reason from scratch. This eliminates wrong tier responses.
    """
    api_key = _resolve_api_key()
    if not api_key:
        return (
            "⚠️ **Groq API key not found.**\n"
            "Add `GROQ_API_KEY=gsk_...` to `.env` or Docker env."
        )

    # ── 1. Build deterministic doctrine assessment ────────────────────────────
    doctrine_block = _build_doctrine_assessment(query)

    # ── 2. RAG: fetch relevant rule descriptions for context ──────────────────
    try:
        from ontology_rag import get_relevant_rules_for_prompt, build_index
        rules = load_rules()
        build_index(rules)
        rag_context = get_relevant_rules_for_prompt(query, top_k=2)
    except Exception as e:
        logger.warning(f"RAG unavailable ({e}), skipping.")
        rag_context = ""

    # ── 3. System prompt with pre-computed verdicts injected ──────────────────
    system_prompt = (
        "You are Sankalp-AI, Indian Armed Forces defence intelligence assistant.\n"
        "Answer as a decisive senior military commander.\n\n"
        f"{doctrine_block}\n"
    )
    if rag_context:
        system_prompt += f"\nDOCTRINE BACKGROUND (for context only):\n{rag_context}\n"

    # ── 4. Cap history at last 6 messages ────────────────────────────────────
    prior = (history or [])[-6:]
    messages = [{"role": "system", "content": system_prompt}] + prior + [
        {"role": "user", "content": query}
    ]

    llm_model = os.getenv("MODEL", "llama-3.1-8b-instant").strip("\"'").split("/")[-1]

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        try:
            from agents.ontology_tools import tools_schema, text_to_cypher, similarity_search
        except ImportError:
            try:
                from ontology_tools import tools_schema, text_to_cypher, similarity_search
                _use_tools = True
            except ImportError:
                _use_tools = False
        else:
            _use_tools = True

        if _use_tools:
            completion = client.chat.completions.create(
                model=llm_model,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                temperature=float(cfg("llm.temperature_tool", 0.1)),
                max_completion_tokens=int(cfg("llm.tool_use_max_tokens", 512)),
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
                        "name": fn_name, "content": str(result)[:1000],
                    })
                second = client.chat.completions.create(
                    model=llm_model, messages=messages,
                    temperature=float(cfg("llm.temperature_chat", 0.2)), stream=True,
                    max_completion_tokens=int(cfg("llm.tool_use_max_tokens", 512)),
                )
                return "".join(chunk.choices[0].delta.content or "" for chunk in second)

            return response_message.content or ""

        else:
            completion = client.chat.completions.create(
                model=llm_model, messages=messages,
                temperature=float(cfg("llm.temperature_chat", 0.2)),
                max_completion_tokens=int(cfg("llm.fallback_max_tokens", 1024)),
            )
            return completion.choices[0].message.content or ""

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return f"⚠️ **Groq API error:** {e}"
