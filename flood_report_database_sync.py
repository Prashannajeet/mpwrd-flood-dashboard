from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from sqlalchemy import create_engine, text
except ImportError as exc:  # pragma: no cover - shown as CLI message
    raise SystemExit(
        "Database sync requires SQLAlchemy and a database driver. "
        "Install requirements.txt, then set DATABASE_URL."
    ) from exc


APP_DIR = Path(__file__).resolve().parent
RIVER_FLOW_FORECAST_DB = APP_DIR / "data" / "river_flow_forecasts.sqlite"


POSTGRES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS flood_reports (
        report_key VARCHAR(80) PRIMARY KEY,
        report_date DATE NOT NULL,
        report_time TIME NOT NULL,
        season_year INTEGER,
        source_filename VARCHAR(500),
        source_file_hash VARCHAR(128),
        extraction_method VARCHAR(60),
        parsed_folder VARCHAR(500),
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reservoir_master (
        reservoir_name VARCHAR(255) NOT NULL,
        district VARCHAR(160) NOT NULL,
        lsl_m NUMERIC(10,3),
        frl_m NUMERIC(10,3),
        live_capacity_frl_mcm NUMERIC(14,3),
        total_no_of_gates INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (reservoir_name, district)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS river_station_master (
        river_name VARCHAR(160) NOT NULL,
        gauge_station VARCHAR(255) NOT NULL,
        district VARCHAR(160) NOT NULL,
        danger_or_max_water_level_m NUMERIC(10,3),
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (river_name, gauge_station, district)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reservoir_observations (
        report_key VARCHAR(80) NOT NULL REFERENCES flood_reports(report_key) ON DELETE CASCADE,
        reservoir_name VARCHAR(255) NOT NULL,
        district VARCHAR(160) NOT NULL,
        source_row_no INTEGER,
        observed_at TIMESTAMP NOT NULL,
        lsl_m NUMERIC(10,3),
        frl_m NUMERIC(10,3),
        live_capacity_frl_mcm NUMERIC(14,3),
        water_level_m NUMERIC(10,3),
        current_live_capacity_mcm NUMERIC(14,3),
        filling_percent NUMERIC(8,3),
        rainfall_daily_mm NUMERIC(10,2),
        rainfall_total_mm NUMERIC(10,2),
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (reservoir_name, district, observed_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS river_observations (
        report_key VARCHAR(80) NOT NULL REFERENCES flood_reports(report_key) ON DELETE CASCADE,
        river_name VARCHAR(160) NOT NULL,
        gauge_station VARCHAR(255) NOT NULL,
        district VARCHAR(160) NOT NULL,
        source_row_no INTEGER,
        danger_or_max_water_level_m NUMERIC(10,3),
        observed_at TIMESTAMP NOT NULL,
        water_level_m NUMERIC(10,3),
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (river_name, gauge_station, district, observed_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reservoir_gate_observations (
        report_key VARCHAR(80) NOT NULL REFERENCES flood_reports(report_key) ON DELETE CASCADE,
        reservoir_name VARCHAR(255) NOT NULL,
        district VARCHAR(160) NOT NULL,
        source_row_no INTEGER,
        total_no_of_gates INTEGER,
        gate_opened_count INTEGER,
        opening_m NUMERIC(10,3),
        gate_opening_date DATE,
        gate_opening_time TIME,
        discharge_cumecs NUMERIC(14,3),
        discharge_cusec NUMERIC(14,3),
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (report_key, reservoir_name, district)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_river_flow_forecasts (
        forecast_id VARCHAR(64) PRIMARY KEY,
        generated_at TIMESTAMP NOT NULL,
        river_name VARCHAR(160),
        gauge_station VARCHAR(255),
        district VARCHAR(160),
        basin VARCHAR(160),
        observed_at TIMESTAMP,
        forecast_time TIMESTAMP,
        lead_day INTEGER,
        water_level_m NUMERIC(10,3),
        danger_gap_m NUMERIC(10,3),
        wl_delta_m NUMERIC(10,3),
        glofas_flow_cms NUMERIC(14,3),
        grrr_flow_cms NUMERIC(14,3),
        predicted_discharge_cumecs NUMERIC(14,3),
        watch_cms NUMERIC(14,3),
        flood_cms NUMERIC(14,3),
        danger_cms NUMERIC(14,3),
        risk_band VARCHAR(40),
        source_model VARCHAR(120),
        prediction_confidence NUMERIC(6,3),
        model_status VARCHAR(500),
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


MYSQL_DDL = [
    ddl.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "DATETIME DEFAULT CURRENT_TIMESTAMP")
    .replace("REFERENCES flood_reports(report_key) ON DELETE CASCADE", "")
    for ddl in POSTGRES_DDL
]


TABLE_KEYS = {
    "flood_reports": ["report_key"],
    "reservoir_master": ["reservoir_name", "district"],
    "river_station_master": ["river_name", "gauge_station", "district"],
    "reservoir_observations": ["reservoir_name", "district", "observed_at"],
    "river_observations": ["river_name", "gauge_station", "district", "observed_at"],
    "reservoir_gate_observations": ["report_key", "reservoir_name", "district"],
    "ai_river_flow_forecasts": ["forecast_id"],
}


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def parsed_report_dirs(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith("parsed"))


def report_key(meta: dict[str, Any]) -> str:
    date_part = str(meta.get("report_date") or "unknown-date")
    time_part = str(meta.get("report_time") or "00:00:00").replace(":", "")
    return f"{date_part}_{time_part}"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def read_report_folder(folder: Path) -> dict[str, pd.DataFrame | dict[str, Any]]:
    meta_path = folder / "report_meta.json"
    if not meta_path.exists():
        raise ValueError(f"Missing report_meta.json in {folder}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    key = report_key(meta)

    report = pd.DataFrame(
        [
            {
                "report_key": key,
                "report_date": meta.get("report_date"),
                "report_time": meta.get("report_time"),
                "season_year": meta.get("season_year"),
                "source_filename": meta.get("source_filename"),
                "source_file_hash": meta.get("source_file_hash"),
                "extraction_method": meta.get("extraction_method"),
                "parsed_folder": folder.name,
            }
        ]
    )

    reservoir_master = read_csv(folder / "reservoirs.csv")
    river_master = read_csv(folder / "river_gauge_stations.csv")

    reservoir_obs = read_csv(folder / "reservoir_status_observations.csv")
    if not reservoir_obs.empty:
        reservoir_obs.insert(0, "report_key", key)
        reservoir_obs["observed_at"] = pd.to_datetime(reservoir_obs["observed_at"], errors="coerce")

    river_obs = read_csv(folder / "river_water_level_observations.csv")
    if not river_obs.empty:
        river_obs.insert(0, "report_key", key)
        river_obs["observed_at"] = pd.to_datetime(river_obs["observed_at"], errors="coerce")

    gate_obs = read_csv(folder / "reservoir_gate_observations.csv")
    if not gate_obs.empty:
        gate_obs.insert(0, "report_key", key)

    return {
        "flood_reports": report,
        "reservoir_master": reservoir_master,
        "river_station_master": river_master,
        "reservoir_observations": reservoir_obs,
        "river_observations": river_obs,
        "reservoir_gate_observations": gate_obs,
        "meta": meta,
    }


def create_schema(engine) -> None:
    ddl_statements = MYSQL_DDL if engine.dialect.name.startswith("mysql") else POSTGRES_DDL
    with engine.begin() as conn:
        for ddl in ddl_statements:
            conn.execute(text(ddl))


def read_ai_river_flow_forecasts(parsed_root: Path = APP_DIR) -> pd.DataFrame:
    db_path = parsed_root / "data" / "river_flow_forecasts.sqlite"
    if not db_path.exists():
        db_path = RIVER_FLOW_FORECAST_DB
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            frame = pd.read_sql_query("SELECT * FROM river_flow_forecasts", conn)
    except Exception:
        return pd.DataFrame()
    for column in ["generated_at", "observed_at", "forecast_time"]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def upsert_frame(engine, table_name: str, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    frame = frame.where(pd.notna(frame), None)
    rows = [{key: clean_value(value) for key, value in row.items()} for row in frame.to_dict("records")]
    columns = list(frame.columns)
    keys = TABLE_KEYS[table_name]
    update_columns = [column for column in columns if column not in keys]
    column_sql = ", ".join(columns)
    value_sql = ", ".join(f":{column}" for column in columns)

    if engine.dialect.name.startswith("mysql"):
        update_sql = ", ".join(f"{column}=VALUES({column})" for column in update_columns)
        statement = text(
            f"INSERT INTO {table_name} ({column_sql}) VALUES ({value_sql}) "
            f"ON DUPLICATE KEY UPDATE {update_sql}"
        )
    else:
        conflict_sql = ", ".join(keys)
        update_sql = ", ".join(f"{column}=EXCLUDED.{column}" for column in update_columns)
        statement = text(
            f"INSERT INTO {table_name} ({column_sql}) VALUES ({value_sql}) "
            f"ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}"
        )

    with engine.begin() as conn:
        conn.execute(statement, rows)
    return len(rows)


def sync_reports(database_url: str, parsed_root: Path = APP_DIR) -> dict[str, int]:
    engine = create_engine(database_url, future=True)
    create_schema(engine)
    totals = {table: 0 for table in TABLE_KEYS}
    for folder in parsed_report_dirs(parsed_root):
        payload = read_report_folder(folder)
        for table_name in [table for table in TABLE_KEYS if table != "ai_river_flow_forecasts"]:
            totals[table_name] += upsert_frame(engine, table_name, payload[table_name])  # type: ignore[arg-type]
    totals["ai_river_flow_forecasts"] += upsert_frame(engine, "ai_river_flow_forecasts", read_ai_river_flow_forecasts(parsed_root))
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync parsed MPWRD flood reports to PostgreSQL or MySQL.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""), help="SQLAlchemy database URL.")
    parser.add_argument("--parsed-root", default=str(APP_DIR), help="Folder containing parsed_* report directories.")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required. Example: postgresql+psycopg2://user:password@host:5432/mpwrd")
    totals = sync_reports(args.database_url, Path(args.parsed_root))
    print(json.dumps(totals, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
