from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd


HINDCAST_TEMPLATE_COLUMNS = [
    "station_code",
    "linked_cwc_station",
    "linked_comid",
    "forecast_issue_time",
    "forecast_valid_time",
    "lead_hours",
    "raw_forecast_discharge_cms",
    "model_source",
]


TRAINING_COLUMNS = [
    "station_code",
    "linked_cwc_station",
    "linked_comid",
    "forecast_issue_time",
    "forecast_valid_time",
    "lead_hours",
    "raw_forecast_discharge_cms",
    "observed_discharge_cms",
    "basin",
    "river",
    "district",
    "model_source",
]


def ensure_hindcast_template(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=HINDCAST_TEMPLATE_COLUMNS).to_csv(path, index=False)


def normalize_hindcast(path: Path) -> pd.DataFrame:
    ensure_hindcast_template(path)
    hindcast = pd.read_csv(path)
    for col in HINDCAST_TEMPLATE_COLUMNS:
        if col not in hindcast:
            hindcast[col] = pd.NA
    hindcast = hindcast[HINDCAST_TEMPLATE_COLUMNS].copy()
    hindcast["forecast_issue_time"] = pd.to_datetime(hindcast["forecast_issue_time"], errors="coerce")
    hindcast["forecast_valid_time"] = pd.to_datetime(hindcast["forecast_valid_time"], errors="coerce")
    hindcast["lead_hours"] = pd.to_numeric(hindcast["lead_hours"], errors="coerce")
    hindcast["raw_forecast_discharge_cms"] = pd.to_numeric(hindcast["raw_forecast_discharge_cms"], errors="coerce")
    hindcast["station_code"] = hindcast["station_code"].fillna("").astype(str).str.strip()
    hindcast["linked_cwc_station"] = hindcast["linked_cwc_station"].fillna("").astype(str).str.strip()
    hindcast["model_source"] = hindcast["model_source"].fillna("Historical model hindcast").astype(str)
    hindcast = hindcast.dropna(subset=["forecast_valid_time", "raw_forecast_discharge_cms"])
    hindcast = hindcast[
        (hindcast["station_code"].str.len() > 0) | (hindcast["linked_cwc_station"].str.len() > 0)
    ].copy()
    return hindcast


def load_reference_tables(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        cwc_daily = pd.read_sql_query(
            """
            SELECT station_name AS linked_cwc_station, date,
                   discharge_cms_mean AS observed_discharge_cms,
                   basin, river, district
            FROM cwc_daily_discharge
            """,
            con,
            parse_dates=["date"],
        )
        linkages = pd.read_sql_query(
            """
            SELECT station_code, effective_cwc_station_name AS linked_cwc_station,
                   linked_comid, cwc_basin AS basin, cwc_river AS river,
                   forecast_district AS district, manual_approved
            FROM gd_cwc_station_linkage
            """,
            con,
        )
    linkages["station_code"] = linkages["station_code"].fillna("").astype(str).str.strip()
    linkages["linked_cwc_station"] = linkages["linked_cwc_station"].fillna("").astype(str).str.strip()
    return cwc_daily, linkages


def build_training_overlap(hindcast: pd.DataFrame, cwc_daily: pd.DataFrame, linkages: pd.DataFrame) -> pd.DataFrame:
    if hindcast.empty:
        return pd.DataFrame(columns=TRAINING_COLUMNS)

    frame = hindcast.copy()
    station_link = linkages[["station_code", "linked_cwc_station", "linked_comid", "basin", "river", "district", "manual_approved"]].copy()
    frame = frame.merge(
        station_link.rename(
            columns={
                "linked_cwc_station": "linked_cwc_station_from_code",
                "linked_comid": "linked_comid_from_code",
                "basin": "basin_from_code",
                "river": "river_from_code",
                "district": "district_from_code",
            }
        ),
        on="station_code",
        how="left",
    )
    frame["linked_cwc_station"] = frame["linked_cwc_station"].where(
        frame["linked_cwc_station"].astype(str).str.len() > 0,
        frame["linked_cwc_station_from_code"],
    )
    frame["linked_comid"] = frame["linked_comid"].where(
        frame["linked_comid"].notna(),
        frame["linked_comid_from_code"],
    )
    frame["valid_date"] = frame["forecast_valid_time"].dt.normalize()
    obs = cwc_daily.copy()
    obs["date"] = pd.to_datetime(obs["date"], errors="coerce").dt.normalize()
    training = frame.merge(
        obs,
        left_on=["linked_cwc_station", "valid_date"],
        right_on=["linked_cwc_station", "date"],
        how="inner",
    )
    training["basin"] = training["basin"].fillna(training.get("basin_from_code"))
    training["river"] = training["river"].fillna(training.get("river_from_code"))
    training["district"] = training["district"].fillna(training.get("district_from_code"))
    return training[TRAINING_COLUMNS].sort_values(["station_code", "forecast_valid_time"])


def write_database_tables(db_path: Path, hindcast: pd.DataFrame, training: pd.DataFrame) -> None:
    with sqlite3.connect(db_path) as con:
        hindcast.to_sql("historical_model_hindcast", con, index=False, if_exists="replace")
        training.to_sql("historical_forecast_observation_training", con, index=False, if_exists="replace")
        con.execute("CREATE INDEX IF NOT EXISTS idx_hindcast_station_time ON historical_model_hindcast(station_code, forecast_valid_time)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_training_station_time ON historical_forecast_observation_training(station_code, forecast_valid_time)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build historical forecast/CWC observation overlap for V02 bias correction.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--hindcast-csv", required=True, type=Path)
    parser.add_argument("--training-output-csv", required=True, type=Path)
    args = parser.parse_args()

    hindcast = normalize_hindcast(args.hindcast_csv)
    cwc_daily, linkages = load_reference_tables(args.db)
    training = build_training_overlap(hindcast, cwc_daily, linkages)
    args.training_output_csv.parent.mkdir(parents=True, exist_ok=True)
    training.to_csv(args.training_output_csv, index=False)
    write_database_tables(args.db, hindcast, training)
    summary = {
        "hindcast_csv": str(args.hindcast_csv),
        "hindcast_rows": int(len(hindcast)),
        "training_overlap_rows": int(len(training)),
        "training_output_csv": str(args.training_output_csv),
        "stations_with_overlap": int(training["station_code"].nunique()) if not training.empty else 0,
        "linked_cwc_stations_with_overlap": int(training["linked_cwc_station"].nunique()) if not training.empty else 0,
    }
    (args.training_output_csv.parent / "hindcast_training_overlap_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
