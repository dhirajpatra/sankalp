"""
Shodhan-Army – Sankalp Transformation Agent (Indian Army)
Raw → Gold quality tables for army assets.
"""
import sqlite3, pandas as pd, logging
from datetime import date

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Shodhan-Army] %(message)s")
logger = logging.getLogger("shodhan_army")

RAW_DB  = "data/processed/sankalp_army_raw.db"
GOLD_DB = "data/processed/sankalp_army_gold.db"


def _base_readiness(op_hours: float) -> float:
    """Army heuristic: heavy maintenance needed every 1500 operational hours."""
    score = 100 - (op_hours / 15)
    return max(0.0, min(100.0, round(score, 2)))


def transform() -> str:
    raw  = sqlite3.connect(RAW_DB)
    gold = sqlite3.connect(GOLD_DB)

    # assets_gold
    assets = pd.read_sql("SELECT * FROM army_assets", raw)
    assets["last_service_date"]  = pd.to_datetime(assets["last_service_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    assets["operational_hours"]  = pd.to_numeric(assets["operational_hours"], errors="coerce").fillna(0)
    assets["readiness_base_score"] = assets["operational_hours"].apply(_base_readiness)
    assets.to_sql("assets_gold", gold, if_exists="replace", index=False)
    logger.info(f"assets_gold: {len(assets)} rows")

    # army_crew_gold
    crew = pd.read_sql("SELECT * FROM army_crew", raw)
    crew.to_sql("army_crew_gold", gold, if_exists="replace", index=False)
    logger.info(f"army_crew_gold: {len(crew)} rows")

    # ops_gold
    ops = pd.read_sql("SELECT * FROM army_ops", raw)
    ops["date"]          = pd.to_datetime(ops["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    ops["ammo_expended"] = pd.to_numeric(ops["ammo_expended"], errors="coerce").fillna(0)
    ops.to_sql("ops_gold", gold, if_exists="replace", index=False)
    logger.info(f"ops_gold: {len(ops)} rows")

    # compute readiness scores (like bhavishyavani)
    from datetime import datetime
    def days_since(ds):
        try: return (date.today() - datetime.strptime(ds, "%Y-%m-%d").date()).days
        except: return 365

    op_count   = ops.groupby("asset_id").size().reset_index(name="op_count")
    last_op    = ops.groupby("asset_id")["date"].max().reset_index(name="last_op_date")
    merged     = assets.merge(op_count, on="asset_id", how="left")
    merged     = merged.merge(last_op,   on="asset_id", how="left")
    merged["op_count"]   = merged["op_count"].fillna(0)
    merged["last_op_date"] = merged["last_op_date"].fillna(merged["last_service_date"])
    merged["days_since"] = merged["last_op_date"].apply(days_since)
    merged["final_readiness_score"] = (
        merged["readiness_base_score"] * 0.6
        - merged["days_since"] * 0.05
        + merged["op_count"] * 0.2
    ).clip(0, 100).round(2)
    merged.to_sql("asset_readiness", gold, if_exists="replace", index=False)
    logger.info(f"asset_readiness computed for {len(merged)} assets")

    raw.close(); gold.close()
    return GOLD_DB


if __name__ == "__main__":
    print(transform())
