"""
automation_engine.py – SANKALP Event-Driven Automation Engine
Pillar: Logic (active, continuous)

Architecture
------------
AutomationRule  – a persisted rule with a trigger condition + action
AutomationEvent – an immutable log entry written every time a rule fires
Scheduler       – APScheduler background thread; evaluates rules on a cadence

Rule anatomy
------------
  trigger_type   : "score_below" | "score_above" | "days_since_maintenance" |
                   "mission_count_below" | "evaluate_action_fail"
  trigger_value  : numeric threshold
  branch         : "iaf" | "army" | "navy" | "all"
  action_type    : "create_alert_node"  – writes an :AutomationAlert node in Neo4j
                   "log_event"          – SQLite only (no Neo4j required)
                   "webhook"            – POST JSON to a URL
  action_payload : dict (alert message template, webhook URL, …)
  cooldown_min   : minimum minutes between repeat firings for the same entity
  enabled        : bool

All rules are stored in SQLite (automation_rules table).
All events are stored in SQLite (automation_events table).
Neo4j :AutomationAlert nodes are written for the "create_alert_node" action.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
from config_loader import cfg

from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("automation_engine")
logging.basicConfig(level=logging.INFO, format="%(levelname)s [AutoEngine] %(message)s")

# ── paths ─────────────────────────────────────────────────────────────────────
AUTOMATION_DB = os.getenv("AUTOMATION_DB", cfg("paths.automation_db"))
IAF_GOLD_DB   = os.getenv("IAF_GOLD_DB",  cfg("paths.iaf_gold_db"))
ARMY_GOLD_DB  = os.getenv("ARMY_GOLD_DB", cfg("paths.army_gold_db"))
NAVY_GOLD_DB  = os.getenv("NAVY_GOLD_DB", cfg("paths.navy_gold_db"))

NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "sankalp123")

# ── singleton scheduler reference ────────────────────────────────────────────
_scheduler      = None
_scheduler_lock = threading.Lock()


# ════════════════════════════════════════════════════════════════════════════
#  DATABASE BOOTSTRAP
# ════════════════════════════════════════════════════════════════════════════

def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(AUTOMATION_DB), exist_ok=True)
    conn = sqlite3.connect(AUTOMATION_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Idempotent."""
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS automation_rules (
            rule_id       TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            description   TEXT,
            branch        TEXT NOT NULL DEFAULT 'all',
            trigger_type  TEXT NOT NULL,
            trigger_value REAL NOT NULL,
            action_type   TEXT NOT NULL,
            action_payload TEXT NOT NULL DEFAULT '{}',
            cooldown_min  INTEGER NOT NULL DEFAULT 60,
            enabled       INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS automation_events (
            event_id      TEXT PRIMARY KEY,
            rule_id       TEXT NOT NULL,
            rule_name     TEXT NOT NULL,
            branch        TEXT NOT NULL,
            entity_id     TEXT NOT NULL,
            entity_type   TEXT NOT NULL,
            trigger_value REAL,
            actual_value  REAL,
            action_type   TEXT NOT NULL,
            action_result TEXT,
            fired_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_events_rule   ON automation_events(rule_id);
        CREATE INDEX IF NOT EXISTS idx_events_entity ON automation_events(entity_id);
        CREATE INDEX IF NOT EXISTS idx_events_fired  ON automation_events(fired_at);
        """)
    logger.info("Automation DB initialised.")
    _seed_default_rules()


# ════════════════════════════════════════════════════════════════════════════
#  DEFAULT RULES (seeded once)
# ════════════════════════════════════════════════════════════════════════════

_DEFAULT_RULES = [
    {
        "rule_id":       "auto_iaf_critical",
        "name":          "IAF aircraft critical readiness",
        "description":   "Alert when an IAF aircraft final_readiness_score falls below the critical threshold.",
        "branch":        "iaf",
        "trigger_type":  "score_below",
        "trigger_value": 30.0,
        "action_type":   "create_alert_node",
        "action_payload": {
            "severity": "CRITICAL",
            "message":  "Aircraft {entity_id} readiness has dropped to {actual_value:.1f}% — immediate depot inspection required (IAF SOP §4.2).",
            "neo4j_label": "Aircraft",
        },
        "cooldown_min":  120,
    },
    {
        "rule_id":       "auto_iaf_watch",
        "name":          "IAF aircraft watch readiness",
        "description":   "Warn when an IAF aircraft score falls below the watch threshold.",
        "branch":        "iaf",
        "trigger_type":  "score_below",
        "trigger_value": 55.0,
        "action_type":   "create_alert_node",
        "action_payload": {
            "severity": "WARNING",
            "message":  "Aircraft {entity_id} readiness is {actual_value:.1f}% — schedule preventive maintenance within 7 days.",
            "neo4j_label": "Aircraft",
        },
        "cooldown_min":  240,
    },
    {
        "rule_id":       "auto_army_critical",
        "name":          "Army asset critical readiness",
        "description":   "Alert when an Army asset final_readiness_score falls below the critical threshold.",
        "branch":        "army",
        "trigger_type":  "score_below",
        "trigger_value": 30.0,
        "action_type":   "create_alert_node",
        "action_payload": {
            "severity": "CRITICAL",
            "message":  "Asset {entity_id} readiness has dropped to {actual_value:.1f}% — REME depot service mandatory.",
            "neo4j_label": "ArmyAsset",
        },
        "cooldown_min":  120,
    },
    {
        "rule_id":       "auto_navy_critical",
        "name":          "Naval vessel critical readiness",
        "description":   "Alert when a naval vessel final_readiness_score falls below the critical threshold.",
        "branch":        "navy",
        "trigger_type":  "score_below",
        "trigger_value": 30.0,
        "action_type":   "create_alert_node",
        "action_payload": {
            "severity": "CRITICAL",
            "message":  "Vessel {entity_id} readiness has dropped to {actual_value:.1f}% — dockyard refit required per IN schedule.",
            "neo4j_label": "Vessel",
        },
        "cooldown_min":  120,
    },
    {
        "rule_id":       "auto_iaf_stale",
        "name":          "IAF aircraft maintenance overdue",
        "description":   "Alert when days since last maintenance exceeds 180 days.",
        "branch":        "iaf",
        "trigger_type":  "days_since_maintenance",
        "trigger_value": 180.0,
        "action_type":   "create_alert_node",
        "action_payload": {
            "severity": "WARNING",
            "message":  "Aircraft {entity_id} last maintenance was {actual_value:.0f} days ago — scheduled overhaul overdue.",
            "neo4j_label": "Aircraft",
        },
        "cooldown_min":  1440,
    },
    {
        "rule_id":       "auto_doctrine_fail",
        "name":          "Doctrine readiness check failed",
        "description":   "Alert when a doctrine action cannot be executed due to insufficient operational assets.",
        "branch":        "all",
        "trigger_type":  "evaluate_action_fail",
        "trigger_value": 0.0,
        "action_type":   "log_event",
        "action_payload": {
            "severity": "INFO",
            "message":  "Doctrine check '{entity_id}' — INSUFFICIENT. {actual_value:.0f} operational assets below requirement.",
        },
        "cooldown_min":  30,
    },
]


def _seed_default_rules() -> None:
    with _get_conn() as conn:
        existing = {r["rule_id"] for r in conn.execute("SELECT rule_id FROM automation_rules").fetchall()}
        now = _now()
        for r in _DEFAULT_RULES:
            if r["rule_id"] not in existing:
                conn.execute(
                    """INSERT INTO automation_rules
                       (rule_id, name, description, branch, trigger_type, trigger_value,
                        action_type, action_payload, cooldown_min, enabled, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,1,?,?)""",
                    (r["rule_id"], r["name"], r["description"], r["branch"],
                     r["trigger_type"], r["trigger_value"], r["action_type"],
                     json.dumps(r["action_payload"]), r["cooldown_min"], now, now),
                )
        conn.commit()


# ════════════════════════════════════════════════════════════════════════════
#  RULE CRUD
# ════════════════════════════════════════════════════════════════════════════

def list_rules(enabled_only: bool = False) -> list[dict]:
    with _get_conn() as conn:
        q = "SELECT * FROM automation_rules"
        if enabled_only:
            q += " WHERE enabled = 1"
        q += " ORDER BY branch, trigger_type"
        rows = conn.execute(q).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["action_payload"] = json.loads(d["action_payload"])
        result.append(d)
    return result


def get_rule(rule_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM automation_rules WHERE rule_id=?", (rule_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["action_payload"] = json.loads(d["action_payload"])
    return d


def add_rule(rule: dict) -> tuple[bool, str]:
    """
    rule must contain: name, branch, trigger_type, trigger_value,
                       action_type, action_payload (dict), cooldown_min
    Optional: rule_id, description, enabled
    """
    import uuid
    rule_id = rule.get("rule_id") or f"auto_{uuid.uuid4().hex[:8]}"
    now = _now()
    try:
        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO automation_rules
                   (rule_id, name, description, branch, trigger_type, trigger_value,
                    action_type, action_payload, cooldown_min, enabled, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rule_id, rule["name"], rule.get("description", ""),
                 rule.get("branch", "all"), rule["trigger_type"],
                 float(rule["trigger_value"]), rule["action_type"],
                 json.dumps(rule.get("action_payload", {})),
                 int(rule.get("cooldown_min", 60)),
                 1 if rule.get("enabled", True) else 0, now, now),
            )
            conn.commit()
        return True, rule_id
    except Exception as e:
        return False, str(e)


def update_rule(rule_id: str, updates: dict) -> tuple[bool, str]:
    allowed = {"name", "description", "branch", "trigger_type", "trigger_value",
               "action_type", "action_payload", "cooldown_min", "enabled"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if "action_payload" in updates:
        updates["action_payload"] = json.dumps(updates["action_payload"])
    updates["updated_at"] = _now()
    try:
        with _get_conn() as conn:
            sets   = ", ".join(f"{k}=?" for k in updates)
            values = list(updates.values()) + [rule_id]
            conn.execute(f"UPDATE automation_rules SET {sets} WHERE rule_id=?", values)
            conn.commit()
        return True, "updated"
    except Exception as e:
        return False, str(e)


def delete_rule(rule_id: str) -> tuple[bool, str]:
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM automation_rules WHERE rule_id=?", (rule_id,))
            conn.commit()
        return True, "deleted"
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════════════════
#  EVENT LOG
# ════════════════════════════════════════════════════════════════════════════

def list_events(limit: int = 100, rule_id: Optional[str] = None,
                branch: Optional[str] = None) -> list[dict]:
    with _get_conn() as conn:
        q    = "SELECT * FROM automation_events WHERE 1=1"
        args = []
        if rule_id:
            q += " AND rule_id=?"; args.append(rule_id)
        if branch:
            q += " AND branch=?";  args.append(branch)
        q += " ORDER BY fired_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def _log_event(rule: dict, branch: str, entity_id: str, entity_type: str,
               trigger_val: float, actual_val: float, action_result: str) -> None:
    import uuid
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO automation_events
               (event_id, rule_id, rule_name, branch, entity_id, entity_type,
                trigger_value, actual_value, action_type, action_result, fired_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (uuid.uuid4().hex, rule["rule_id"], rule["name"], branch,
             entity_id, entity_type, trigger_val, actual_val,
             rule["action_type"], action_result, _now()),
        )
        conn.commit()


def _cooldown_ok(rule_id: str, entity_id: str, cooldown_min: int) -> bool:
    """Return True if the rule hasn't fired for entity_id within cooldown window."""
    cutoff = (datetime.now(tz=__import__("datetime").timezone.utc) - timedelta(minutes=cooldown_min)).isoformat()
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM automation_events
               WHERE rule_id=? AND entity_id=? AND fired_at > ?""",
            (rule_id, entity_id, cutoff),
        ).fetchone()
    return row[0] == 0


# ════════════════════════════════════════════════════════════════════════════
#  ACTIONS
# ════════════════════════════════════════════════════════════════════════════

def _get_neo4j_driver():
    from neo4j import GraphDatabase
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        logger.warning(f"Neo4j unavailable for automation: {e}")
        return None


def _action_create_alert_node(rule: dict, entity_id: str,
                               actual_val: float) -> str:
    """Write an :AutomationAlert node to Neo4j and link it to the asset node."""
    payload  = rule["action_payload"]
    severity = payload.get("severity", "WARNING")
    template = payload.get("message", "Alert for {entity_id}")
    neo4j_lbl = payload.get("neo4j_label", "Aircraft")
    msg = template.format(entity_id=entity_id, actual_value=actual_val)

    driver = _get_neo4j_driver()
    if driver is None:
        return f"neo4j_offline | logged: {msg}"

    import uuid
    alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
    try:
        with driver.session() as session:
            session.run(
                """
                CREATE (al:AutomationAlert {
                    alert_id:   $alert_id,
                    rule_id:    $rule_id,
                    severity:   $severity,
                    message:    $message,
                    entity_id:  $entity_id,
                    created_at: $created_at,
                    resolved:   false
                })
                WITH al
                MATCH (asset {%(id_prop)s: $entity_id})
                WHERE $label IN labels(asset)
                MERGE (asset)-[:HAS_ALERT]->(al)
                """ % {"id_prop": _id_prop(neo4j_lbl)},
                alert_id=alert_id, rule_id=rule["rule_id"],
                severity=severity, message=msg,
                entity_id=entity_id, created_at=_now(),
                label=neo4j_lbl,
            )
        driver.close()
        return f"alert_node_created:{alert_id}"
    except Exception as e:
        logger.error(f"Neo4j alert creation failed: {e}")
        return f"neo4j_error:{e}"


def _id_prop(label: str) -> str:
    return {
        "Aircraft":    "aircraft_id",
        "ArmyAsset":   "asset_id",
        "Vessel":      "vessel_id",
    }.get(label, "aircraft_id")


def _action_webhook(rule: dict, entity_id: str, actual_val: float) -> str:
    """POST alert JSON to a configured webhook URL."""
    import urllib.request
    payload = rule["action_payload"]
    url     = payload.get("url", "")
    if not url:
        return "no_webhook_url_configured"
    body = json.dumps({
        "rule_id":    rule["rule_id"],
        "rule_name":  rule["name"],
        "entity_id":  entity_id,
        "actual_value": actual_val,
        "severity":   payload.get("severity", "WARNING"),
        "message":    payload.get("message", "").format(
            entity_id=entity_id, actual_value=actual_val),
        "fired_at":   _now(),
    }).encode()
    try:
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return f"webhook_ok:{resp.status}"
    except Exception as e:
        return f"webhook_error:{e}"


def _dispatch_action(rule: dict, entity_id: str, actual_val: float) -> str:
    action = rule["action_type"]
    if action == "create_alert_node":
        return _action_create_alert_node(rule, entity_id, actual_val)
    elif action == "webhook":
        return _action_webhook(rule, entity_id, actual_val)
    else:  # "log_event" or fallback
        payload = rule["action_payload"]
        msg = payload.get("message", "").format(entity_id=entity_id, actual_value=actual_val)
        logger.info(f"[{payload.get('severity','INFO')}] {msg}")
        return f"logged:{msg[:80]}"


# ════════════════════════════════════════════════════════════════════════════
#  EVALUATORS — one per trigger_type
# ════════════════════════════════════════════════════════════════════════════

def _load_readiness(branch: str) -> list[dict]:
    """Return list of {entity_id, entity_type, score, last_maintenance} dicts."""
    db_map = {"iaf": IAF_GOLD_DB, "army": ARMY_GOLD_DB, "navy": NAVY_GOLD_DB}
    table_map = {
        "iaf":  ("aircraft_readiness", "aircraft_id", "Aircraft",  "last_maintenance_date"),
        "army": ("asset_readiness",    "asset_id",    "ArmyAsset", "last_service_date"),
        "navy": ("vessel_readiness",   "vessel_id",   "Vessel",    "last_refit_date"),
    }
    db = db_map.get(branch)
    if not db or not os.path.exists(db):
        return []
    table, id_col, etype, date_col = table_map[branch]
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT {id_col} AS entity_id, final_readiness_score AS score,"
            f" {date_col} AS maint_date FROM {table}"
        ).fetchall()
        conn.close()
        return [{"entity_id": r["entity_id"], "entity_type": etype,
                 "score": float(r["score"] or 0), "maint_date": r["maint_date"],
                 "branch": branch}
                for r in rows]
    except Exception as e:
        logger.warning(f"Could not load {branch} readiness: {e}")
        return []


def _eval_score_below(rule: dict) -> list[dict]:
    """Fire for each entity where score < trigger_value."""
    branches = ["iaf", "army", "navy"] if rule["branch"] == "all" else [rule["branch"]]
    hits = []
    for branch in branches:
        for row in _load_readiness(branch):
            if row["score"] < rule["trigger_value"]:
                hits.append({**row, "actual_value": row["score"]})
    return hits


def _eval_score_above(rule: dict) -> list[dict]:
    branches = ["iaf", "army", "navy"] if rule["branch"] == "all" else [rule["branch"]]
    hits = []
    for branch in branches:
        for row in _load_readiness(branch):
            if row["score"] > rule["trigger_value"]:
                hits.append({**row, "actual_value": row["score"]})
    return hits


def _eval_days_since_maintenance(rule: dict) -> list[dict]:
    branches = ["iaf", "army", "navy"] if rule["branch"] == "all" else [rule["branch"]]
    hits = []
    today = datetime.now(tz=__import__("datetime").timezone.utc).date()
    for branch in branches:
        for row in _load_readiness(branch):
            mdate = row.get("maint_date")
            if not mdate:
                continue
            try:
                d = datetime.strptime(str(mdate)[:10], "%Y-%m-%d").date()
                days = (today - d).days
                if days > rule["trigger_value"]:
                    hits.append({**row, "actual_value": float(days)})
            except Exception:
                pass
    return hits


def _eval_evaluate_action_fail(rule: dict) -> list[dict]:
    """Fire for each doctrine rule that currently cannot be executed."""
    try:
        from agents.ontology_engine import load_rules, evaluate_action
    except ImportError:
        try:
            from ontology_engine import load_rules, evaluate_action
        except ImportError:
            return []
    hits = []
    rules = load_rules()
    for action_name, _ in rules.items():
        if action_name == "__global_settings__":
            continue
        try:
            can_exec, reasons, tier = evaluate_action(action_name)
            if not can_exec:
                # count total shortfall (sum of all branch deficits)
                hits.append({
                    "entity_id":   action_name,
                    "entity_type": "DoctrineRule",
                    "branch":      "all",
                    "actual_value": 0.0,
                })
        except Exception:
            pass
    return hits


_EVALUATORS = {
    "score_below":             _eval_score_below,
    "score_above":             _eval_score_above,
    "days_since_maintenance":  _eval_days_since_maintenance,
    "evaluate_action_fail":    _eval_evaluate_action_fail,
}


# ════════════════════════════════════════════════════════════════════════════
#  MAIN EVALUATION LOOP
# ════════════════════════════════════════════════════════════════════════════

def run_evaluation_cycle() -> list[dict]:
    """
    Evaluate all enabled rules.
    For each rule × entity that fires, check cooldown and dispatch action.
    Returns list of fired event dicts for caller inspection.
    """
    fired = []
    rules = list_rules(enabled_only=True)
    if not rules:
        logger.info("No enabled automation rules — skipping cycle.")
        return fired

    logger.info(f"Automation cycle: evaluating {len(rules)} rule(s).")

    for rule in rules:
        evaluator = _EVALUATORS.get(rule["trigger_type"])
        if not evaluator:
            logger.warning(f"Unknown trigger_type '{rule['trigger_type']}' in rule {rule['rule_id']}")
            continue

        try:
            hits = evaluator(rule)
        except Exception as e:
            logger.error(f"Evaluator error for rule {rule['rule_id']}: {e}")
            continue

        for hit in hits:
            entity_id  = str(hit["entity_id"])
            actual_val = float(hit.get("actual_value", 0))
            branch     = str(hit.get("branch", rule["branch"]))

            if not _cooldown_ok(rule["rule_id"], entity_id, rule["cooldown_min"]):
                logger.debug(f"Cooldown active — skip {rule['rule_id']} × {entity_id}")
                continue

            # Dispatch action
            result = _dispatch_action(rule, entity_id, actual_val)
            logger.info(
                f"FIRED rule='{rule['name']}' entity={entity_id} "
                f"val={actual_val:.1f} result={result}"
            )

            # Persist event
            _log_event(rule, branch, entity_id,
                       hit.get("entity_type", "Unknown"),
                       rule["trigger_value"], actual_val, result)

            fired.append({
                "rule_id":    rule["rule_id"],
                "rule_name":  rule["name"],
                "entity_id":  entity_id,
                "actual_value": actual_val,
                "action_result": result,
                "fired_at":   _now(),
            })

    logger.info(f"Automation cycle complete — {len(fired)} event(s) fired.")
    return fired


# ════════════════════════════════════════════════════════════════════════════
#  BACKGROUND SCHEDULER (APScheduler)
# ════════════════════════════════════════════════════════════════════════════

def start_scheduler(interval_minutes: int = 5) -> None:
    """
    Start a background APScheduler thread.
    Safe to call multiple times — only one scheduler will run.
    """
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            logger.info("Scheduler already running.")
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            logger.warning(
                "APScheduler not installed. Install with: pip install apscheduler\n"
                "Falling back to manual evaluation only."
            )
            return

        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(
            run_evaluation_cycle,
            trigger="interval",
            minutes=interval_minutes,
            id="sankalp_automation",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=60,
        )
        _scheduler.start()
        logger.info(f"Automation scheduler started — interval {interval_minutes} min.")


def stop_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            logger.info("Automation scheduler stopped.")


def scheduler_status() -> dict:
    if _scheduler and _scheduler.running:
        jobs = _scheduler.get_jobs()
        nxt  = jobs[0].next_run_time.isoformat() if jobs else None
        return {"running": True, "next_run": nxt, "job_count": len(jobs)}
    return {"running": False, "next_run": None, "job_count": 0}


# ════════════════════════════════════════════════════════════════════════════
#  ALERT RESOLUTION (Neo4j)
# ════════════════════════════════════════════════════════════════════════════

def resolve_alert(alert_id: str, resolved_by: str = "operator") -> tuple[bool, str]:
    """Mark an :AutomationAlert node as resolved."""
    driver = _get_neo4j_driver()
    if driver is None:
        return False, "Neo4j unavailable"
    try:
        with driver.session() as session:
            result = session.run(
                """MATCH (al:AutomationAlert {alert_id: $aid})
                   SET al.resolved = true, al.resolved_by = $by, al.resolved_at = $ts
                   RETURN al.alert_id""",
                aid=alert_id, by=resolved_by, ts=_now(),
            )
            if result.single():
                return True, f"Alert {alert_id} resolved."
            return False, "Alert not found."
    except Exception as e:
        return False, str(e)
    finally:
        driver.close()


def list_active_alerts() -> list[dict]:
    """Return all unresolved :AutomationAlert nodes from Neo4j."""
    driver = _get_neo4j_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            rows = session.run(
                """MATCH (al:AutomationAlert {resolved: false})
                   RETURN al ORDER BY al.created_at DESC LIMIT 100"""
            )
            return [dict(r["al"]) for r in rows]
    except Exception as e:
        logger.warning(f"list_active_alerts error: {e}")
        return []
    finally:
        driver.close()


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(tz=__import__("datetime").timezone.utc).isoformat(timespec="seconds")


# ════════════════════════════════════════════════════════════════════════════
#  STANDALONE RUN
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    print("\n=== SANKALP Automation Engine ===")
    print(f"Rules loaded: {len(list_rules())}")
    print("\nRunning evaluation cycle...\n")
    events = run_evaluation_cycle()
    if events:
        for ev in events:
            print(f"  FIRED  {ev['rule_name']} | {ev['entity_id']} | val={ev['actual_value']:.1f} | {ev['action_result']}")
    else:
        print("  No rules fired — all assets within thresholds.")
    print("\nDone.")
