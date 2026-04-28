"""
Ganana-Navy – Sankalp Ingestion Agent (Indian Navy)
Reads navy CSVs → SQLite raw store.
"""
import sqlite3, pandas as pd, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s [Ganana-Navy] %(message)s")
logger = logging.getLogger("ganana_navy")

RAW_DB   = "data/processed/sankalp_navy_raw.db"
DATA_DIR = Path("data/raw")

CSV_TABLES = {
    "navy_vessels": DATA_DIR / "navy_vessels.csv",
    "navy_crew":    DATA_DIR / "navy_crew.csv",
    "navy_sorties": DATA_DIR / "navy_sorties.csv",
}

SAMPLE_VESSELS = """vessel_id,vessel_type,flotilla,last_refit_date,sea_hours,displacement_tons
IN_001,INS Vikrant (Carrier),Western Fleet,2025-02-10,1200,45000
IN_002,INS Kolkata (Destroyer),Eastern Fleet,2025-03-05,800,7500
IN_003,INS Chennai (Destroyer),Western Fleet,2025-04-01,950,7500
IN_004,INS Shivalik (Frigate),Eastern Fleet,2025-01-20,1100,6200
IN_005,Sindhughosh-class Sub,Submarine Command,2025-05-10,600,3000
IN_006,Kalvari-class Sub,Submarine Command,2025-03-18,750,1750
IN_007,INS Sukanya (OPV),Southern Naval Command,2025-02-28,400,1890
IN_008,HAL Sea King,Naval Air Arm,2025-06-01,320,NA
IN_009,P-8I Poseidon,Naval Air Arm,2025-04-15,280,NA
IN_010,BrahMos Armed Vessel,Western Fleet,2025-01-05,1500,4000
IN_011,INS Kolkata (Destroyer),Western Fleet,2025-05-20,600,7500
IN_012,Kalvari-class Sub,Submarine Command,2024-12-10,1800,1750
IN_013,INS Shivalik (Frigate),Far Eastern Naval Command,2025-03-25,900,6200
IN_014,HAL Sea King,Naval Air Arm,2025-02-14,450,NA
IN_015,P-8I Poseidon,Naval Air Arm,2025-06-08,180,NA
IN_016,INS Sukanya (OPV),Andaman & Nicobar,2025-04-30,350,1890
IN_017,BrahMos Armed Vessel,Eastern Fleet,2025-01-18,1300,4000
IN_018,Sindhughosh-class Sub,Submarine Command,2025-05-05,850,3000
IN_019,INS Vikrant (Carrier),Western Fleet,2024-11-25,2000,45000
IN_020,INS Chennai (Destroyer),Southern Naval Command,2025-03-12,700,7500
"""

SAMPLE_CREW = """crew_id,name,rank,vessel_qualified
NVC-001,Vice Adm Ajay Menon,Vice Admiral,INS Vikrant (Carrier)
NVC-002,Rear Adm Sanjay Krishnan,Rear Admiral,INS Kolkata (Destroyer)
NVC-003,Cdr Priya Nair,Commander,INS Shivalik (Frigate)
NVC-004,Capt Ravi Pillai,Captain,Sindhughosh-class Sub
NVC-005,Lt Cdr Kavitha Sharma,Lieutenant Commander,Kalvari-class Sub
NVC-006,Lt Vikrant Iyer,Lieutenant,HAL Sea King
NVC-007,Cdr Aditya Rao,Commander,P-8I Poseidon
NVC-008,Capt Neha Patil,Captain,INS Sukanya (OPV)
NVC-009,Commodore Surya Bose,Commodore,BrahMos Armed Vessel
NVC-010,Lt Cdr Kiran Jha,Lieutenant Commander,INS Vikrant (Carrier)
NVC-011,Cdr Deepti Verma,Commander,INS Kolkata (Destroyer)
NVC-012,Capt Rohit Nambiar,Captain,Sindhughosh-class Sub
NVC-013,Lt Ananya Singh,Lieutenant,HAL Sea King
NVC-014,Lt Cdr Naveen Kumar,Lieutenant Commander,Kalvari-class Sub
NVC-015,Cdr Shalini Gupta,Commander,P-8I Poseidon
NVC-016,Capt Tarun Malhotra,Captain,INS Shivalik (Frigate)
NVC-017,Lt Sreeja Varma,Lieutenant,INS Sukanya (OPV)
NVC-018,Lt Cdr Hitesh Shah,Lieutenant Commander,BrahMos Armed Vessel
NVC-019,Cdr Pavan Reddy,Commander,INS Chennai (Destroyer)
NVC-020,Capt Lata Krishnamurthy,Captain,INS Vikrant (Carrier)
"""

SAMPLE_SORTIES = """sortie_id,vessel_id,crew_id,date,sortie_type,fuel_consumed_tons
SRT-0001,IN_001,NVC-001,2024-11-05,Fleet Exercise,250
SRT-0002,IN_002,NVC-002,2024-10-18,Patrol,80
SRT-0003,IN_003,NVC-003,2024-12-01,Anti-Submarine Warfare,110
SRT-0004,IN_004,NVC-004,2024-11-22,Escort,90
SRT-0005,IN_005,NVC-005,2024-09-10,Anti-Submarine Warfare,20
SRT-0006,IN_006,NVC-006,2024-10-25,ISR,15
SRT-0007,IN_007,NVC-007,2024-11-30,Patrol,45
SRT-0008,IN_008,NVC-008,2024-12-12,Humanitarian Aid,60
SRT-0009,IN_009,NVC-009,2024-10-02,ISR,180
SRT-0010,IN_010,NVC-010,2024-11-17,Strike,320
SRT-0011,IN_011,NVC-011,2024-09-22,Fleet Exercise,90
SRT-0012,IN_012,NVC-012,2024-12-07,Anti-Submarine Warfare,18
SRT-0013,IN_013,NVC-013,2024-10-30,Patrol,100
SRT-0014,IN_014,NVC-014,2024-11-10,ISR,12
SRT-0015,IN_015,NVC-015,2024-12-18,Patrol,170
SRT-0016,IN_016,NVC-016,2024-09-15,Port Visit,30
SRT-0017,IN_017,NVC-017,2024-10-08,Strike,280
SRT-0018,IN_018,NVC-018,2024-11-27,Anti-Submarine Warfare,22
SRT-0019,IN_019,NVC-019,2024-12-10,Fleet Exercise,300
SRT-0020,IN_020,NVC-020,2024-10-20,Escort,85
"""


def _write_samples():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not (DATA_DIR / "navy_vessels.csv").exists():
        (DATA_DIR / "navy_vessels.csv").write_text(SAMPLE_VESSELS.strip())
    if not (DATA_DIR / "navy_crew.csv").exists():
        (DATA_DIR / "navy_crew.csv").write_text(SAMPLE_CREW.strip())
    if not (DATA_DIR / "navy_sorties.csv").exists():
        (DATA_DIR / "navy_sorties.csv").write_text(SAMPLE_SORTIES.strip())


def ingest() -> dict:
    _write_samples()
    conn = sqlite3.connect(RAW_DB)
    status = {}
    for table_name, csv_path in CSV_TABLES.items():
        df = pd.read_csv(csv_path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        status[table_name] = {"rows": len(df)}
        logger.info(f"Ingested '{table_name}': {len(df)} rows.")
    conn.close()
    return status


if __name__ == "__main__":
    print(ingest())
