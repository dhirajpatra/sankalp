"""
Ganana-Army – Sankalp Ingestion Agent (Indian Army)
Reads army CSVs → SQLite raw store.
"""
import sqlite3, pandas as pd, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Ganana-Army] %(message)s")
logger = logging.getLogger("ganana_army")

RAW_DB   = "sankalp_army_raw.db"
DATA_DIR = Path("data/raw")

CSV_TABLES = {
    "army_assets": DATA_DIR / "army_assets.csv",
    "army_crew":   DATA_DIR / "army_crew.csv",
    "army_ops":    DATA_DIR / "army_ops.csv",
}

SAMPLE_ASSETS = """asset_id,asset_type,unit,last_service_date,operational_hours,total_assets
AR_001,T-90 Bhishma,Armoured Corps,2025-03-10,800,45
AR_002,Arjun MBT Mk1A,Armoured Corps,2025-04-05,1200,12
AR_003,BMP-2 Sarath,Mechanised Infantry,2025-02-18,650,120
AR_004,K9 Vajra,Artillery,2025-05-01,420,100
AR_005,M777 Howitzer,Artillery,2025-01-22,980,145
AR_006,Pinaka MLRS,Artillery,2025-06-10,310,44
AR_007,HAL Rudra,Army Aviation,2025-03-28,560,12
AR_008,ALH Dhruv,Army Aviation,2025-05-15,700,75
AR_009,T-90 Bhishma,Armoured Corps,2025-01-09,1500,45
AR_010,BMP-2 Sarath,Infantry,2025-04-20,400,120
AR_011,Arjun MBT Mk1A,Armoured Corps,2025-02-14,900,12
AR_012,K9 Vajra,Artillery,2024-12-01,1800,100
AR_013,Smerch MLRS,Artillery,2025-03-05,620,8
AR_014,ALH Dhruv,Army Aviation,2025-06-01,150,75
AR_015,T-90 Bhishma,Para SF,2025-05-22,1100,45
AR_016,BMP-2 Sarath,Engineers,2025-04-11,740,120
AR_017,HAL Rudra,Army Aviation,2024-11-30,1650,12
AR_018,K9 Vajra,Artillery,2025-02-28,490,100
AR_019,M777 Howitzer,Infantry,2025-06-15,220,145
AR_020,Pinaka MLRS,Artillery,2025-01-15,880,44
"""

SAMPLE_CREW = """crew_id,name,rank,vehicle_qualified
ARC-001,Brigadier Arjun Singh,Brigadier,T-90 Bhishma
ARC-002,Colonel Vikram Sharma,Colonel,Arjun MBT Mk1A
ARC-003,Lt Col Rajan Nair,Lieutenant Colonel,BMP-2 Sarath
ARC-004,Major Pradeep Yadav,Major,K9 Vajra
ARC-005,Captain Suresh Patel,Captain,M777 Howitzer
ARC-006,Major Kiran Mehta,Major,Pinaka MLRS
ARC-007,Captain Deepak Joshi,Captain,HAL Rudra
ARC-008,Lt Col Amitabh Roy,Lieutenant Colonel,ALH Dhruv
ARC-009,Colonel Shyam Verma,Colonel,T-90 Bhishma
ARC-010,Major Ravi Gupta,Major,BMP-2 Sarath
ARC-011,Brigadier Manish Tiwari,Brigadier,Arjun MBT Mk1A
ARC-012,Captain Sunita Rao,Captain,K9 Vajra
ARC-013,Major Pooja Agarwal,Major,Smerch MLRS
ARC-014,Lt Col Neha Sharma,Lieutenant Colonel,ALH Dhruv
ARC-015,Colonel Ankit Kumar,Colonel,T-90 Bhishma
ARC-016,Major Rohit Mishra,Major,BMP-2 Sarath
ARC-017,Captain Gaurav Sinha,Captain,HAL Rudra
ARC-018,Lt Col Anil Pandey,Lieutenant Colonel,Pinaka MLRS
ARC-019,Colonel Vijay Chauhan,Colonel,M777 Howitzer
ARC-020,Major Rahul Desai,Major,K9 Vajra
"""

SAMPLE_OPS = """op_id,asset_id,crew_id,date,op_type,ammo_expended
OP-0001,AR_001,ARC-001,2024-11-10,Border Vigil,0
OP-0002,AR_002,ARC-002,2024-10-15,Live Fire Exercise,200
OP-0003,AR_003,ARC-003,2024-12-01,Patrol,0
OP-0004,AR_004,ARC-004,2024-11-20,Training,50
OP-0005,AR_005,ARC-005,2024-09-05,Live Fire Exercise,150
OP-0006,AR_006,ARC-006,2024-10-22,Strike Mission,400
OP-0007,AR_007,ARC-007,2024-11-30,Recon,0
OP-0008,AR_008,ARC-008,2024-12-10,Logistics,0
OP-0009,AR_009,ARC-009,2024-10-01,Border Vigil,0
OP-0010,AR_010,ARC-010,2024-11-15,Counter-Insurgency,100
OP-0011,AR_011,ARC-011,2024-09-20,Live Fire Exercise,300
OP-0012,AR_012,ARC-012,2024-12-05,Training,75
OP-0013,AR_013,ARC-013,2024-10-28,Strike Mission,500
OP-0014,AR_014,ARC-014,2024-11-08,Logistics,0
OP-0015,AR_015,ARC-015,2024-12-15,Border Vigil,0
OP-0016,AR_016,ARC-016,2024-09-12,Patrol,0
OP-0017,AR_017,ARC-017,2024-10-05,Recon,0
OP-0018,AR_018,ARC-018,2024-11-25,Training,25
OP-0019,AR_019,ARC-019,2024-12-08,Live Fire Exercise,180
OP-0020,AR_020,ARC-020,2024-10-18,Strike Mission,350
"""


def _write_samples():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not (DATA_DIR / "army_assets.csv").exists():
        (DATA_DIR / "army_assets.csv").write_text(SAMPLE_ASSETS.strip())
    if not (DATA_DIR / "army_crew.csv").exists():
        (DATA_DIR / "army_crew.csv").write_text(SAMPLE_CREW.strip())
    if not (DATA_DIR / "army_ops.csv").exists():
        (DATA_DIR / "army_ops.csv").write_text(SAMPLE_OPS.strip())


def ingest() -> dict:
    _write_samples()
    conn = sqlite3.connect(RAW_DB)
    status = {}
    for table_name, csv_path in CSV_TABLES.items():
        df = pd.read_csv(csv_path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        status[table_name] = {"rows": len(df), "columns": list(df.columns)}
        logger.info(f"Ingested '{table_name}': {len(df)} rows.")
    conn.close()
    return status


if __name__ == "__main__":
    print(ingest())
