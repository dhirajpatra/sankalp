"""
darshan_automation_tab.py – SANKALP Automation Engine UI
Plugs into darshan.py as a new "⚡ Automations" branch.

Usage in darshan.py:
    from darshan_automation_tab import render_automation
    ...
    elif branch == "automation":
        render_automation()

And add to the branches list in darshan_left_sidebar.py:
    ("automation", "⚡", "Automation Engine", "AUTO"),
"""

import streamlit as st
import pandas as pd
from datetime import datetime

try:
    from agents.automation_engine import (
        init_db, list_rules, get_rule, add_rule, update_rule, delete_rule,
        list_events, run_evaluation_cycle, start_scheduler, stop_scheduler,
        scheduler_status, list_active_alerts, resolve_alert,
    )
except ImportError:
    from automation_engine import (
        init_db, list_rules, get_rule, add_rule, update_rule, delete_rule,
        list_events, run_evaluation_cycle, start_scheduler, stop_scheduler,
        scheduler_status, list_active_alerts, resolve_alert,
    )

# ── initialise DB once ────────────────────────────────────────────────────────
init_db()

_TRIGGER_TYPES = [
    "score_below",
    "score_above",
    "days_since_maintenance",
    "evaluate_action_fail",
]
_ACTION_TYPES = ["create_alert_node", "log_event", "webhook"]
_BRANCHES     = ["iaf", "army", "navy", "all"]
_SEVERITIES   = ["CRITICAL", "WARNING", "INFO"]

# ── colour helpers ─────────────────────────────────────────────────────────────

