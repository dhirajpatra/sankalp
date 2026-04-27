"""
Ganana (गणना) – Sankalp Ingestion Agent
DRDO requirement: Ingest multi-source defence logistics data into a unified raw store.
"""

import sqlite3
import pandas as pd
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Ganana] %(message)s")
logger = logging.getLogger("ganana")

RAW_DB = "sankalp_raw.db"
DATA_DIR = Path("data/raw")

CSV_TABLES = {
    "aircraft": DATA_DIR / "aircraft.csv",
    "crew": DATA_DIR / "crew.csv",
    "missions": DATA_DIR / "missions.csv",
}


def ingest() -> dict:
    """Read CSV files and persist to SQLite raw store."""
    conn = sqlite3.connect(RAW_DB)
    status = {}

    for table_name, csv_path in CSV_TABLES.items():
        if not csv_path.exists():
            logger.warning(f"File not found: {csv_path}. Skipping {table_name}.")
            continue

        df = pd.read_csv(csv_path)

        # Log null warnings – Indian Army/IAF data often has missing maintenance records
        nulls = df.isnull().sum()
        for col, count in nulls.items():
            if count > 0:
                logger.warning(f"Table '{table_name}' column '{col}' has {count} null(s).")

        df.to_sql(table_name, conn, if_exists="replace", index=False)
        status[table_name] = {"rows": len(df), "columns": list(df.columns)}
        logger.info(f"Ingested '{table_name}': {len(df)} rows.")

    conn.close()
    logger.info(f"Raw store ready: {RAW_DB}")
    return status


if __name__ == "__main__":
    result = ingest()
    print(result)
