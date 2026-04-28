"""
Shodhan-Navy – Sankalp Transformation Agent (Indian Navy)
Raw → Gold quality tables for naval assets.
"""
import sqlite3, pandas as pd, logging
from datetime import date, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Shodhan-Navy] %(message)s")
logger = logging.getLogger("shodhan_navy")

RAW_DB  = "data/processed/sankalp_navy_raw.db"
GOLD_DB = "data/processed/sankalp_navy_gold.db"


def _base_readiness(sea_hours) -> float:
    """Navy heuristic: major refit cycle ~3000 sea hours."""
    try:
        h = float(sea_hours)
    except (ValueError, TypeError):
        h = 0.0
    score = 100 - (h / 30)
    return max(0.0, min(100.0, round(score, 2)))


def transform() -> str:
    raw  = sqlite3.connect(RAW_DB)
    gold = sqlite3.connect(GOLD_DB)

    # vessels_gold
    vessels = pd.read_sql("SELECT * FROM navy_vessels", raw)
    vessels["last_refit_date"] = pd.to_datetime(vessels["last_refit_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    vessels["sea_hours"]       = pd.to_numeric(vessels["sea_hours"], errors="coerce").fillna(0)
    vessels["readiness_base_score"] = vessels["sea_hours"].apply(_base_readiness)
    vessels.to_sql("vessels_gold", gold, if_exists="replace", index=False)
    logger.info(f"vessels_gold: {len(vessels)} rows")

    # navy_crew_gold
    crew = pd.read_sql("SELECT * FROM navy_crew", raw)
    crew.to_sql("navy_crew_gold", gold, if_exists="replace", index=False)
    logger.info(f"navy_crew_gold: {len(crew)} rows")

    # sorties_gold
    sorties = pd.read_sql("SELECT * FROM navy_sorties", raw)
    sorties["date"]               = pd.to_datetime(sorties["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    sorties["fuel_consumed_tons"] = pd.to_numeric(sorties["fuel_consumed_tons"], errors="coerce").fillna(0)
    sorties.to_sql("sorties_gold", gold, if_exists="replace", index=False)
    logger.info(f"sorties_gold: {len(sorties)} rows")

    # vessel readiness scores
    def days_since(ds):
        try: return (date.today() - datetime.strptime(ds, "%Y-%m-%d").date()).days
        except: return 365

    s_count  = sorties.groupby("vessel_id").size().reset_index(name="sortie_count")
    last_s   = sorties.groupby("vessel_id")["date"].max().reset_index(name="last_sortie_date")
    merged   = vessels.merge(s_count, on="vessel_id", how="left")
    merged   = merged.merge(last_s,   on="vessel_id", how="left")
    merged["sortie_count"]     = merged["sortie_count"].fillna(0)
    merged["last_sortie_date"] = merged["last_sortie_date"].fillna(merged["last_refit_date"])
    merged["days_since"]       = merged["last_sortie_date"].apply(days_since)
    merged["final_readiness_score"] = (
        merged["readiness_base_score"] * 0.6
        - merged["days_since"] * 0.05
        + merged["sortie_count"] * 0.2
    ).clip(0, 100).round(2)
    merged.to_sql("vessel_readiness", gold, if_exists="replace", index=False)
    logger.info(f"vessel_readiness computed for {len(merged)} vessels")

    raw.close(); gold.close()
    return GOLD_DB


if __name__ == "__main__":
    print(transform())