def _sev_badge(sev: str) -> str:
    return {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(sev, "⚪")


def _branch_icon(branch: str) -> str:
    return {"iaf": "✈️", "army": "🪖", "navy": "⚓", "all": "🛡️"}.get(branch, "")


# ════════════════════════════════════════════════════════════════════════════
#  MAIN RENDER
# ════════════════════════════════════════════════════════════════════════════

def render_automation():
    st.markdown("## ⚡ Automation Engine — Event-Driven Alerts")
    st.caption(
        "Active ontology: triggers evaluate on a schedule and fire actions "
        "(Neo4j alert nodes, webhook, log) when thresholds are crossed."
    )

    # ── Sub-tab navigation ────────────────────────────────────────────────────
    sub_tabs = ["🔔 Active Alerts", "📋 Rules", "📜 Event Log",
                "➕ Add Rule", "⚙️ Scheduler"]
    if "auto_tab" not in st.session_state:
        st.session_state.auto_tab = 0

    tab_cols = st.columns(len(sub_tabs))
    for i, (col, label) in enumerate(zip(tab_cols, sub_tabs)):
        with col:
            active = st.session_state.auto_tab == i
            if st.button(label, key=f"auto_subtab_{i}",
                         use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.auto_tab = i
                st.rerun()

    st.markdown("---")
    tab = st.session_state.auto_tab

    # ────────────────────────────────────────────────────────────────────────
    if tab == 0:
        _render_active_alerts()
    elif tab == 1:
        _render_rules()
    elif tab == 2:
        _render_event_log()
    elif tab == 3:
        _render_add_rule()
    elif tab == 4:
        _render_scheduler()


# ════════════════════════════════════════════════════════════════════════════
#  TAB 0 — ACTIVE ALERTS
# ════════════════════════════════════════════════════════════════════════════

def _render_active_alerts():
    st.subheader("🔔 Active (Unresolved) Alerts")

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Run cycle now", type="primary", use_container_width=True):
            with st.spinner("Evaluating all rules…"):
                events = run_evaluation_cycle()
            if events:
                st.success(f"{len(events)} alert(s) fired!")
            else:
                st.info("No rules triggered this cycle.")
            st.rerun()

    # Pull from Neo4j first; fall back to recent event log
    alerts = list_active_alerts()

    if not alerts:
        # Fallback: show recent events from SQLite as a proxy
        st.info("No unresolved Neo4j alert nodes found.")
        st.caption("Tip: Neo4j must be running for :AutomationAlert nodes to be created. "
                   "Recent events from the SQLite log are shown below instead.")
        recent = list_events(limit=20)
        if recent:
            _render_event_table(recent)
        return

    st.markdown(f"**{len(alerts)} unresolved alert(s)**")
    for al in alerts:
        sev  = al.get("severity", "WARNING")
        badge = _sev_badge(sev)
        entity = al.get("entity_id", "unknown")
        msg  = al.get("message", "")
        aid  = al.get("alert_id", "")
        created = al.get("created_at", "")[:19].replace("T", " ")

        with st.expander(f"{badge} {sev} — {entity}  ·  {created}", expanded=(sev == "CRITICAL")):
            st.markdown(f"**Alert ID:** `{aid}`")
            st.markdown(f"**Message:** {msg}")

            if st.button(f"✅ Mark Resolved", key=f"resolve_{aid}"):
                ok, msg2 = resolve_alert(aid, resolved_by="operator")
                if ok:
                    st.success(msg2)
                    st.rerun()
                else:
                    st.error(msg2)


# ════════════════════════════════════════════════════════════════════════════
#  TAB 1 — RULES LIST
# ════════════════════════════════════════════════════════════════════════════

def _render_rules():
    st.subheader("📋 Automation Rules")
    rules = list_rules()
    if not rules:
        st.info("No rules defined.")
        return

    # Summary metrics
    total    = len(rules)
    enabled  = sum(1 for r in rules if r["enabled"])
    disabled = total - enabled

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Rules",    total)
    m2.metric("Enabled",        enabled)
    m3.metric("Disabled",       disabled)
    st.markdown("---")

    # Group by branch
    by_branch: dict[str, list] = {}
    for r in rules:
        by_branch.setdefault(r["branch"], []).append(r)

    for branch, brules in sorted(by_branch.items()):
        icon = _branch_icon(branch)
        st.markdown(f"#### {icon} {branch.upper()}")
        for rule in brules:
            _rule_card(rule)
        st.markdown("<br>", unsafe_allow_html=True)


def _rule_card(rule: dict):
    enabled = bool(rule["enabled"])
    status  = "🟢" if enabled else "⚫"
    sev     = rule["action_payload"].get("severity", "")
    badge   = _sev_badge(sev)

    with st.expander(
        f"{status} {badge} **{rule['name']}** "
        f"— trigger: `{rule['trigger_type']}` < {rule['trigger_value']}",
        expanded=False,
    ):
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"**ID:** `{rule['rule_id']}`")
            st.markdown(f"**Description:** {rule.get('description','—')}")
            st.markdown(
                f"**Trigger:** `{rule['trigger_type']}` threshold `{rule['trigger_value']}`  "
                f"| **Action:** `{rule['action_type']}`  "
                f"| **Cooldown:** {rule['cooldown_min']} min"
            )
            if rule["action_payload"].get("message"):
                st.caption(f"Message template: {rule['action_payload']['message'][:100]}")
        with c2:
            # Toggle enabled
            new_state = st.toggle("Enabled", value=enabled, key=f"tog_{rule['rule_id']}")
            if new_state != enabled:
                update_rule(rule["rule_id"], {"enabled": 1 if new_state else 0})
                st.rerun()

            # Delete
            if st.button("🗑️ Delete", key=f"del_{rule['rule_id']}", use_container_width=True):
                ok, msg = delete_rule(rule["rule_id"])
                if ok:
                    st.success("Deleted.")
                    st.rerun()
                else:
                    st.error(msg)


# ════════════════════════════════════════════════════════════════════════════
#  TAB 2 — EVENT LOG
# ════════════════════════════════════════════════════════════════════════════

def _render_event_log():
    st.subheader("📜 Event Log")

    col1, col2, col3 = st.columns(3)
    with col1:
        branch_filter = st.selectbox("Branch", ["all"] + _BRANCHES, key="evlog_branch")
    with col2:
        limit = st.selectbox("Show", [25, 50, 100, 200], key="evlog_limit")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    branch_arg = None if branch_filter == "all" else branch_filter
    events = list_events(limit=limit, branch=branch_arg)

    if not events:
        st.info("No events logged yet. Run an evaluation cycle to generate events.")
        return

    st.markdown(f"**{len(events)} event(s)** (latest first)")
    _render_event_table(events)


def _render_event_table(events: list[dict]):
    df = pd.DataFrame(events)
    if df.empty:
        return

    # Clean display
    display_cols = [c for c in
                    ["fired_at", "rule_name", "branch", "entity_id",
                     "actual_value", "action_type", "action_result"]
                    if c in df.columns]
    df = df[display_cols].copy()

    if "fired_at" in df.columns:
        df["fired_at"] = df["fired_at"].str[:19].str.replace("T", " ")
    if "actual_value" in df.columns:
        df["actual_value"] = df["actual_value"].round(1)
    if "action_result" in df.columns:
        df["action_result"] = df["action_result"].str[:60]

    df.columns = [c.replace("_", " ").title() for c in df.columns]
    st.dataframe(df, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
#  TAB 3 — ADD RULE
# ════════════════════════════════════════════════════════════════════════════

def _render_add_rule():
    st.subheader("➕ Add Automation Rule")
    st.markdown("Define a new trigger → action rule. It will be evaluated on every scheduler cycle.")

    with st.form("add_auto_rule_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name        = st.text_input("Rule name *",
                                        placeholder="e.g. Navy vessel watch alert")
            description = st.text_area("Description", height=80,
                                       placeholder="When does this rule fire and why?")
            branch      = st.selectbox("Branch", _BRANCHES)
            cooldown    = st.number_input("Cooldown (minutes)", min_value=5,
                                          max_value=10080, value=60)
        with c2:
            trigger_type  = st.selectbox("Trigger type", _TRIGGER_TYPES)
            trigger_value = st.number_input(
                "Threshold value",
                value=30.0,
                help="score_below/above: readiness % | days_since_maintenance: days",
            )
            action_type = st.selectbox("Action", _ACTION_TYPES)
            severity    = st.selectbox("Severity", _SEVERITIES)
            enabled     = st.checkbox("Enabled immediately", value=True)

        st.markdown("**Action message template**")
        st.caption("Use `{entity_id}` and `{actual_value:.1f}` as placeholders.")
        message = st.text_area(
            "Message",
            value="Asset {entity_id} value is {actual_value:.1f} — requires attention.",
            height=80,
        )

        webhook_url = ""
        if action_type == "webhook":
            webhook_url = st.text_input("Webhook URL", placeholder="https://your-endpoint/hook")

        submitted = st.form_submit_button("✅ Create Rule", type="primary")

    if submitted:
        if not name.strip():
            st.error("Rule name is required.")
            return

        payload: dict = {"severity": severity, "message": message}
        if action_type == "create_alert_node":
            neo4j_map = {"iaf": "Aircraft", "army": "ArmyAsset",
                         "navy": "Vessel", "all": "Aircraft"}
            payload["neo4j_label"] = neo4j_map.get(branch, "Aircraft")
        if action_type == "webhook" and webhook_url:
            payload["url"] = webhook_url

        ok, result = add_rule({
            "name":          name.strip(),
            "description":   description,
            "branch":        branch,
            "trigger_type":  trigger_type,
            "trigger_value": trigger_value,
            "action_type":   action_type,
            "action_payload": payload,
            "cooldown_min":  cooldown,
            "enabled":       enabled,
        })
        if ok:
            st.success(f"✅ Rule created — ID: `{result}`")
            st.session_state.auto_tab = 1
            st.rerun()
        else:
            st.error(f"Failed: {result}")


# ════════════════════════════════════════════════════════════════════════════
#  TAB 4 — SCHEDULER
# ════════════════════════════════════════════════════════════════════════════

def _render_scheduler():
    st.subheader("⚙️ Scheduler Control")

    status = scheduler_status()

    c1, c2, c3 = st.columns(3)
    c1.metric("Status", "Running 🟢" if status["running"] else "Stopped ⚫")
    c2.metric("Scheduled jobs", status["job_count"])
    c3.metric("Next run", (status["next_run"] or "—")[:19].replace("T", " "))

    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        interval = st.number_input("Interval (minutes)", min_value=1,
                                   max_value=1440, value=5)
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("▶️ Start Scheduler", use_container_width=True,
                     disabled=status["running"]):
            start_scheduler(interval_minutes=int(interval))
            st.success(f"Scheduler started — every {interval} min.")
            st.rerun()
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⏹️ Stop Scheduler", use_container_width=True,
                     disabled=not status["running"]):
            stop_scheduler()
            st.warning("Scheduler stopped.")
            st.rerun()

    st.markdown("---")
    st.markdown("### Manual trigger")
    st.caption(
        "Run one full evaluation cycle immediately, regardless of scheduler state. "
        "Useful for testing rules."
    )
    if st.button("⚡ Run Evaluation Cycle Now", type="primary"):
        with st.spinner("Evaluating all enabled rules…"):
            events = run_evaluation_cycle()
        if events:
            st.success(f"{len(events)} event(s) fired!")
            _render_event_table(events)
        else:
            st.info("Cycle complete — no rules triggered.")

    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
The scheduler runs `run_evaluation_cycle()` on a background thread:

1. **Load** all enabled rules from SQLite.
2. For each rule, **evaluate** the trigger against live gold-store data.
3. For each entity that crosses the threshold, **check cooldown** (no repeat within N minutes).
4. **Dispatch action** — create Neo4j `:AutomationAlert` node, log to SQLite, or POST webhook.
5. **Persist event** to `automation_events` table for audit.

The cycle is stateless — safe to run multiple times.
""")

    # APScheduler install hint
    try:
        import apscheduler  # noqa: F401
    except ImportError:
        st.warning(
            "APScheduler is not installed. The background scheduler will not start.\n\n"
            "Install with: `pip install apscheduler>=3.10`"
        )
