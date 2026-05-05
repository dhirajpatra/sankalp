"""
readiness_monitor.py – SANKALP Event-Driven Readiness Monitor
Runs as a background thread; polls Neo4j every N seconds, evaluates doctrine
rules, and writes alerts to SQLite when tiers change.
"""

import sqlite3
import threading
import time
import json
import os
import logging
from datetime import datetime
from pathlib import Path

try:
    from config_loader import cfg
except ImportError:
    cfg = None  # fallback: cfg not available (e.g. very early import)

logger = logging.getLogger("readiness_monitor")

ALERTS_DB = (
    cfg("alerts.alerts_db", "data/processed/sankalp_alerts.db") if cfg else
    os.getenv("ALERTS_DB", "data/processed/sankalp_alerts.db")
)
POLL_SECS = int(
    cfg("alerts.monitor_poll_secs", os.getenv("MONITOR_POLL_SECS", "60")) if cfg else
    os.getenv("MONITOR_POLL_SECS", "60")
)

# ── Thread-safe singleton ─────────────────────────────────────────────────────
_monitor_thread: threading.Thread | None = None
_stop_event = threading.Event()


# ── Alerts DB ─────────────────────────────────────────────────────────────────

def _ensure_alerts_db():
    os.makedirs(os.path.dirname(ALERTS_DB), exist_ok=True)
    conn = sqlite3.connect(ALERTS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            rule_name   TEXT    NOT NULL,
            prev_tier   TEXT,
            new_tier    TEXT    NOT NULL,
            direction   TEXT    NOT NULL,   -- 'degraded' | 'improved'
            iaf_op      INTEGER,
            army_op     INTEGER,
            navy_op     INTEGER,
            message     TEXT,
            ack         INTEGER DEFAULT 0   -- 0=unread, 1=acknowledged
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fleet_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,
            iaf_op      INTEGER,
            army_op     INTEGER,
            navy_op     INTEGER,
            iaf_ready   REAL,
            army_ready  REAL,
            navy_ready  REAL
        )
    """)
    conn.commit()
    conn.close()


def write_alert(rule_name, prev_tier, new_tier, caps: dict, message: str):
    _ensure_alerts_db()
    direction = "degraded" if _tier_index(new_tier) > _tier_index(prev_tier) else "improved"
    conn = sqlite3.connect(ALERTS_DB)
    conn.execute(
        "INSERT INTO alerts (ts, rule_name, prev_tier, new_tier, direction, "
        "iaf_op, army_op, navy_op, message) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            rule_name, prev_tier, new_tier, direction,
            caps.get("iaf_op", 0), caps.get("army_op", 0), caps.get("navy_op", 0),
            message,
        ),
    )
    conn.commit()
    conn.close()
    logger.info(f"Alert written: [{direction.upper()}] {rule_name}: {prev_tier} → {new_tier}")


def write_snapshot(caps: dict, readiness: dict):
    _ensure_alerts_db()
    conn = sqlite3.connect(ALERTS_DB)
    conn.execute(
        "INSERT INTO fleet_snapshots (ts, iaf_op, army_op, navy_op, iaf_ready, army_ready, navy_ready) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            caps.get("iaf_op", 0), caps.get("army_op", 0), caps.get("navy_op", 0),
            readiness.get("iaf", 0), readiness.get("army", 0), readiness.get("navy", 0),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_alerts(limit: int = 50, unread_only: bool = False) -> list[dict]:
    _ensure_alerts_db()
    conn = sqlite3.connect(ALERTS_DB)
    conn.row_factory = sqlite3.Row
    where = "WHERE ack=0" if unread_only else ""
    rows = conn.execute(
        f"SELECT * FROM alerts {where} ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_snapshots(limit: int = 60) -> list[dict]:
    _ensure_alerts_db()
    conn = sqlite3.connect(ALERTS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM fleet_snapshots ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def ack_all_alerts():
    _ensure_alerts_db()
    conn = sqlite3.connect(ALERTS_DB)
    conn.execute("UPDATE alerts SET ack=1 WHERE ack=0")
    conn.commit()
    conn.close()


def unread_count() -> int:
    _ensure_alerts_db()
    conn = sqlite3.connect(ALERTS_DB)
    n = conn.execute("SELECT COUNT(*) FROM alerts WHERE ack=0").fetchone()[0]
    conn.close()
    return n


# ── Tier helpers ──────────────────────────────────────────────────────────────

TIER_ORDER = {"SUPERIOR": 0, "ADEQUATE": 1, "INSUFFICIENT": 2}

def _tier_index(tier: str) -> int:
    return TIER_ORDER.get(tier, 2)


# ── Neo4j readiness query ─────────────────────────────────────────────────────

def _fetch_readiness() -> dict:
    """
    Returns avg readiness scores per branch from Neo4j.
    Falls back to SQLite gold DBs if Neo4j is unreachable.
    """
    try:
        from neo4j import GraphDatabase
        from dotenv import load_dotenv
        load_dotenv(override=True)
        uri  = os.getenv("NEO4J_URI",  "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        pwd  = os.getenv("NEO4J_PASSWORD", "sankalp123")
        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        with driver.session() as s:
            iaf   = s.run("MATCH (a:Aircraft)  RETURN avg(coalesce(a.final_readiness_score, a.readiness_base_score, 0)) AS r").single()["r"] or 0
            army  = s.run("MATCH (a:ArmyAsset) RETURN avg(coalesce(a.final_readiness_score, a.readiness_base_score, 0)) AS r").single()["r"] or 0
            navy  = s.run("MATCH (v:Vessel)    RETURN avg(coalesce(v.final_readiness_score, v.readiness_base_score, 0)) AS r").single()["r"] or 0
        driver.close()
        return {"iaf": round(iaf, 1), "army": round(army, 1), "navy": round(navy, 1)}
    except Exception as e:
        logger.warning(f"Neo4j readiness fetch failed ({e}), using SQLite fallback")
        return _fetch_readiness_sqlite()


def _fetch_readiness_sqlite() -> dict:
    result = {}
    try:
        import pandas as pd
        conn = sqlite3.connect("data/processed/sankalp_gold.db")
        df = pd.read_sql("SELECT readiness_base_score FROM aircraft_gold", conn)
        conn.close()
        result["iaf"] = round(df["readiness_base_score"].mean(), 1)
    except Exception:
        result["iaf"] = 0
    try:
        import pandas as pd
        conn = sqlite3.connect("data/processed/sankalp_army_gold.db")
        df = pd.read_sql("SELECT readiness_base_score FROM assets_gold", conn)
        conn.close()
        result["army"] = round(df["readiness_base_score"].mean(), 1)
    except Exception:
        result["army"] = 0
    try:
        import pandas as pd
        conn = sqlite3.connect("data/processed/sankalp_navy_gold.db")
        df = pd.read_sql("SELECT readiness_base_score FROM vessels_gold", conn)
        conn.close()
        result["navy"] = round(df["readiness_base_score"].mean(), 1)
    except Exception:
        result["navy"] = 0
    return result


# ── Monitor loop ──────────────────────────────────────────────────────────────

def _monitor_loop(prev_tiers: dict):
    logger.info(f"Readiness monitor started (poll every {POLL_SECS}s)")
    _ensure_alerts_db()

    while not _stop_event.is_set():
        try:
            # Import here to avoid circular imports at module load time
            from ontology_engine import evaluate_action, load_rules, get_current_capabilities

            rules = load_rules()
            caps  = get_current_capabilities()
            readiness = _fetch_readiness()

            write_snapshot(caps, readiness)

            action_keys = [k for k in rules if k != "__global_settings__"]
            for action_name in action_keys:
                result = evaluate_action(action_name)
                new_tier = result[2] if len(result) > 2 else ("ADEQUATE" if result[0] else "INSUFFICIENT")
                prev_tier = prev_tiers.get(action_name)

                if prev_tier is not None and prev_tier != new_tier:
                    direction = "degraded" if _tier_index(new_tier) > _tier_index(prev_tier) else "improved"
                    if direction == "degraded":
                        msg = (
                            f"DOCTRINE ALERT: '{action_name}' degraded from {prev_tier} to {new_tier}. "
                            f"Fleet: IAF={caps['iaf_op']}, Army={caps['army_op']}, Navy={caps['navy_op']}."
                        )
                    else:
                        msg = (
                            f"RESTORED: '{action_name}' improved from {prev_tier} to {new_tier}. "
                            f"Fleet: IAF={caps['iaf_op']}, Army={caps['army_op']}, Navy={caps['navy_op']}."
                        )
                    write_alert(action_name, prev_tier, new_tier, caps, msg)

                prev_tiers[action_name] = new_tier

        except Exception as e:
            logger.error(f"Monitor loop error: {e}")

        _stop_event.wait(timeout=POLL_SECS)

    logger.info("Readiness monitor stopped.")


# ── Public API ────────────────────────────────────────────────────────────────

def start_monitor():
    """Start background monitoring thread (idempotent)."""
    global _monitor_thread, _stop_event

    if _monitor_thread and _monitor_thread.is_alive():
        return  # already running

    _stop_event.clear()

    # Seed prev_tiers so we only alert on *changes*, not on first evaluation
    prev_tiers: dict = {}
    try:
        from ontology_engine import evaluate_action, load_rules
        rules = load_rules()
        for k in rules:
            if k == "__global_settings__":
                continue
            result = evaluate_action(k)
            prev_tiers[k] = result[2] if len(result) > 2 else ("ADEQUATE" if result[0] else "INSUFFICIENT")
        logger.info(f"Seeded {len(prev_tiers)} rule baseline tier(s).")
    except Exception as e:
        logger.warning(f"Could not seed prev_tiers: {e}")

    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        args=(prev_tiers,),
        daemon=True,
        name="sankalp-readiness-monitor",
    )
    _monitor_thread.start()
    logger.info("Readiness monitor thread launched.")


def stop_monitor():
    _stop_event.set()


def is_running() -> bool:
    return _monitor_thread is not None and _monitor_thread.is_alive()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
    start_monitor()
    try:
        while True:
            time.sleep(5)
            alerts = get_recent_alerts(limit=5, unread_only=True)
            if alerts:
                print(f"\n--- {len(alerts)} new alert(s) ---")
                for a in alerts:
                    print(f"  [{a['direction'].upper()}] {a['rule_name']}: {a['prev_tier']} → {a['new_tier']} @ {a['ts']}")
    except KeyboardInterrupt:
        stop_monitor()
